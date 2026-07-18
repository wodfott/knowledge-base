"""Collector agent: web scraping, RSS feed collection, with SimHash deduplication."""

import logging
from datetime import datetime
from typing import Optional

import feedparser
import httpx
from bs4 import BeautifulSoup

from config import settings
from storage import db
from utils import clean_text, compute_simhash, generate_doc_id, simhash_similarity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PersonalKM-Collector/1.0; "
        "+https://github.com/example/pkm)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
}

_NON_CONTENT_TAGS = frozenset({
    "script", "style", "nav", "footer", "header", "aside",
    "noscript", "iframe", "form", "button", "input", "select",
    "textarea", "svg",
})

_NON_CONTENT_CLASS_PATTERNS = (
    "nav", "menu", "sidebar", "footer", "header", "comment",
    "advertisement", "ad-", "cookie", "popup", "banner",
    "social", "share", "related", "recommend", "widget",
)


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------

def extract_main_content(html: str, url: str) -> tuple[str, str]:
    """Extract title and main text from an HTML document.

    Strips scripts, styles, navigation, footers, sidebars, and other
    non-content boilerplate.  Title detection tries five strategies in
    order: ``<title>``, ``<h1>``, ``og:title`` meta, the first heading
    of any level, and finally the raw *url*.

    Returns
    -------
    tuple[str, str]
        ``(title, cleaned_text_content)``.
    """
    soup = BeautifulSoup(html, "lxml")

    # ---- title ----------------------------------------------------------
    title = _extract_title(soup, url)

    # ---- strip non-content elements ------------------------------------
    _remove_non_content(soup)

    # ---- locate main content area --------------------------------------
    body = soup.find("body")
    if body:
        text_source = _find_main_content(body) or body
    else:
        text_source = soup

    raw_text = text_source.get_text(separator="\n", strip=True)
    content = clean_text(raw_text) if raw_text else ""

    return title, content


def _extract_title(soup: BeautifulSoup, fallback: str) -> str:
    """Extract a page title through a cascade of strategies."""
    # 1. <title> tag
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    # 2. First <h1>
    h1 = soup.find("h1")
    if h1:
        candidate = h1.get_text(strip=True)
        if candidate:
            return candidate

    # 3. Open Graph meta
    meta_og = soup.find("meta", property="og:title")
    if meta_og and meta_og.get("content"):
        return meta_og["content"].strip()

    # 4. First heading of any level
    for level in ("h2", "h3"):
        tag = soup.find(level)
        if tag:
            candidate = tag.get_text(strip=True)
            if candidate:
                return candidate

    # 5. Absolute fallback
    return fallback


def _remove_non_content(soup: BeautifulSoup) -> None:
    """Decompose boilerplate elements in-place."""
    # Tag-based removal (fast path)
    for tag_name in _NON_CONTENT_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Class / id based removal (slower path, scans all remaining elements)
    for element in soup.find_all(True):
        if _has_non_content_marker(element):
            element.decompose()


def _has_non_content_marker(element) -> bool:
    """Return ``True`` when the element carries a known boilerplate class or id."""
    elem_class = element.get("class")
    if elem_class:
        class_text = " ".join(elem_class).lower()
        if any(p in class_text for p in _NON_CONTENT_CLASS_PATTERNS):
            return True

    elem_id = element.get("id")
    if elem_id:
        id_lower = elem_id.lower()
        if any(p in id_lower for p in _NON_CONTENT_CLASS_PATTERNS):
            return True

    # role-based detection
    role = element.get("role", "")
    if role in ("navigation", "banner", "contentinfo", "complementary"):
        return True

    return False


def _find_main_content(body) -> Optional[BeautifulSoup]:
    """Heuristically locate the primary content container inside *body*.

    Returns ``None`` when no obvious container is found (caller should
    fall back to the whole body).
    """
    # Explicit semantic elements
    for selector in ("main", "article", '[role="main"]'):
        match = body.select_one(selector)
        if match:
            return match

    # Class-based heuristics
    for element in body.find_all(True):
        classes = element.get("class")
        if classes and any("content" in c.lower() for c in classes):
            return element

    # Id-based heuristics
    for element in body.find_all(True):
        eid = element.get("id", "")
        if eid and "content" in eid.lower():
            return element

    return None


# ---------------------------------------------------------------------------
# Document processing (shared internals)
# ---------------------------------------------------------------------------

def _process_and_save(
    title: str,
    content: str,
    source_type: str = "web",
    source_url: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Generate a document dict, compute its SimHash, deduplicate, and persist.

    Parameters
    ----------
    title : str
        Document title.
    content : str
        Pre-cleaned text body.
    source_type : str
        Category label (``"web"``, ``"manual"``, ``"rss"``, etc.).
    source_url : str or None
        Original URL if applicable.
    tags : list[str] or None
        Optional tags to attach.

    Returns
    -------
    dict
        Document dict with an added ``status`` key:

        - ``"created"`` -- new document saved.
        - ``"duplicate"`` -- a similar document already exists (includes
          ``similarity`` float key).
        - ``"error"`` -- processing failed (includes ``error`` string).
    """
    doc_id = generate_doc_id(title, content, source_url)
    sh = compute_simhash(content)

    # ---- deduplication ------------------------------------------------
    if sh:
        similar_docs = db.find_similar_by_simhash(sh, threshold=settings.simhash_threshold)
        for candidate in similar_docs:
            if candidate["id"] != doc_id:
                similarity = simhash_similarity(sh, candidate["simhash"])
                logger.info(
                    "Duplicate: %r matches %r (similarity=%.3f)",
                    title, candidate["title"], similarity,
                )
                return {**candidate, "status": "duplicate", "similarity": similarity}

    # ---- persist ------------------------------------------------------
    now = datetime.now().isoformat()
    doc: dict = {
        "id": doc_id,
        "title": title,
        "content": content,
        "source_type": source_type,
        "source_url": source_url,
        "author": None,
        "tags": tags or [],
        "simhash": sh,
        "collected_at": now,
        "updated_at": now,
        "metadata": {},
    }

    try:
        db.insert_document(doc)
    except Exception:
        logger.exception("DB insert failed for %r", title)
        return {"status": "error", "error": "Database insert failed", "title": title}

    logger.info("Saved: %r  id=%s", title, doc_id)
    return {**doc, "status": "created"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def collect_url(url: str) -> dict:
    """Fetch *url*, extract text, deduplicate via SimHash, and persist.

    Uses :mod:`httpx` for asynchronous HTTP with a 30-second timeout and
    automatic redirect following.  Returns a document dict with a
    ``status`` key (see :func:`_process_and_save`).

    Parameters
    ----------
    url : str
        The web page URL to collect.

    Returns
    -------
    dict
        Document dict with ``status`` in ``{"created", "duplicate",
        "error"}``.
    """
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=_REQUEST_HEADERS)
            response.raise_for_status()
            html = response.text
        except httpx.TimeoutException:
            logger.error("Timeout fetching %s", url)
            return {"status": "error", "error": "Request timed out", "url": url}
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP %s fetching %s", exc.response.status_code, url)
            return {
                "status": "error",
                "error": f"HTTP {exc.response.status_code}",
                "url": url,
            }
        except httpx.RequestError as exc:
            logger.error("Request failed for %s: %s", url, exc)
            return {"status": "error", "error": str(exc), "url": url}

    title, content = extract_main_content(html, url)

    if not content:
        logger.warning("No extractable content from %s", url)
        return {
            "status": "error",
            "error": "No content extracted",
            "url": url,
            "title": title,
        }

    return _process_and_save(title, content, source_type="web", source_url=url)


def collect_text(
    title: str,
    text: str,
    source_type: str = "manual",
    source_url: Optional[str] = None,
) -> dict:
    """Ingest raw text as a document.

    Convenience entry point for notes, manual entries, or programmatic
    ingestion.  Performs the same deduplication and persistence pipeline
    as :func:`collect_url`.

    Parameters
    ----------
    title : str
        Human-readable title.
    text : str
        Raw text body (will be cleaned via :func:`~utils.clean_text`).
    source_type : str
        Category label.  Default ``"manual"``.
    source_url : str or None
        Optional reference URL.

    Returns
    -------
    dict
        Document dict with a ``status`` key.
    """
    content = clean_text(text)
    if not content:
        logger.warning("Empty text after cleaning (title=%r)", title)
        return {"status": "error", "error": "No content after cleaning", "title": title}

    return _process_and_save(
        title, content, source_type=source_type, source_url=source_url,
    )


async def poll_rss(feed_url: str) -> list[dict]:
    """Parse an RSS or Atom feed and collect every linked article.

    Uses :mod:`feedparser` for feed parsing and :func:`collect_url` for
    each entry's ``link``.  Entries without a link are silently skipped.

    The returned list contains one document dict per entry processed.
    Each dict carries a ``status`` key (``"created"``, ``"duplicate"``,
    or ``"error"``).

    Parameters
    ----------
    feed_url : str
        URL of the RSS or Atom feed.

    Returns
    -------
    list[dict]
        Collected document dicts.
    """
    # ---- parse feed --------------------------------------------------
    try:
        feed = feedparser.parse(feed_url)
    except Exception:
        logger.exception("Unhandled exception parsing feed %s", feed_url)
        return [{"status": "error", "error": "Feed parse exception", "feed_url": feed_url}]

    if feed.bozo and not feed.entries:
        logger.error(
            "Malformed feed %s: %s", feed_url, feed.bozo_exception,
        )
        return [{
            "status": "error",
            "error": str(feed.bozo_exception),
            "feed_url": feed_url,
        }]

    feed_title = feed.feed.get("title", feed_url)
    logger.info("Feed %r has %d entries", feed_title, len(feed.entries))

    # ---- collect entries ---------------------------------------------
    results: list[dict] = []
    for entry in feed.entries:
        link = entry.get("link")
        if not link:
            logger.debug("Skipping entry without link: %s", entry.get("title", "untitled"))
            continue

        logger.debug("Collecting: %s", link)
        doc = await collect_url(link)
        results.append(doc)

    # ---- summary -----------------------------------------------------
    created = sum(1 for r in results if r.get("status") == "created")
    dupes = sum(1 for r in results if r.get("status") == "duplicate")
    errors = sum(1 for r in results if r.get("status") == "error")
    logger.info(
        "Feed %r done: %d created, %d duplicates, %d errors",
        feed_url, created, dupes, errors,
    )

    return results

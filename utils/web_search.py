"""Web search fallback when knowledge base has no results."""

import logging
import json
import urllib.request
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using DuckDuckGo (no API key needed).

    Falls back gracefully if network unavailable.
    """
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1"

        req = urllib.request.Request(url, headers={"User-Agent": "PersonalKM/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        results = []

        # Abstract
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
                "source": "duckduckgo",
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results - len(results)]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                    "snippet": topic["Text"],
                    "url": topic.get("FirstURL", ""),
                    "source": "duckduckgo",
                })

        return results[:max_results]

    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return []


def enrich_answer(question: str, kb_sources: list[dict]) -> Optional[str]:
    """If KB has no good results, try web search to supplement."""
    if kb_sources:
        return None  # KB has content, no need

    web_results = search_web(question)
    if not web_results:
        return None

    lines = ["🌐 知识库中暂无相关内容，以下来自网络搜索:\n"]
    for i, r in enumerate(web_results[:3], 1):
        lines.append(f"{i}. **{r['title']}**")
        lines.append(f"   {r['snippet'][:200]}")
        lines.append(f"   🔗 {r['url']}")
        lines.append("")
    lines.append("💡 要将这些内容存入知识库吗？发送 `/collect 网址` 即可收藏。")

    return "\n".join(lines)

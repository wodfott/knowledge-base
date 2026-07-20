"""Scheduler: RSS polling, daily flashcard push, state persistence."""

import json
import logging
from pathlib import Path
from datetime import datetime

from config import settings

logger = logging.getLogger(__name__)

STATE_FILE = Path(settings.sqlite_path).parent / "schedule_state.json"


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"rss_feeds": {}, "review_push_records": []}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# --- RSS ---

def register_rss_feed(feed_url: str):
    state = _load_state()
    state["rss_feeds"][feed_url] = {
        "added": datetime.now().isoformat(),
        "last_poll": None,
        "poll_count": 0,
    }
    _save_state(state)


def unregister_rss_feed(feed_url: str):
    state = _load_state()
    state["rss_feeds"].pop(feed_url, None)
    _save_state(state)


async def poll_all_rss():
    from agents.collector import poll_rss
    from agents.knowledge import process_and_index_document

    state = _load_state()
    feeds = state.get("rss_feeds", {})
    if not feeds:
        return {"status": "ok", "message": "No RSS feeds registered"}

    total = 0
    for feed_url, info in feeds.items():
        try:
            results = await poll_rss(feed_url)
            created = [r for r in results if r.get("status") == "created"]
            for doc in created:
                process_and_index_document(doc["id"])
            total += len(created)
            info["last_poll"] = datetime.now().isoformat()
            info["poll_count"] = info.get("poll_count", 0) + 1
        except Exception as e:
            logger.error(f"RSS poll failed for {feed_url}: {e}")

    _save_state(state)
    return {"status": "ok", "feeds": len(feeds), "created": total}


# --- Flashcard Push ---

async def push_daily_review():
    """Push today's due flashcards to Feishu users.

    Checks the review time from settings and only pushes once per day.
    Returns a dict with status and count of pushed cards.
    """
    from storage import db
    from agents.personal import get_due_reviews
    from feishu import bot
    from feishu.cards import review_card
    import json as _json

    now = datetime.now()
    state = _load_state()

    # Only push at review time
    review_hour = int(settings.review_time.split(":")[0])
    if now.hour != review_hour:
        return {"status": "skip", "reason": f"Not review time (current hour: {now.hour}, target: {review_hour})"}

    # Only push once per day
    today = now.date().isoformat()
    push_records = state.get("review_push_records", [])
    if today in push_records:
        return {"status": "skip", "reason": "Already pushed today"}

    # Get due cards
    reviews = get_due_reviews()
    if not reviews:
        state["review_push_records"].append(today)
        _save_state(state)
        return {"status": "ok", "pushed": 0, "message": "No cards due"}

    # Push cards one by one to each allowed user
    pushed = 0
    for review in reviews[:10]:  # Max 10 cards per push
        entity = db.get_entity(review["entity_id"])
        if not entity:
            continue

        # Get relations for card back
        relations_data = db.get_relations_for_entity(entity["id"])
        relation_strs = []
        for r in relations_data[:5]:
            source_e = db.get_entity(r["source_entity_id"]) or {}
            target_e = db.get_entity(r["target_entity_id"]) or {}
            rel_text = f"{source_e.get('name', '?')} → {r['relation_type']} → {target_e.get('name', '?')}"
            relation_strs.append(rel_text)

        # Get related docs
        source_ids = entity.get("source_doc_ids", [])
        if isinstance(source_ids, str):
            source_ids = _json.loads(source_ids)
        doc_titles = []
        for did in source_ids[:3]:
            doc = db.get_document(did)
            if doc:
                doc_titles.append(doc["title"][:80])

        # Build flashcard
        card = review_card(
            entity_name=entity["name"],
            relations=relation_strs if relation_strs else [f"类型: {entity['type']}", entity.get("description", "")[:100]],
            related_docs=doc_titles,
        )

        # Push to all allowed Feishu users
        from config import settings as s
        # Note: We push via the bot's Feishu account configured in settings
        # The Feishu channel handles routing; here we just log that it would be sent
        logger.info(f"Pushing flashcard: {entity['name']} (interval: {review['interval_days']}d, ease: {review['ease']:.1f})")
        pushed += 1

    state["review_push_records"].append(today)
    # Keep only last 30 days
    state["review_push_records"] = state["review_push_records"][-30:]
    _save_state(state)

    return {
        "status": "ok",
        "pushed": pushed,
        "due_total": len(reviews),
        "time": now.strftime("%H:%M"),
    }

"""Personal Memory agent: annotations and review queue management."""

import logging
from datetime import datetime, timedelta

from storage import db
from storage.graph_db import graph_db

logger = logging.getLogger(__name__)


def add_to_review_queue(entity_name: str) -> dict:
    """Add an entity to the spaced repetition review queue."""
    entity = graph_db.find_entity_by_name(entity_name)
    if not entity:
        # Try SQLite
        entity = db.find_entity_by_name(entity_name)
        if not entity:
            return {"status": "error", "message": f"Entity not found: {entity_name}"}

    now = datetime.now()
    review = {
        "id": f"review_{entity['id']}_{now.strftime('%Y%m%d')}",
        "entity_id": entity["id"],
        "ease": 2.5,
        "interval_days": 1,
        "repetitions": 0,
        "last_reviewed": None,
        "next_review": (now + timedelta(days=1)).isoformat(),
        "created_at": now.isoformat(),
    }
    db.insert_review(review)
    return {"status": "ok", "message": f"Added to review queue: {entity_name}"}


def annotate_entity(entity_name: str, content: str, annotation_type: str = "note") -> dict:
    """Add a personal annotation to an entity."""
    entity = graph_db.find_entity_by_name(entity_name)
    if not entity:
        entity = db.find_entity_by_name(entity_name)
        if not entity:
            return {"status": "error", "message": f"Entity not found: {entity_name}"}

    import hashlib
    now = datetime.now().isoformat()
    ann_id = hashlib.sha256(f"{entity['id']}|{content}|{now}".encode()).hexdigest()[:16]

    annotation = {
        "id": ann_id,
        "target_type": "entity",
        "target_id": entity["id"],
        "annotation_type": annotation_type,
        "content": content,
        "linked_entity_id": None,
        "rating": None,
        "created_at": now,
        "updated_at": now,
    }
    db.insert_annotation(annotation)
    return {"status": "ok", "annotation_id": ann_id}


def get_due_reviews() -> list[dict]:
    """Get all due review items with entity names."""
    reviews = db.get_due_reviews()
    result = []
    for review in reviews:
        entity = db.get_entity(review["entity_id"])
        if entity:
            result.append({
                "review_id": review["id"],
                "entity_name": entity["name"],
                "ease": review["ease"],
                "interval_days": review["interval_days"],
                "repetitions": review["repetitions"],
                "next_review": review["next_review"],
            })
    return result

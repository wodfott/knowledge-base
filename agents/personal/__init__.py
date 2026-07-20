"""Personal Memory agent: SM-2 flashcards, annotations, review queue."""

import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from storage import db
from storage.graph_db import graph_db

logger = logging.getLogger(__name__)


# --- SM-2 Spaced Repetition Algorithm ---

def sm2_quality_to_params(quality: int, current: dict) -> dict:
    """Apply SM-2 algorithm: update ease, interval, and next review date.

    Quality scale:
      0 - Complete blackout
      1 - Incorrect, but answer remembered upon seeing it
      2 - Incorrect, but answer seemed easy to recall
      3 - Correct with serious difficulty
      4 - Correct after hesitation
      5 - Perfect response
    """
    now = datetime.now()

    if quality < 3:
        # Failed: reset repetitions, short interval
        current["repetitions"] = 0
        current["interval_days"] = 1
        current["ease"] = max(1.3, current["ease"] - 0.2)
    else:
        # Passed
        if current["repetitions"] == 0:
            current["interval_days"] = 1
        elif current["repetitions"] == 1:
            current["interval_days"] = 3
        else:
            current["interval_days"] = int(current["interval_days"] * current["ease"])

        current["repetitions"] += 1
        # Adjust ease
        current["ease"] = current["ease"] + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        current["ease"] = max(1.3, current["ease"])

    current["interval_days"] = max(1, min(current["interval_days"], 365))
    current["last_reviewed"] = now.isoformat()
    current["next_review"] = (now + timedelta(days=current["interval_days"])).isoformat()

    return current


# --- Flashcard Management ---

def create_flashcard(entity_name: str) -> dict:
    """Create a flashcard from a knowledge graph entity, with LLM-generated QA."""
    entity = graph_db.find_entity_by_name(entity_name)
    if not entity:
        entity = db.find_entity_by_name(entity_name)
    if not entity:
        return {"status": "error", "message": f"Entity not found: {entity_name}"}

    entity_id = entity["id"]
    entity_type = entity.get("type", "Other")
    description = entity.get("description", "")

    # Check if already in review queue
    import sqlite3, json
    try:
        conn = sqlite3.connect(db.db_path)
        row = conn.execute("SELECT 1 FROM review_records WHERE entity_id = ?", (entity_id,)).fetchone()
        conn.close()
        if row:
            return {"status": "duplicate", "message": f"已在复习队列中: {entity_name}"}
    except Exception:
        pass

    # Gather context for LLM to generate flashcard
    context_parts = [description]
    # Get relations
    relations = graph_db.get_neighbors(entity_id, max_depth=1)
    for n in relations.get("neighbors", [])[:5]:
        rel = n.get("relation", {})
        context_parts.append(
            f"关系 {rel.get('type', '')}: {n.get('name', '')} [{n.get('type', '')}]"
        )
    # Get related document content snippets
    source_doc_ids = entity.get("source_doc_ids", "[]")
    if isinstance(source_doc_ids, str):
        try:
            source_doc_ids = json.loads(source_doc_ids)
        except (json.JSONDecodeError, TypeError):
            source_doc_ids = []
    for doc_id in source_doc_ids[:2]:
        doc = db.get_document(doc_id)
        if doc:
            context_parts.append(doc["content"][:500])

    context = "\n\n".join(context_parts)

    # Generate QA with LLM
    question, answer, hint = "", "", ""
    try:
        from utils.llm import llm_client
        qa = llm_client.generate_flashcard_qa(
            entity_name=entity_name,
            entity_type=entity_type,
            description=description,
            context=context,
        )
        question = qa.get("front", "")
        answer = qa.get("back", "")
        hint = qa.get("hint", "")
        logger.info(f"Generated flashcard QA for: {entity_name}")
    except Exception as e:
        logger.warning(f"LLM flashcard generation failed, using fallback: {e}")
        # Fallback: simple question from entity info
        question = f"请简述 {entity_name} 是什么，以及它的主要特点。"
        answer = description or f"{entity_name} 是一个 {entity_type} 类型的知识实体。"
        hint = entity_type

    now = datetime.now()
    review = {
        "id": f"review_{entity_id}_{now.strftime('%Y%m%d%H%M')}",
        "entity_id": entity_id,
        "ease": 2.5,
        "interval_days": 1,
        "repetitions": 0,
        "last_reviewed": None,
        "next_review": now.isoformat(),  # Due immediately
        "created_at": now.isoformat(),
        "question": question,
        "answer": answer,
        "hint": hint,
    }
    db.insert_review(review)
    logger.info(f"Flashcard created: {entity_name}")
    return {
        "status": "ok",
        "review": review,
        "entity_name": entity_name,
        "question": question,
        "answer": answer,
    }


def create_flashcards_batch(entity_names: list[str]) -> dict:
    """Create flashcards for multiple entities."""
    results = []
    for name in entity_names:
        r = create_flashcard(name)
        results.append({"entity": name, **r})
    return {
        "total": len(results),
        "created": sum(1 for r in results if r["status"] == "ok"),
        "duplicate": sum(1 for r in results if r["status"] == "duplicate"),
        "error": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }


def create_flashcards_from_doc(doc_id: str) -> dict:
    """Create flashcards for all entities mentioned in a document."""
    doc = db.get_document(doc_id)
    if not doc:
        return {"status": "error", "message": f"Document not found: {doc_id}"}

    import json
    entities = db.list_entities(limit=200)
    # Filter entities that reference this doc
    doc_entities = []
    for e in entities:
        source_ids = e.get("source_doc_ids", [])
        if isinstance(source_ids, str):
            source_ids = json.loads(source_ids)
        if doc_id in source_ids:
            doc_entities.append(e["name"])

    if not doc_entities:
        return {"status": "ok", "created": 0, "message": "No entities for this document"}

    return create_flashcards_batch(doc_entities)


def get_review_stats() -> dict:
    """Get flashcard review statistics."""
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) as c FROM review_records").fetchone()["c"]
    due = conn.execute(
        "SELECT COUNT(*) as c FROM review_records WHERE next_review <= ?",
        (datetime.now().isoformat(),)
    ).fetchone()["c"]
    reviewed = conn.execute(
        "SELECT COUNT(*) as c FROM review_records WHERE repetitions > 0"
    ).fetchone()["c"]
    avg_ease = conn.execute(
        "SELECT AVG(ease) as c FROM review_records WHERE repetitions > 0"
    ).fetchone()["c"] or 2.5
    avg_interval = conn.execute(
        "SELECT AVG(interval_days) as c FROM review_records WHERE repetitions > 0"
    ).fetchone()["c"] or 0

    # Today's stats
    today = datetime.now().date().isoformat()
    today_reviewed = conn.execute(
        "SELECT COUNT(*) as c FROM review_records WHERE last_reviewed LIKE ?",
        (f"{today}%",)
    ).fetchone()["c"]

    conn.close()

    return {
        "total_cards": total,
        "due_today": due,
        "reviewed_total": reviewed,
        "reviewed_today": today_reviewed,
        "avg_ease": round(avg_ease, 2),
        "avg_interval_days": round(avg_interval, 1),
    }


def review_flashcard(entity_name: str, quality: int) -> dict:
    """Review a flashcard with SM-2 quality rating (0-5)."""
    entity = graph_db.find_entity_by_name(entity_name)
    if not entity:
        entity = db.find_entity_by_name(entity_name)
    if not entity:
        return {"status": "error", "message": f"Entity not found: {entity_name}"}

    entity_id = entity["id"]

    # Find the review record
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM review_records WHERE entity_id = ? ORDER BY next_review ASC LIMIT 1",
        (entity_id,)
    ).fetchone()
    conn.close()

    if not row:
        # Auto-create one
        create_flashcard(entity_name)
        return review_flashcard(entity_name, quality)

    review = dict(row)
    quality = max(0, min(5, quality))
    updated = sm2_quality_to_params(quality, review)
    db.insert_review(updated)

    q_labels = {0: "完全忘了", 1: "有印象但不记得", 2: "模糊记得", 3: "努力后想起", 4: "犹豫后想起", 5: "完美回忆"}
    return {
        "status": "ok",
        "entity": entity_name,
        "quality": quality,
        "quality_label": q_labels.get(quality, ""),
        "next_review": updated["next_review"],
        "interval_days": updated["interval_days"],
        "ease": round(updated["ease"], 2),
        "repetitions": updated["repetitions"],
    }


# --- Legacy functions for backward compatibility ---

def add_to_review_queue(entity_name: str) -> dict:
    return create_flashcard(entity_name)


def annotate_entity(entity_name: str, content: str, annotation_type: str = "note") -> dict:
    """Add a personal annotation to an entity."""
    entity = graph_db.find_entity_by_name(entity_name)
    if not entity:
        entity = db.find_entity_by_name(entity_name)
        if not entity:
            return {"status": "error", "message": f"Entity not found: {entity_name}"}

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
    """Get all due review items with entity names and QA content."""
    reviews = db.get_due_reviews()
    result = []
    for review in reviews:
        entity = db.get_entity(review["entity_id"])
        if entity:
            result.append({
                "review_id": review["id"],
                "entity_id": entity["id"],
                "entity_name": entity["name"],
                "entity_type": entity["type"],
                "ease": review["ease"],
                "interval_days": review["interval_days"],
                "repetitions": review["repetitions"],
                "last_reviewed": review.get("last_reviewed"),
                "next_review": review["next_review"],
                "question": review.get("question", ""),
                "answer": review.get("answer", ""),
                "hint": review.get("hint", ""),
            })
    return result

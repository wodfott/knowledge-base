"""Personal Memory API — flashcards, annotations, reviews."""

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agents.personal import (
    create_flashcard, create_flashcards_batch, create_flashcards_from_doc,
    review_flashcard, get_review_stats, get_due_reviews,
    annotate_entity,
)
from storage.graph_db import graph_db
from storage import db as sdb

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/personal", tags=["Personal Memory"])


class AnnotateRequest(BaseModel):
    entity_name: str
    content: str
    annotation_type: str = "note"


class ReviewRequest(BaseModel):
    entity_name: str


class BatchCreateRequest(BaseModel):
    entity_names: list[str]


# --- Flashcards ---

@router.post("/flashcard/create")
async def api_create_flashcard(entity_name: str = Query(...)):
    """Create a flashcard for an entity."""
    result = create_flashcard(entity_name)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.post("/flashcard/batch")
async def api_batch_flashcards(req: BatchCreateRequest):
    """Create flashcards for multiple entities."""
    return create_flashcards_batch(req.entity_names)


@router.post("/flashcard/from-doc")
async def api_flashcards_from_doc(doc_id: str = Query(...)):
    """Create flashcards for all entities in a document."""
    result = create_flashcards_from_doc(doc_id)
    return result


@router.post("/flashcard/review")
async def api_review_flashcard(
    entity_name: str = Query(...),
    quality: int = Query(..., ge=0, le=5, description="SM-2 quality: 0=blackout, 5=perfect"),
):
    """Review a flashcard with SM-2 quality rating."""
    result = review_flashcard(entity_name, quality)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.get("/flashcard/stats")
async def api_flashcard_stats():
    """Get flashcard review statistics."""
    return get_review_stats()


@router.get("/flashcard/due")
async def api_flashcards_due():
    """Get today's due flashcards."""
    reviews = get_due_reviews()
    return {"count": len(reviews), "cards": reviews}


# --- Annotations ---

@router.post("/annotate")
async def api_annotate(req: AnnotateRequest):
    """Add a personal annotation to an entity."""
    result = annotate_entity(req.entity_name, req.content, req.annotation_type)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.get("/annotations")
async def api_annotations(entity_name: str = Query(None)):
    """Get annotations for an entity or all recent."""
    if entity_name:
        entity = graph_db.find_entity_by_name(entity_name)
        if not entity:
            entity = sdb.find_entity_by_name(entity_name)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity not found: {entity_name}")
        annotations = sdb.get_annotations("entity", entity["id"])
        return {"entity": entity_name, "count": len(annotations), "annotations": annotations}

    # All recent
    entities = sdb.list_entities(limit=50)
    all_anns = []
    for e in entities:
        anns = sdb.get_annotations("entity", e["id"])
        for a in anns:
            a["entity_name"] = e["name"]
        all_anns.extend(anns)
    all_anns.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"count": len(all_anns[:50]), "annotations": all_anns[:50]}


# --- Quick review for Feishu cards ---

@router.post("/review-quick")
async def api_review_quick(
    entity_name: str = Query(...),
    grade: str = Query("easy", pattern="^(easy|hard|skip)$"),
):
    """Quick review via Feishu card buttons."""
    q_map = {"easy": 5, "hard": 3, "skip": 0}
    quality = q_map.get(grade, 5)
    result = review_flashcard(entity_name, quality)
    return result

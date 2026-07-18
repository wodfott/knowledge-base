"""Review and recap API endpoints."""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException

from models.api import RecapRequest, RecapResponse, ReviewDueResponse
from storage import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Review & Recap"])


@router.get("/review/due", response_model=ReviewDueResponse)
async def api_review_due():
    """Get today's due review items."""
    reviews = db.get_due_reviews()
    items = []
    for review in reviews:
        entity = db.get_entity(review["entity_id"])
        if entity:
            items.append({
                "review_id": review["id"],
                "entity_id": entity["id"],
                "entity_name": entity["name"],
                "entity_type": entity["type"],
                "ease": review["ease"],
                "interval_days": review["interval_days"],
                "repetitions": review["repetitions"],
                "last_reviewed": review.get("last_reviewed"),
                "next_review": review["next_review"],
            })

    return ReviewDueResponse(reviews=items, count=len(items))


@router.post("/recap", response_model=RecapResponse)
async def api_recap(req: RecapRequest):
    """Generate a knowledge recap for a time period."""
    now = datetime.now()
    if req.period == "90d":
        since = (now - timedelta(days=90)).isoformat()
    elif req.period == "30d":
        since = (now - timedelta(days=30)).isoformat()
    else:
        since = (now - timedelta(days=7)).isoformat()

    stats = db.get_stats(since=since)
    entities = db.list_entities(limit=10)
    top_names = [e["name"] for e in entities[:5]]

    return RecapResponse(
        period=req.period,
        new_documents=stats["documents"],
        new_entities=stats["entities"],
        new_relations=stats["relations"],
        top_entities=top_names,
        summary=f"In the past {req.period}: {stats['documents']} docs, {stats['entities']} entities, {stats['relations']} relations",
    )


@router.get("/export")
async def api_export():
    """Export all data as JSON-compatible dict."""
    from storage.graph_db import graph_db

    documents = db.list_documents(limit=10000)
    entities = db.list_entities(limit=10000)
    graph_entities = graph_db.get_all_entities()
    graph_relations = graph_db.get_all_relations()

    return {
        "exported_at": datetime.now().isoformat(),
        "counts": {
            "documents": len(documents),
            "entities_sql": len(entities),
            "entities_graph": len(graph_entities),
            "relations": len(graph_relations),
        },
        "documents": documents,
        "entities": entities,
        "graph_entities": graph_entities,
        "graph_relations": graph_relations,
    }


@router.get("/health")
async def api_health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "stats": db.get_stats(),
    }

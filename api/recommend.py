"""Recommend API endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Query

from agents.recommend import recommend_similar, recommend_learning_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommend", tags=["Recommend"])


@router.get("/similar")
async def api_recommend_similar(
    entity: str = Query(..., description="Entity name"),
    top_k: int = Query(default=5, ge=1, le=20),
):
    """Get similar entities by embedding similarity."""
    results = recommend_similar(entity, top_k=top_k)
    return {
        "entity": entity,
        "count": len(results),
        "recommendations": results,
    }


@router.get("/learning-path")
async def api_learning_path(
    entity: str = Query(..., description="Starting entity name"),
    max_depth: int = Query(default=2, ge=1, le=3),
):
    """Get a learning path via graph traversal."""
    path = recommend_learning_path(entity, max_depth=max_depth)
    return {
        "entity": entity,
        "depth": max_depth,
        "path": path,
    }


@router.get("/latest")
async def api_latest_docs(
    limit: int = Query(default=10, ge=1, le=50),
):
    """Get recently collected documents."""
    from storage import db
    docs = db.list_documents(limit=limit)
    return {
        "count": len(docs),
        "documents": [
            {"id": d["id"], "title": d["title"], "source_type": d["source_type"],
             "collected_at": d["collected_at"], "tags": d.get("tags", [])}
            for d in docs
        ],
    }

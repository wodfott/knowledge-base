"""Collection API endpoints."""

import logging
from fastapi import APIRouter, HTTPException

from models.api import CollectRequest, CollectResponse
from agents.collector import collect_url, collect_text, poll_rss
from agents.knowledge import process_and_index_document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/collect", tags=["Collection"])


@router.post("/url", response_model=CollectResponse)
async def api_collect_url(req: CollectRequest):
    """Collect content from a URL."""
    if not req.url:
        raise HTTPException(status_code=400, detail="url is required")

    result = await collect_url(req.url)

    if result["status"] == "created":
        process_and_index_document(result["id"])
        return CollectResponse(
            status="ok",
            doc_id=result["id"],
            message=f"Collected and indexed: {result.get('title', '')}",
        )
    elif result["status"] == "duplicate":
        return CollectResponse(status="duplicate", message="Document already exists")
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Collection failed"))


@router.post("/text", response_model=CollectResponse)
async def api_collect_text(req: CollectRequest):
    """Collect plain text content."""
    if not req.text:
        raise HTTPException(status_code=400, detail="text is required")

    result = collect_text(
        title=req.title or "Untitled",
        text=req.text,
        source_type=req.source_type,
    )

    if result["status"] == "created":
        process_and_index_document(result["id"])
        return CollectResponse(
            status="ok",
            doc_id=result["id"],
            message="Text collected and indexed",
        )
    elif result["status"] == "duplicate":
        return CollectResponse(status="duplicate", message="Content already exists")
    else:
        raise HTTPException(status_code=500, detail=result.get("message", ""))


@router.post("/rss", response_model=CollectResponse)
async def api_poll_rss(req: CollectRequest):
    """Poll an RSS feed."""
    if not req.rss_feed_url:
        raise HTTPException(status_code=400, detail="rss_feed_url is required")

    results = await poll_rss(req.rss_feed_url)
    created = [r for r in results if r.get("status") == "created"]
    errors = [r for r in results if r.get("status") == "error"]

    # Index new documents
    for doc in created:
        process_and_index_document(doc["id"])

    return CollectResponse(
        status="ok",
        message=f"Processed {len(results)} entries: {len(created)} new, {len(errors)} errors",
    )

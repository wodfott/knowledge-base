"""Q&A API endpoints."""

import logging
from fastapi import APIRouter, HTTPException

from models.api import QARequest, QAResponse, FeedbackRequest
from agents.qa import answer
from storage import db
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/qa", tags=["Q&A"])


@router.post("/ask", response_model=QAResponse)
async def api_ask(req: QARequest):
    """Ask a question based on the knowledge base."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    result = answer(
        question=req.question,
        session_id=req.session_id,
        top_k=req.top_k,
    )

    return QAResponse(
        answer=result["answer"],
        sources=result["sources"],
        cached=result.get("cached", False),
        session_id=result.get("session_id"),
    )


@router.post("/feedback")
async def api_feedback(req: FeedbackRequest):
    """Record feedback on an answer."""
    if req.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")

    import hashlib
    fb_id = hashlib.sha256(f"{req.query_id}|{req.rating}|{datetime.now().isoformat()}".encode()).hexdigest()[:16]

    db.insert_feedback({
        "id": fb_id,
        "query_id": req.query_id,
        "rating": req.rating,
        "comment": req.comment,
        "created_at": datetime.now().isoformat(),
    })

    return {"status": "ok"}

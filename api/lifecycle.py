"""Knowledge Lifecycle API endpoints."""

import logging
from fastapi import APIRouter, Query

from agents.lifecycle import check_stale_entities, get_cluster_new_content

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lifecycle", tags=["Lifecycle"])


@router.get("/stale")
async def api_stale_entities(
    days: int = Query(default=90, ge=7, le=365, description="Days threshold for staleness"),
):
    """Get entities that haven't been accessed recently."""
    stale = check_stale_entities(days_threshold=days)
    return {
        "threshold_days": days,
        "count": len(stale),
        "stale_entities": stale,
    }


@router.get("/cluster-updates")
async def api_cluster_updates(
    entity: str = Query(..., description="Entity name"),
    days: int = Query(default=30, ge=1, le=180),
):
    """Check for new content in an entity cluster."""
    updates = get_cluster_new_content(entity, days=days)
    return {
        "entity": entity,
        "days": days,
        "new_content": updates,
    }

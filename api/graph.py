"""Graph query API endpoints."""

import logging
from fastapi import APIRouter, HTTPException

from models.api import GraphQueryRequest, GraphQueryResponse, EntityResult, RelationResult
from agents.qa import generate_entity_card
from storage.graph_db import graph_db
from storage import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["Graph"])


@router.post("/query", response_model=GraphQueryResponse)
async def api_graph_query(req: GraphQueryRequest):
    """Query entity in knowledge graph."""
    entity_name = req.entity_name
    entity_id = req.entity_id

    if not entity_name and not entity_id:
        raise HTTPException(status_code=400, detail="entity_name or entity_id required")

    # Resolve entity
    if entity_id:
        entity = graph_db.get_entity(entity_id)
        if entity:
            entity_name = entity.get("name", entity_id)
    elif entity_name:
        entity = graph_db.find_entity_by_name(entity_name)
        if entity:
            entity_id = entity["id"]

    if not entity_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    result = generate_entity_card(entity_name)

    if not result["found"]:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_name}")

    # Build response
    entity_data = result["entity"]
    entity_result = EntityResult(
        id=entity_data["id"],
        name=entity_data["name"],
        type=entity_data["type"],
        description=entity_data.get("description"),
        confidence=entity_data.get("confidence", 1.0),
        relations=[
            RelationResult(
                id=f"rel_{i}",
                relation_type=r["relation_type"],
                source_name=entity_data["name"] if r.get("direction") == "outgoing" else r["target_name"],
                target_name=r["target_name"] if r.get("direction") == "outgoing" else entity_data["name"],
                confidence=r.get("confidence", 1.0),
            )
            for i, r in enumerate(result.get("relations", []))
        ],
    )

    neighbors = []
    if entity_id:
        neighbors_data = graph_db.get_neighbors(entity_id, max_depth=req.max_depth)
        for n in neighbors_data.get("neighbors", []):
            n_relations = [
                RelationResult(
                    id=f"nrel_{i}",
                    relation_type=n.get("relation", {}).get("type", "related_to"),
                    source_name=entity_name,
                    target_name=n.get("name", ""),
                    confidence=n.get("relation", {}).get("confidence", 1.0),
                )
                for i in [0]  # One relation per neighbor in summary
            ]
            neighbors.append(EntityResult(
                id=n["id"],
                name=n.get("name", ""),
                type=n.get("type", ""),
                confidence=1.0,
                relations=n_relations,
            ))

    return GraphQueryResponse(
        entity=entity_result,
        neighbors=neighbors[:10],
        text_tree=result.get("text_tree", ""),
    )


@router.get("/search")
async def api_graph_search(q: str = "", limit: int = 10):
    """Search entities by name."""
    results = graph_db.search_entities(q, max_results=limit)
    return {
        "query": q,
        "count": len(results),
        "entities": [
            {
                "id": r["id"],
                "name": r.get("name", ""),
                "type": r.get("type", ""),
                "description": r.get("description", ""),
            }
            for r in results
        ],
    }


@router.get("/full")
async def api_graph_full(limit: int = 5000):
    """Return all entities and relations for full graph overview."""
    all_entities = graph_db.get_all_entities()
    all_relations = graph_db.get_all_relations()

    # Build node list
    nodes = []
    seen = set()
    for e in all_entities[:limit]:
        if e["id"] not in seen:
            seen.add(e["id"])
            nodes.append({
                "id": e["id"],
                "name": e.get("name", ""),
                "type": e.get("type", "Other"),
                "description": e.get("description", ""),
            })

    # Build link list
    links = []
    for r in all_relations:
        if r["source"] in seen and r["target"] in seen:
            links.append({
                "source": r["source"],
                "target": r["target"],
                "type": r.get("type", "related_to"),
                "confidence": r.get("confidence", 1.0),
            })

    return {
        "nodes": nodes,
        "links": links[:500],
        "counts": {
            "total_entities": len(all_entities),
            "total_relations": len(all_relations),
            "shown_entities": len(nodes),
            "shown_relations": len(links[:limit]),
        },
    }

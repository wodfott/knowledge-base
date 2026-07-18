"""Recommend agent: content-based and graph-path recommendations."""

import logging
from datetime import datetime

from storage import db
from storage.graph_db import graph_db
from utils.embedding import embedding_client

logger = logging.getLogger(__name__)


def recommend_similar(entity_name: str, top_k: int = 5) -> list[dict]:
    """Recommend similar entities based on embedding cosine similarity."""
    entity = graph_db.find_entity_by_name(entity_name)
    if not entity:
        return []

    entity_text = f"{entity.get('name', '')} {entity.get('description', '')}"
    entity_emb = embedding_client.embed_single(entity_text)

    all_entities = graph_db.get_all_entities()
    scored = []
    for e in all_entities:
        if e["id"] == entity["id"]:
            continue
        e_text = f"{e.get('name', '')} {e.get('description', '')}"
        e_emb = embedding_client.embed_single(e_text)
        score = embedding_client.cosine_similarity(entity_emb, e_emb)
        scored.append({"entity": e, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return [
        {"name": s["entity"].get("name"), "type": s["entity"].get("type"), "similarity": round(s["score"], 3)}
        for s in scored[:top_k]
    ]


def recommend_learning_path(entity_name: str, max_depth: int = 2) -> list[dict]:
    """Recommend a learning path via graph traversal."""
    entity = graph_db.find_entity_by_name(entity_name)
    if not entity:
        return []

    neighbors = graph_db.get_neighbors(entity["id"], max_depth=max_depth)
    path = []
    visited = {entity["id"]}

    for n in neighbors.get("neighbors", []):
        if n["id"] not in visited:
            path.append({
                "name": n.get("name"),
                "type": n.get("type"),
                "relation": n.get("relation", {}).get("type"),
                "direction": n.get("relation", {}).get("direction"),
            })
            visited.add(n["id"])

    return path

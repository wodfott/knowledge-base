"""Knowledge Lifecycle agent: stale detection and maintenance prompts."""

import logging
from datetime import datetime, timedelta

from storage import db
from storage.graph_db import graph_db

logger = logging.getLogger(__name__)


def check_stale_entities(days_threshold: int = 90) -> list[dict]:
    """Find entities that haven't been accessed in days_threshold days."""
    now = datetime.now()
    threshold = (now - timedelta(days=days_threshold)).isoformat()
    stale = []

    entities = graph_db.get_all_entities()
    for entity in entities:
        last_access = entity.get("last_access", "")
        if last_access and last_access < threshold:
            stale.append({
                "id": entity["id"],
                "name": entity.get("name", ""),
                "type": entity.get("type", ""),
                "last_access": last_access,
                "days_stale": (now - datetime.fromisoformat(last_access)).days,
            })

    stale.sort(key=lambda x: x["days_stale"], reverse=True)
    return stale[:20]


def touch_entity(entity_id: str):
    """Update the last_access timestamp of an entity."""
    entity = db.get_entity(entity_id)
    if entity:
        entity["last_access"] = datetime.now().isoformat()
        db.insert_entity(entity)

    if graph_db.has_entity(entity_id):
        graph_data = graph_db.get_entity(entity_id)
        if graph_data:
            graph_db.add_entity(
                entity_id=entity_id,
                name=graph_data.get("name", ""),
                entity_type=graph_data.get("type", ""),
                description=graph_data.get("description"),
                confidence=graph_data.get("confidence", 1.0),
                source_doc_ids=graph_data.get("source_doc_ids", "[]"),
                last_access=datetime.now().isoformat(),
            )


def get_cluster_new_content(entity_name: str, days: int = 30) -> list[dict]:
    """Check for new content related to an entity cluster since last visit."""
    entity = graph_db.find_entity_by_name(entity_name)
    if not entity:
        return []

    since = (datetime.now() - timedelta(days=days)).isoformat()
    neighbors = graph_db.get_neighbors(entity["id"], max_depth=1)

    # Check recent documents mentioning neighbor entities
    new_docs = []
    checked_entities = {entity["id"]}
    for n in neighbors.get("neighbors", []):
        if n["id"] not in checked_entities:
            checked_entities.add(n["id"])
            docs = db.list_documents(limit=5)
            for doc in docs:
                if doc.get("collected_at", "") > since:
                    new_docs.append({
                        "entity": n.get("name", ""),
                        "doc_title": doc["title"],
                        "collected_at": doc["collected_at"],
                    })

    return new_docs

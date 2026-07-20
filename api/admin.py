"""Admin dashboard API — aggregated stats, document detail, graph rebuild."""

import json as _json
import logging
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from config import settings
from storage import db
from storage.graph_db import graph_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"])


@router.get("/dashboard")
async def api_dashboard():
    """Return aggregated data for the admin dashboard."""
    stats = db.get_stats()

    # Due reviews
    due_reviews_raw = db.get_due_reviews()
    due_reviews = []
    for r in due_reviews_raw:
        entity = db.get_entity(r["entity_id"])
        due_reviews.append({
            "review_id": r["id"],
            "entity_id": r["entity_id"],
            "entity_name": entity["name"] if entity else "(deleted)",
            "entity_type": entity["type"] if entity else "unknown",
            "ease": r["ease"],
            "interval_days": r["interval_days"],
            "repetitions": r["repetitions"],
            "last_reviewed": r.get("last_reviewed"),
            "next_review": r["next_review"],
            "question": r.get("question", ""),
            "answer": r.get("answer", ""),
            "hint": r.get("hint", ""),
        })

    # Recent documents
    recent_docs_raw = db.list_documents(limit=50)
    recent_docs = []
    for d in recent_docs_raw:
        text = d.get("content", "")
        preview = text[:120].replace("\n", " ") + ("…" if len(text) > 120 else "")
        recent_docs.append({
            "id": d["id"], "title": d["title"], "source_type": d["source_type"],
            "source_url": d.get("source_url"), "collected_at": d["collected_at"],
            "tags": d.get("tags", []), "preview": preview,
        })

    # Entity type distribution
    entities = db.list_entities(limit=5000)
    entity_types = {}
    for e in entities:
        t = e.get("type", "Unknown")
        entity_types[t] = entity_types.get(t, 0) + 1
    entity_types_sorted = sorted(entity_types.items(), key=lambda x: x[1], reverse=True)

    # Source type distribution
    docs_all = db.list_documents(limit=5000)
    source_types = {}
    for d in docs_all:
        st = d.get("source_type", "unknown")
        source_types[st] = source_types.get(st, 0) + 1
    source_types_sorted = sorted(source_types.items(), key=lambda x: x[1], reverse=True)

    # Docs timeline (14 days)
    docs_by_day = {}
    for d in docs_all:
        date = d.get("collected_at", "")[:10]
        if date:
            docs_by_day[date] = docs_by_day.get(date, 0) + 1
    docs_timeline = sorted(docs_by_day.items())[-14:]

    # Annotations
    all_annotations = 0
    for e in entities[:50]:
        all_annotations += len(db.get_annotations("entity", e["id"]))

    # Lifecycle: stale entities
    from agents.lifecycle import check_stale_entities
    stale_raw = check_stale_entities(days_threshold=90)

    # Recommend: spotlight
    from agents.recommend import recommend_similar as rec_similar
    top_entities_for_rec = [e for e in entities[:3] if e.get("name")]
    spotlight_recs = []
    for e in top_entities_for_rec:
        try:
            similar = rec_similar(e["name"], top_k=3)
            if similar:
                spotlight_recs.append({"entity": e["name"], "type": e.get("type", ""), "similar": similar})
        except Exception:
            pass

    return {
        "stats": {"documents": stats["documents"], "entities": stats["entities"],
                   "relations": stats["relations"], "annotations": all_annotations},
        "due_reviews": {"count": len(due_reviews), "items": due_reviews[:20]},
        "recent_docs": recent_docs,
        "entity_types": dict(entity_types_sorted),
        "source_types": dict(source_types_sorted),
        "docs_timeline": dict(docs_timeline),
        "lifecycle": {"stale_count": len(stale_raw), "stale_entities": stale_raw[:10]},
        "recommend": {"spotlight": spotlight_recs},
        "system": {
            "llm_model": settings.deepseek_chat_model, "embed_model": settings.deepseek_embed_model,
            "graph_db": settings.graph_db_path, "sqlite": settings.sqlite_path,
            "vector_db": settings.vector_db_path, "debug": settings.debug,
        },
        "generated_at": datetime.now().isoformat(),
    }


@router.get("/document/{doc_id}")
async def api_get_document(doc_id: str):
    """Get a single document with full content."""
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = db.get_chunks_by_doc(doc_id)

    # Find linked entities
    all_entities = db.list_entities(limit=5000)
    linked_entities = []
    for e in all_entities:
        source_docs = e.get("source_doc_ids", [])
        if isinstance(source_docs, str):
            try:
                source_docs = _json.loads(source_docs)
            except (_json.JSONDecodeError, TypeError):
                source_docs = []
        if doc_id in source_docs:
            linked_entities.append({"id": e["id"], "name": e["name"], "type": e["type"]})

    return {
        "id": doc["id"], "title": doc["title"], "content": doc["content"],
        "source_type": doc["source_type"], "source_url": doc.get("source_url"),
        "author": doc.get("author"), "tags": doc.get("tags", []),
        "collected_at": doc["collected_at"], "updated_at": doc["updated_at"],
        "chunks": [{"index": c["chunk_index"], "content": c["content"], "tokens": c.get("token_count", 0)} for c in chunks],
        "entities": linked_entities,
    }


class DocUpdateRequest(BaseModel):
    title: str = ""
    content: str = ""


@router.delete("/document/{doc_id}")
async def api_delete_document(doc_id: str):
    """Delete a document and clean up related data."""
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    title = doc["title"]

    # 1. Remove from BM25 index
    from utils.retriever import bm25_retriever
    bm25_retriever.delete_by_doc(doc_id)

    # 1.5 Clear semantic cache (cached answers may reference deleted doc)
    from utils.cache import semantic_cache
    semantic_cache.clear()

    # 2. Remove entity associations
    removed_entities = db.delete_entities_for_doc(doc_id)

    # 3. Remove from SQLite
    db.delete_document(doc_id)

    logger.info(f"Deleted document: {title} (id={doc_id}), removed {removed_entities} orphaned entities")
    return {"status": "ok", "deleted": doc_id, "title": title, "removed_entities": removed_entities}


@router.put("/document/{doc_id}")
async def api_update_document(doc_id: str, req: DocUpdateRequest):
    """Update a document's title and/or content. Re-indexes if content changed."""
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    updated = db.update_document(doc_id, title=req.title, content=req.content)

    if req.content:
        # Re-chunk and re-index
        from utils.retriever import bm25_retriever
        bm25_retriever.delete_by_doc(doc_id)
        from utils import chunk_text
        chunks = chunk_text(req.content, chunk_size=500, overlap=50)
        chunk_records = []
        for i, chunk_text_content in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            chunk_records.append({
                "id": chunk_id, "doc_id": doc_id, "chunk_index": i,
                "content": chunk_text_content, "title": req.title or doc["title"],
                "token_count": len(chunk_text_content),
            })
        db.insert_chunks(chunk_records)
        bm25_retriever.add(chunk_records)

    return {"status": "ok", "updated": updated}


@router.post("/clear-cache")
async def api_clear_cache():
    """Clear the semantic QA cache."""
    from utils.cache import semantic_cache
    before = semantic_cache.size
    semantic_cache.clear()
    return {"status": "ok", "cleared": before}


@router.post("/rebuild-graph")
async def api_rebuild_graph():
    """Rebuild graph DB entirely from SQLite — clears stale first."""
    graph_db.clear()
    entities = db.list_entities(limit=50000)
    synced_e, synced_r = 0, 0

    # Sync entities
    for ent in entities:
        sds = ent.get("source_doc_ids", [])
        if isinstance(sds, str):
            try:
                sds = _json.loads(sds)
            except (_json.JSONDecodeError, TypeError):
                sds = []
        graph_db.add_entity(
            entity_id=ent["id"], name=ent["name"], entity_type=ent.get("type", "Other"),
            description=ent.get("description", ""), confidence=ent.get("confidence", 1.0),
            source_doc_ids=sds, last_access=ent.get("last_access", ""),
        )
        synced_e += 1

    # Sync relations
    seen = set()
    for ent in entities:
        for rel in db.get_relations_for_entity(ent["id"]):
            key = f"{rel['source_entity_id']}_{rel['target_entity_id']}_{rel['relation_type']}"
            if key in seen:
                continue
            seen.add(key)
            sds = rel.get("source_doc_ids", [])
            if isinstance(sds, str):
                try:
                    sds = _json.loads(sds)
                except (_json.JSONDecodeError, TypeError):
                    sds = []
            graph_db.add_relation(
                source_id=rel["source_entity_id"], target_id=rel["target_entity_id"],
                relation_type=rel["relation_type"], confidence=rel.get("confidence", 1.0),
                source_doc_ids=sds, evidence=rel.get("evidence", ""),
            )
            synced_r += 1

    return {
        "status": "ok", "synced_entities": synced_e, "synced_relations": synced_r,
        "graph_entities": graph_db.entity_count, "graph_relations": graph_db.relation_count,
    }

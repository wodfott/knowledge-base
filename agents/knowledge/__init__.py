"""Knowledge Agent: entity and relation extraction, graph population."""

import logging
from datetime import datetime

from utils.llm import llm_client
from utils import generate_entity_id, generate_relation_id, chunk_text
from storage import db
from storage.graph_db import graph_db
from config import settings

logger = logging.getLogger(__name__)


def process_document(doc_id: str) -> dict:
    """Process a collected document: extract entities + relations, write to graph."""
    doc = db.get_document(doc_id)
    if not doc:
        return {"status": "error", "message": f"Document not found: {doc_id}"}

    try:
        text = doc["title"] + "\n" + doc["content"]

        # 1. Extract entities
        entities = llm_client.extract_entities(text)
        logger.info(f"Extracted {len(entities)} entities from doc {doc_id}")

        saved_entities = []
        for ent in entities:
            ent_id = generate_entity_id(ent["name"], ent.get("type", "Other"))
            now = datetime.now().isoformat()

            # Check if entity already exists
            existing = db.find_entity_by_name(ent["name"])
            if existing:
                # Merge source_doc_ids
                source_ids = existing["source_doc_ids"]
                if doc_id not in source_ids:
                    source_ids.append(doc_id)
                entity_data = {
                    **existing,
                    "description": ent.get("description") or existing.get("description"),
                    "source_doc_ids": source_ids,
                    "updated_at": now,
                }
            else:
                entity_data = {
                    "id": ent_id,
                    "name": ent["name"],
                    "type": ent.get("type", "Other"),
                    "aliases": [],
                    "description": ent.get("description"),
                    "confidence": ent.get("confidence", 0.8),
                    "source_doc_ids": [doc_id],
                    "created_at": now,
                    "updated_at": now,
                    "last_access": now,
                    "metadata": {},
                }

            db.insert_entity(entity_data)
            graph_db.add_entity(
                entity_id=ent_id,
                name=entity_data["name"],
                entity_type=entity_data["type"],
                description=entity_data.get("description"),
                confidence=entity_data["confidence"],
                source_doc_ids=entity_data["source_doc_ids"],
            )
            saved_entities.append(entity_data)

        # 2. Extract relations
        relations = llm_client.extract_relations(text, entities)
        logger.info(f"Extracted {len(relations)} relations from doc {doc_id}")

        saved_relations = []
        for rel in relations:
            source_ent = db.find_entity_by_name(rel["source"])
            target_ent = db.find_entity_by_name(rel["target"])

            if not source_ent or not target_ent:
                logger.warning(f"Skipping relation {rel}: entity not found")
                continue

            rel_id = generate_relation_id(rel["source"], rel["target"], rel["type"])
            now = datetime.now().isoformat()

            relation_data = {
                "id": rel_id,
                "source_entity_id": source_ent["id"],
                "target_entity_id": target_ent["id"],
                "relation_type": rel["type"],
                "confidence": rel.get("confidence", 0.8),
                "source_doc_ids": [doc_id],
                "evidence": rel.get("evidence"),
                "created_at": now,
                "metadata": {},
            }

            db.insert_relation(relation_data)
            graph_db.add_relation(
                source_id=source_ent["id"],
                target_id=target_ent["id"],
                relation_type=rel["type"],
                relation_id=rel_id,
                confidence=rel.get("confidence", 0.8),
                source_doc_ids=[doc_id],
                evidence=rel.get("evidence"),
            )
            saved_relations.append(relation_data)

        return {
            "status": "ok",
            "doc_id": doc_id,
            "entities_count": len(saved_entities),
            "relations_count": len(saved_relations),
            "entities": saved_entities,
            "relations": saved_relations,
        }

    except Exception as e:
        logger.error(f"Knowledge extraction failed for doc {doc_id}: {e}")
        return {"status": "error", "message": str(e)}


def chunk_and_index_document(doc_id: str) -> dict:
    """Chunk a document and index with BM25 for keyword search."""
    from utils.retriever import bm25_retriever

    doc = db.get_document(doc_id)
    if not doc:
        return {"status": "error", "message": f"Document not found: {doc_id}"}

    try:
        chunks = chunk_text(doc["content"], chunk_size=500, overlap=50)
        chunk_records = []

        for i, chunk_text_content in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            chunk_records.append({
                "id": chunk_id,
                "doc_id": doc_id,
                "chunk_index": i,
                "content": chunk_text_content,
                "title": doc["title"],
                "token_count": len(chunk_text_content),
            })

        # Save chunks to SQLite
        db.insert_chunks(chunk_records)

        # Add to BM25 index
        bm25_retriever.add(chunk_records)
        logger.info(f"Indexed {len(chunks)} chunks for doc {doc_id}, BM25 total: {bm25_retriever.count()}")

        return {"status": "ok", "doc_id": doc_id, "chunks_count": len(chunks)}

    except Exception as e:
        logger.error(f"Chunk/index failed for doc {doc_id}: {e}")
        return {"status": "error", "message": str(e)}


def process_and_index_document(doc_id: str) -> dict:
    """Full pipeline: collect → extract knowledge → chunk & embed."""
    logger.info(f"Processing document: {doc_id}")

    # Step 1: Extract knowledge
    knowledge_result = process_document(doc_id)
    if knowledge_result["status"] != "ok":
        return knowledge_result

    # Step 2: Chunk and index with BM25
    index_result = chunk_and_index_document(doc_id)

    return {
        "status": "ok",
        "doc_id": doc_id,
        "knowledge": {
            "entities": knowledge_result["entities_count"],
            "relations": knowledge_result["relations_count"],
        },
        "indexing": {
            "chunks": index_result.get("chunks_count", 0),
        },
    }

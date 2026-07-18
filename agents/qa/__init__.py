"""QA Agent: retrieval-augmented question answering."""

import logging
import hashlib
from datetime import datetime
from typing import Optional

from utils.llm import llm_client
from utils.embedding import embedding_client
from storage.vector_db import vector_db
from storage.graph_db import graph_db
from storage import db
from config import settings

logger = logging.getLogger(__name__)


def search(
    query: str,
    top_k: int = 20,
    use_graph: bool = True,
) -> list[dict]:
    """Dual-path retrieval: vector search + graph search."""
    results = []

    # 1. Vector retrieval
    query_embedding = embedding_client.embed_single(query)
    vector_results = vector_db.search(query_embedding, top_k=top_k)
    results.extend(vector_results)

    # 2. Graph retrieval (entity lookup + neighbors)
    if use_graph:
        entities = graph_db.search_entities(query, max_results=5)
        for entity in entities:
            entity_id = entity["id"]
            neighbors = graph_db.get_neighbors(entity_id, max_depth=1)
            for n in neighbors.get("neighbors", []):
                results.append({
                    "doc_id": entity_id,
                    "chunk_id": f"graph_{entity_id}",
                    "content": f"{entity.get('name', '')}: {entity.get('description', '')}",
                    "title": entity.get("name", ""),
                    "score": 0.5,
                })

    # Deduplicate by doc_id
    seen = set()
    unique_results = []
    for r in results:
        if r["doc_id"] not in seen:
            seen.add(r["doc_id"])
            unique_results.append(r)

    # Sort by score
    unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return unique_results[:top_k]


def answer(
    question: str,
    session_id: Optional[str] = None,
    top_k: int = 20,
) -> dict:
    """Full RAG pipeline: retrieve → generate answer."""
    try:
        # 1. Retrieve relevant chunks
        search_results = search(question, top_k=top_k)
        if not search_results:
            return {
                "answer": "知识库中暂无相关内容。请先采集一些文档再提问。",
                "sources": [],
                "cached": False,
            }

        # 2. Prepare context (top 3 chunks)
        context_chunks = [r["content"][:1500] for r in search_results[:3]]

        # 3. Generate answer
        answer_text = llm_client.answer_question(question, context_chunks)

        # 4. Format sources
        sources = [
            {
                "doc_id": r["doc_id"],
                "chunk_id": r["chunk_id"],
                "content": r["content"][:300],
                "score": round(r.get("score", 0), 3),
                "title": r.get("title", ""),
            }
            for r in search_results[:5]
        ]

        return {
            "answer": answer_text,
            "sources": sources,
            "cached": False,
            "session_id": session_id,
        }

    except Exception as e:
        logger.error(f"QA pipeline failed: {e}")
        return {
            "answer": f"问答处理出错: {str(e)}",
            "sources": [],
            "cached": False,
        }


def generate_entity_card(entity_name: str) -> dict:
    """Generate a Feishu card-friendly entity summary."""
    entity = graph_db.find_entity_by_name(entity_name)
    if not entity:
        return {"found": False, "text": f"未找到实体: {entity_name}"}

    entity_id = entity["id"]
    text_tree = graph_db.build_text_tree(entity_id, max_depth=1)

    # Get neighbors for structured data
    neighbors_data = graph_db.get_neighbors(entity_id, max_depth=1)
    relations = []
    for n in neighbors_data.get("neighbors", []):
        rel = n.get("relation", {})
        relations.append({
            "target_name": n.get("name", ""),
            "target_type": n.get("type", ""),
            "relation_type": rel.get("type", ""),
            "direction": rel.get("direction", ""),
            "confidence": rel.get("confidence", 0),
        })

    # Get documents mentioning this entity
    source_doc_ids = entity.get("source_doc_ids", "[]")
    if isinstance(source_doc_ids, str):
        import json
        source_doc_ids = json.loads(source_doc_ids)

    related_docs = []
    for doc_id in source_doc_ids[:3]:
        doc = db.get_document(doc_id)
        if doc:
            related_docs.append({"id": doc["id"], "title": doc["title"][:100]})

    return {
        "found": True,
        "entity": {
            "id": entity_id,
            "name": entity.get("name", entity_name),
            "type": entity.get("type", ""),
            "description": entity.get("description", ""),
            "confidence": entity.get("confidence", 0),
        },
        "relations": relations[:10],
        "related_docs": related_docs,
        "text_tree": text_tree,
    }

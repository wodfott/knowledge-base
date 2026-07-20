"""QA Agent: BM25 retrieval + LLM answer generation."""

import json
import logging
from typing import Optional

from utils.llm import llm_client
from utils.retriever import bm25_retriever
from storage.graph_db import graph_db
from storage import db
from config import settings

logger = logging.getLogger(__name__)


def search(
    query: str,
    top_k: int = 20,
    use_graph: bool = True,
) -> list[dict]:
    """Dual-path retrieval: BM25 keyword search + graph search."""
    results = []

    # 1. BM25 keyword retrieval
    bm25_results = bm25_retriever.search(query, top_k=top_k)
    results.extend(bm25_results)

    # 2. Graph retrieval (entity lookup)
    if use_graph:
        entities = graph_db.search_entities(query, max_results=5)
        for entity in entities:
            # Skip orphaned entities (from deleted docs)
            sds = entity.get("source_doc_ids", "[]")
            if isinstance(sds, str):
                try: sds = json.loads(sds)
                except: sds = []
            if not sds: continue
            entity_id = entity["id"]
            neighbors = graph_db.get_neighbors(entity_id, max_depth=1)
            for n in neighbors.get("neighbors", []):
                results.append({
                    "doc_id": entity_id,
                    "chunk_id": f"graph_{entity_id}",
                    "content": f"{entity.get('name', '')}: {entity.get('description', '')}. "
                               f"Related: {n.get('name', '')} [{n.get('type', '')}]",
                    "title": entity.get("name", ""),
                    "score": 0.5,
                })

    # Deduplicate by content
    seen = set()
    unique_results = []
    for r in results:
        key = r.get("chunk_id", r.get("content", "")[:50])
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    # Sort by score
    unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return unique_results[:top_k]


def _rewrite_query(question: str) -> str:
    """Rewrite short queries for better retrieval (simple keyword extraction)."""
    # For short queries (≤5 chars), try to expand
    if len(question) <= 5:
        return question  # Too short to rewrite meaningfully
    # For Chinese questions ending with 吗/呢/？, strip to core
    core = question.rstrip("吗呢？?！!")
    return core


def _handle_meta_question(question: str) -> Optional[dict]:
    """Detect metadata/introspection questions and answer from DB directly.

    Returns None if this is NOT a meta question (→ proceed to BM25 + LLM).
    """
    q = question.strip().lower()

    # Patterns for meta questions
    meta_patterns = [
        # Recent docs
        ("最近采集", "recent_docs"),
        ("最近收藏", "recent_docs"),
        ("最近有什么", "recent_docs"),
        ("最近有哪些", "recent_docs"),
        ("最近新增", "recent_docs"),
        ("最新文档", "recent_docs"),
        ("最近的内容", "recent_docs"),
        ("最近收集", "recent_docs"),
        ("最近导入", "recent_docs"),
        # Stats
        ("多少篇文档", "stats"),
        ("多少文档", "stats"),
        ("多少实体", "stats"),
        ("多少关系", "stats"),
        ("知识库有多大", "stats"),
        ("系统状态", "stats"),
        ("有哪些文档", "list_docs"),
        ("文档列表", "list_docs"),
    ]

    matched = None
    for pattern, action in meta_patterns:
        if pattern in q:
            matched = action
            break

    if not matched:
        return None

    if matched == "recent_docs":
        docs = db.list_documents(limit=10)
        if not docs:
            return {"answer": "知识库中还没有任何文档。发送 /collect URL 来采集第一篇！", "sources": [], "cached": False}
        lines = ["📄 **最近采集的文档:**\n"]
        for d in docs:
            date = d.get("collected_at", "")[:10]
            src = d.get("source_type", "")
            lines.append(f"• **{d['title']}** ({src} · {date})")
        return {"answer": "\n".join(lines), "sources": [], "cached": False}

    elif matched == "stats":
        stats = db.get_stats()
        return {"answer": f"📊 **知识库概况**\n\n• 文档: {stats['documents']} 篇\n• 实体: {stats['entities']} 个\n• 关系: {stats['relations']} 条", "sources": [], "cached": False}

    elif matched == "list_docs":
        docs = db.list_documents(limit=20)
        if not docs:
            return {"answer": "知识库中还没有任何文档。", "sources": [], "cached": False}
        lines = [f"📚 **知识库文档列表** ({len(docs)} 篇):\n"]
        for d in docs:
            lines.append(f"• {d['title']} [{d.get('source_type', '')}]")
        return {"answer": "\n".join(lines), "sources": [], "cached": False}

    return None


def answer(
    question: str,
    session_id: Optional[str] = None,
    top_k: int = 20,
) -> dict:
    """Full pipeline: cache → meta-check → retrieve → generate answer."""
    from utils.cache import semantic_cache

    try:
        # 0. Check cache
        cached = semantic_cache.get(question)
        if cached:
            return {**cached, "cached": True, "session_id": session_id}

        # 0.3 Check if this is a meta/introspection question
        meta_result = _handle_meta_question(question)
        if meta_result:
            semantic_cache.set(question, meta_result)
            return {**meta_result, "session_id": session_id}

        # 0.5 Rewrite query for better retrieval
        search_query = _rewrite_query(question)

        # 1. Retrieve relevant chunks
        search_results = search(search_query, top_k=top_k)

        # 1.2 If top result is weak, try LLM query expansion
        top_score = search_results[0].get("score", 0) if search_results else -999
        if top_score < 1.0 and len(search_results) < 3:
            logger.info(f"Weak BM25 results (top_score={top_score:.1f}), trying query expansion...")
            try:
                expanded_queries = llm_client.expand_query(question)
                seen_ids = {r.get("chunk_id") for r in search_results}
                for eq in expanded_queries:
                    if eq == question:
                        continue
                    extra = search(eq, top_k=5)
                    for r in extra:
                        if r.get("chunk_id") not in seen_ids:
                            seen_ids.add(r["chunk_id"])
                            search_results.append(r)
                # Re-sort
                search_results.sort(key=lambda x: x.get("score", 0), reverse=True)
                logger.info(f"After expansion: {len(search_results)} results, top_score={search_results[0].get('score',0):.1f}")
            except Exception as e:
                logger.warning(f"Query expansion failed: {e}")

        if not search_results:
            # Try web search fallback
            from utils.web_search import enrich_answer
            web_answer = enrich_answer(question, search_results)
            if web_answer:
                return {
                    "answer": web_answer,
                    "sources": [],
                    "cached": False,
                }
            return {
                "answer": "知识库中暂无相关内容。请先通过 /collect 采集一些文档再提问。",
                "sources": [],
                "cached": False,
            }

        # 1.5 Score cutoff: warn if top result is still weak after expansion
        top_score = search_results[0].get("score", 0) if search_results else 0

        # 2. Prepare context (top 3 chunks)
        context_chunks = [r["content"][:1500] for r in search_results[:3]]

        # 3. Generate answer
        answer_text = llm_client.answer_question(question, context_chunks)

        # Add notice for low-confidence results
        if top_score < -5 and len(search_results) <= 1:
            answer_text = "⚠️ 知识库中相关内容较少，以下答案可能不够准确:\n\n" + answer_text

        # 4. Format sources
        sources = [
            {
                "doc_id": r.get("doc_id", ""),
                "chunk_id": r.get("chunk_id", ""),
                "content": r.get("content", "")[:300],
                "score": round(r.get("score", 0), 3),
                "title": r.get("title", ""),
            }
            for r in search_results[:5]
        ]

        result = {
            "answer": answer_text,
            "sources": sources,
            "cached": False,
            "session_id": session_id,
        }

        # 5. Cache the result
        semantic_cache.set(question, result)

        return result

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

    import json
    source_doc_ids = entity.get("source_doc_ids", "[]")
    if isinstance(source_doc_ids, str):
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

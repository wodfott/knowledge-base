"""Text retrieval using BM25 + jieba (zero external model downloads)."""

import logging
import jieba
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Retriever:
    """BM25 keyword-based document retriever for Chinese text."""

    def __init__(self):
        self._corpus: list[str] = []
        self._metadata: list[dict] = []
        self._bm25: BM25Okapi | None = None
        self._tokenized_corpus: list[list[str]] = []

    def add(self, chunks: list[dict]):
        """Add chunks to the index."""
        for chunk in chunks:
            text = chunk.get("content", "")
            self._corpus.append(text)
            self._metadata.append({
                "chunk_id": chunk.get("id", ""),
                "doc_id": chunk.get("doc_id", ""),
                "title": chunk.get("title", ""),
                "content": text,
            })
        self._rebuild_index()

    def _rebuild_index(self):
        """Rebuild BM25 index from corpus."""
        self._tokenized_corpus = [
            list(jieba.cut(text)) for text in self._corpus
        ]
        if self._tokenized_corpus:
            self._bm25 = BM25Okapi(self._tokenized_corpus)

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """Search for relevant chunks."""
        if not self._bm25:
            return []

        tokenized_query = list(jieba.cut(query))
        scores = self._bm25.get_scores(tokenized_query)

        # Get top-k indices (BM25 scores can be negative, always take top-k)
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        top_indices = [i for i, _ in indexed_scores[:top_k]]

        results = []
        for idx in top_indices:
            if idx < len(self._metadata):
                meta = dict(self._metadata[idx])
                meta["score"] = float(scores[idx])
                results.append(meta)

        return results

    def delete_by_doc(self, doc_id: str):
        """Remove chunks for a document from the index."""
        keep_indices = [
            i for i, m in enumerate(self._metadata)
            if m.get("doc_id") != doc_id
        ]
        if len(keep_indices) < len(self._corpus):
            self._corpus = [self._corpus[i] for i in keep_indices]
            self._metadata = [self._metadata[i] for i in keep_indices]
            self._rebuild_index()
            logger.info(f"Removed doc {doc_id} from BM25 index")

    def count(self) -> int:
        return len(self._corpus)

    def load_from_db(self):
        """Reload all chunks from SQLite — call on startup."""
        from storage import db
        try:
            chunks = db.get_all_chunks()
            if chunks:
                # Build doc_id → title map
                title_map = {}
                for doc in db.list_documents(limit=10000):
                    title_map[doc["id"]] = doc.get("title", "")

                self._corpus = [c["content"] for c in chunks]
                self._metadata = [{
                    "chunk_id": c.get("id", ""),
                    "doc_id": c.get("doc_id", ""),
                    "title": title_map.get(c.get("doc_id", ""), ""),
                    "content": c.get("content", ""),
                } for c in chunks]
                self._rebuild_index()
                logger.info(f"BM25 reloaded: {len(chunks)} chunks from DB")
            else:
                logger.info("BM25: no chunks in DB")
        except Exception as e:
            logger.warning(f"BM25 load_from_db failed: {e}")


# Singleton
bm25_retriever = BM25Retriever()

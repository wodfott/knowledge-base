"""LanceDB vector database wrapper for document chunk embeddings."""

import lancedb
from pathlib import Path
from typing import Optional

from config import settings


class VectorDB:
    """LanceDB-backed vector store for semantic search."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.vector_db_path
        Path(self.db_path).mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(self.db_path)
        self._table_name = "chunks"
        self._init_table()

    def _init_table(self):
        """Create table if it doesn't exist."""
        if self._table_name not in self._db.table_names():
            import pyarrow as pa
            schema = pa.schema([
                pa.field("chunk_id", pa.string()),
                pa.field("doc_id", pa.string()),
                pa.field("content", pa.string()),
                pa.field("title", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), list_size=1536)),  # DeepSeek embedding dim
            ])
            self._db.create_table(self._table_name, schema=schema)

    @property
    def table(self):
        return self._db.open_table(self._table_name)

    def add(self, chunks: list[dict], embeddings: list[list[float]]):
        """Add chunks with their embeddings to the vector store."""
        import pyarrow as pa
        import numpy as np

        data = []
        for chunk, emb in zip(chunks, embeddings):
            data.append({
                "chunk_id": chunk["id"],
                "doc_id": chunk["doc_id"],
                "content": chunk["content"][:8000],  # Truncate for safety
                "title": chunk.get("title", ""),
                "vector": [float(x) for x in emb],
            })

        self.table.add(data)

    def search(self, query_embedding: list[float], top_k: int = 20) -> list[dict]:
        """Search for similar chunks using cosine similarity."""
        results = (
            self.table.search([float(x) for x in query_embedding])
            .metric("cosine")
            .limit(top_k)
            .to_list()
        )
        return [
            {
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_id"],
                "content": r["content"],
                "title": r.get("title", ""),
                "score": 1.0 - r.get("_distance", 0),  # Convert distance to similarity
            }
            for r in results
        ]

    def delete_by_doc(self, doc_id: str):
        """Delete all chunks for a document."""
        self.table.delete(f"doc_id = '{doc_id}'")

    def count(self) -> int:
        return self.table.count_rows()


# Singleton
vector_db = VectorDB()

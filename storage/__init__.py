"""Storage layer - SQLite metadata store."""

import sqlite3
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from config import settings


class SQLiteDB:
    """SQLite database for document metadata, annotations, reviews."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.sqlite_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()
        self._migrate()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass  # WAL not supported on this filesystem, use default
        return conn

    def _init_tables(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_url TEXT,
                    author TEXT,
                    tags TEXT DEFAULT '[]',
                    simhash TEXT DEFAULT '0',
                    collected_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS document_chunks (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    token_count INTEGER DEFAULT 0,
                    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    aliases TEXT DEFAULT '[]',
                    description TEXT,
                    confidence REAL DEFAULT 1.0,
                    source_doc_ids TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_access TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS relations (
                    id TEXT PRIMARY KEY,
                    source_entity_id TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source_doc_ids TEXT DEFAULT '[]',
                    evidence TEXT,
                    created_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (source_entity_id) REFERENCES entities(id),
                    FOREIGN KEY (target_entity_id) REFERENCES entities(id)
                );

                CREATE TABLE IF NOT EXISTS annotations (
                    id TEXT PRIMARY KEY,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    annotation_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    linked_entity_id TEXT,
                    rating INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS review_records (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    ease REAL DEFAULT 2.5,
                    interval_days INTEGER DEFAULT 1,
                    repetitions INTEGER DEFAULT 0,
                    last_reviewed TEXT,
                    next_review TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    question TEXT DEFAULT '',
                    answer TEXT DEFAULT '',
                    hint TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (entity_id) REFERENCES entities(id)
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY,
                    query_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    comment TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_docs_source ON documents(source_type);
                CREATE INDEX IF NOT EXISTS idx_docs_simhash ON documents(simhash);
                CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
                CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
                CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_entity_id);
                CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_entity_id);
                CREATE INDEX IF NOT EXISTS idx_annotations_target ON annotations(target_type, target_id);
                CREATE INDEX IF NOT EXISTS idx_reviews_next ON review_records(next_review);
            """)

    def _migrate(self):
        """Add columns missing from older schema versions."""
        migrations = [
            "ALTER TABLE review_records ADD COLUMN question TEXT DEFAULT ''",
            "ALTER TABLE review_records ADD COLUMN answer TEXT DEFAULT ''",
            "ALTER TABLE review_records ADD COLUMN hint TEXT DEFAULT ''",
            "ALTER TABLE review_records ADD COLUMN metadata TEXT DEFAULT '{}'",
        ]
        with self._get_conn() as conn:
            for sql in migrations:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # Column already exists

    # --- Document operations ---
    def insert_document(self, doc: dict) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO documents
                (id, title, content, source_type, source_url, author, tags, simhash, collected_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc["id"], doc["title"], doc["content"], doc["source_type"],
                    doc.get("source_url"), doc.get("author"),
                    json.dumps(doc.get("tags", [])),
                    str(doc.get("simhash", 0)),
                    doc.get("collected_at", datetime.now().isoformat()),
                    doc.get("updated_at", datetime.now().isoformat()),
                    json.dumps(doc.get("metadata", {}), ensure_ascii=False),
                ),
            )

    def get_document(self, doc_id: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if row:
                d = dict(row)
                d["tags"] = json.loads(d["tags"])
                d["metadata"] = json.loads(d["metadata"])
                return d
        return None

    def list_documents(self, source_type: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._get_conn() as conn:
            if source_type:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE source_type = ? ORDER BY collected_at DESC LIMIT ? OFFSET ?",
                    (source_type, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM documents ORDER BY collected_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d["tags"] = json.loads(d["tags"])
                d["metadata"] = json.loads(d["metadata"])
                results.append(d)
            return results

    def find_similar_by_simhash(self, simhash: int, threshold: float = 0.85) -> list[dict]:
        """Find documents with similar SimHash (pre-filter in SQL, exact check in Python)."""
        # We retrieve all and compute in Python (simhash XOR can't be indexed easily in SQLite)
        with self._get_conn() as conn:
            rows = conn.execute("SELECT id, simhash FROM documents WHERE simhash != '0'").fetchall()

        from utils import simhash_similarity
        similar = []
        for row in rows:
            try:
                doc_hash = int(row["simhash"])
            except (ValueError, TypeError):
                continue
            if simhash_similarity(simhash, doc_hash) >= threshold:
                doc = self.get_document(row["id"])
                if doc:
                    similar.append(doc)
        return similar

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document and its chunks from SQLite."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM document_chunks WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return conn.total_changes > 0

    def update_document(self, doc_id: str, title: str = "", content: str = "") -> bool:
        """Update document title and/or content."""
        with self._get_conn() as conn:
            updates = []
            params = []
            if title:
                updates.append("title = ?")
                params.append(title)
            if content:
                updates.append("content = ?")
                params.append(content)
            if not updates:
                return False
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(doc_id)
            conn.execute(f"UPDATE documents SET {', '.join(updates)} WHERE id = ?", params)
            return conn.total_changes > 0

    def delete_entities_for_doc(self, doc_id: str) -> int:
        """Remove entity-doc associations and orphaned entities. Returns deleted count."""
        import json as _json
        deleted = 0
        entities = self.list_entities(limit=50000)
        for ent in entities:
            sds = ent.get("source_doc_ids", [])
            if isinstance(sds, str):
                try:
                    sds = _json.loads(sds)
                except (_json.JSONDecodeError, TypeError):
                    sds = []
            if doc_id in sds:
                sds.remove(doc_id)
                ent["source_doc_ids"] = sds
                # Remove from graph DB
                from storage.graph_db import graph_db
                if graph_db.has_entity(ent["id"]):
                    graph_db.add_entity(
                        entity_id=ent["id"], name=ent["name"],
                        entity_type=ent.get("type", "Other"),
                        description=ent.get("description", ""),
                        confidence=ent.get("confidence", 1.0),
                        source_doc_ids=sds,
                    )
                # If no more source docs, delete the entity (SQLite + Graph)
                if not sds:
                    self.delete_entity(ent["id"])
                    graph_db.remove_entity(ent["id"])
                    deleted += 1
                else:
                    self.insert_entity(ent)
        return deleted

    def delete_entity(self, entity_id: str):
        """Delete an entity from SQLite."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM relations WHERE source_entity_id = ? OR target_entity_id = ?",
                         (entity_id, entity_id))
            conn.execute("DELETE FROM review_records WHERE entity_id = ?", (entity_id,))
            conn.execute("DELETE FROM annotations WHERE target_id = ?", (entity_id,))
            conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))

    def count_documents(self, source_type: Optional[str] = None) -> int:
        with self._get_conn() as conn:
            if source_type:
                row = conn.execute("SELECT COUNT(*) as c FROM documents WHERE source_type = ?", (source_type,)).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) as c FROM documents").fetchone()
            return row["c"]

    # --- Chunk operations ---
    def insert_chunks(self, chunks: list[dict]) -> None:
        with self._get_conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO document_chunks (id, doc_id, chunk_index, content, token_count)
                VALUES (?, ?, ?, ?, ?)""",
                [(c["id"], c["doc_id"], c["chunk_index"], c["content"], c.get("token_count", 0)) for c in chunks],
            )

    def get_chunks_by_doc(self, doc_id: str) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM document_chunks WHERE doc_id = ? ORDER BY chunk_index",
                (doc_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_chunks(self) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM document_chunks ORDER BY doc_id, chunk_index").fetchall()
            return [dict(r) for r in rows]

    # --- Entity operations ---
    def insert_entity(self, entity: dict) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO entities
                (id, name, type, aliases, description, confidence, source_doc_ids, created_at, updated_at, last_access, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entity["id"], entity["name"], entity["type"],
                    json.dumps(entity.get("aliases", [])),
                    entity.get("description"),
                    entity.get("confidence", 1.0),
                    json.dumps(entity.get("source_doc_ids", [])),
                    entity.get("created_at", datetime.now().isoformat()),
                    entity.get("updated_at", datetime.now().isoformat()),
                    entity.get("last_access", datetime.now().isoformat()),
                    json.dumps(entity.get("metadata", {}), ensure_ascii=False),
                ),
            )

    def get_entity(self, entity_id: str) -> Optional[dict]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
            if row:
                d = dict(row)
                d["aliases"] = json.loads(d["aliases"])
                d["source_doc_ids"] = json.loads(d["source_doc_ids"])
                d["metadata"] = json.loads(d["metadata"])
                return d
        return None

    def find_entity_by_name(self, name: str) -> Optional[dict]:
        name = name.strip()
        with self._get_conn() as conn:
            # Exact match first
            row = conn.execute("SELECT * FROM entities WHERE name = ?", (name,)).fetchone()
            # Partial match fallback
            if not row:
                row = conn.execute(
                    "SELECT * FROM entities WHERE name LIKE ? LIMIT 1",
                    (f"%{name}%",)
                ).fetchone()
            if row:
                d = dict(row)
                d["aliases"] = json.loads(d["aliases"])
                d["source_doc_ids"] = json.loads(d["source_doc_ids"])
                d["metadata"] = json.loads(d["metadata"])
                return d
        return None

    def list_entities(self, entity_type: Optional[str] = None, limit: int = 100) -> list[dict]:
        with self._get_conn() as conn:
            if entity_type:
                rows = conn.execute("SELECT * FROM entities WHERE type = ? LIMIT ?", (entity_type, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM entities LIMIT ?", (limit,)).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d["aliases"] = json.loads(d["aliases"])
                d["source_doc_ids"] = json.loads(d["source_doc_ids"])
                d["metadata"] = json.loads(d["metadata"])
                results.append(d)
            return results

    def count_entities(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) as c FROM entities").fetchone()["c"]

    # --- Relation operations ---
    def insert_relation(self, rel: dict) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO relations
                (id, source_entity_id, target_entity_id, relation_type, confidence,
                 source_doc_ids, evidence, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rel["id"], rel["source_entity_id"], rel["target_entity_id"],
                    rel["relation_type"], rel.get("confidence", 1.0),
                    json.dumps(rel.get("source_doc_ids", [])),
                    rel.get("evidence"),
                    rel.get("created_at", datetime.now().isoformat()),
                    json.dumps(rel.get("metadata", {}), ensure_ascii=False),
                ),
            )

    def get_relations_for_entity(self, entity_id: str) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM relations WHERE source_entity_id = ? OR target_entity_id = ?",
                (entity_id, entity_id),
            ).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d["source_doc_ids"] = json.loads(d["source_doc_ids"])
                d["metadata"] = json.loads(d["metadata"])
                results.append(d)
            return results

    def count_relations(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) as c FROM relations").fetchone()["c"]

    # --- Annotation operations ---
    def insert_annotation(self, ann: dict) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO annotations
                (id, target_type, target_id, annotation_type, content, linked_entity_id, rating, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ann["id"], ann["target_type"], ann["target_id"],
                    ann["annotation_type"], ann["content"],
                    ann.get("linked_entity_id"), ann.get("rating"),
                    ann.get("created_at", datetime.now().isoformat()),
                    ann.get("updated_at", datetime.now().isoformat()),
                ),
            )

    def get_annotations(self, target_type: str, target_id: str) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM annotations WHERE target_type = ? AND target_id = ? ORDER BY created_at DESC",
                (target_type, target_id),
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Review operations ---
    def insert_review(self, review: dict) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO review_records
                (id, entity_id, ease, interval_days, repetitions, last_reviewed, next_review, created_at, question, answer, hint, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    review["id"], review["entity_id"],
                    review.get("ease", 2.5), review.get("interval_days", 1),
                    review.get("repetitions", 0),
                    review.get("last_reviewed"), review["next_review"],
                    review.get("created_at", datetime.now().isoformat()),
                    review.get("question", ""),
                    review.get("answer", ""),
                    review.get("hint", ""),
                    json.dumps(review.get("metadata", {}), ensure_ascii=False),
                ),
            )

    def get_due_reviews(self) -> list[dict]:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM review_records WHERE next_review <= ? ORDER BY next_review ASC",
                (now,),
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Feedback operations ---
    def insert_feedback(self, fb: dict) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO feedback (id, query_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                (fb["id"], fb["query_id"], fb["rating"], fb.get("comment"), fb.get("created_at", datetime.now().isoformat())),
            )

    # --- Stats ---
    def get_stats(self, since: Optional[str] = None) -> dict:
        with self._get_conn() as conn:
            doc_count = conn.execute(
                "SELECT COUNT(*) as c FROM documents" + (" WHERE collected_at >= ?" if since else ""),
                (since,) if since else (),
            ).fetchone()["c"]
            entity_count = conn.execute(
                "SELECT COUNT(*) as c FROM entities" + (" WHERE created_at >= ?" if since else ""),
                (since,) if since else (),
            ).fetchone()["c"]
            rel_count = conn.execute(
                "SELECT COUNT(*) as c FROM relations" + (" WHERE created_at >= ?" if since else ""),
                (since,) if since else (),
            ).fetchone()["c"]
            return {"documents": doc_count, "entities": entity_count, "relations": rel_count}


# Singleton
db = SQLiteDB()

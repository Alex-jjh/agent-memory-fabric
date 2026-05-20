"""SQLite sidecar — derived index for metadata, vectors, graph edges, and FTS."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from agent_memory_fabric.core.node import MemoryNode

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active',
    type TEXT NOT NULL DEFAULT 'project',
    project TEXT,
    created TEXT NOT NULL,
    modified TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    access_count INTEGER DEFAULT 0,
    decay_score REAL DEFAULT 1.0,
    strength REAL DEFAULT 1.0,
    ttl TEXT,
    tags TEXT,
    file_path TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS edges (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL DEFAULT 'links_to',
    weight REAL DEFAULT 1.0,
    created TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, edge_type)
);
"""

FTS_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS fts_index USING fts5(
    node_id UNINDEXED, name, content, tags, tokenize='unicode61', prefix='2,3'
);
"""


class SQLiteStore:
    """SQLite sidecar database (.amf/index.db).

    This is a DERIVED index — Markdown files are source of truth.
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path) if not isinstance(db_path, Path) else db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._vec_available: Optional[bool] = None
        self._vec_initialized: bool = False

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn

    def initialize(self) -> None:
        conn = self._get_conn()
        conn.executescript(SCHEMA_SQL)
        conn.executescript(FTS_SCHEMA_SQL)
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def upsert_node(self, node: MemoryNode, content: str | None = None) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO nodes
               (id, name, state, type, project, created, modified, last_accessed,
                access_count, decay_score, strength, ttl, tags, file_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node.id,
                node.name,
                node.state.value,
                node.type.value,
                node.project,
                node.created.isoformat(),
                node.modified.isoformat(),
                node.last_accessed.isoformat(),
                node.access_count,
                node.decay_score,
                node.strength,
                node.ttl.isoformat() if node.ttl else None,
                json.dumps(node.tags),
                None,
            ),
        )
        fts_content = content or node.content
        conn.execute("DELETE FROM fts_index WHERE node_id = ?", (node.id,))
        conn.execute(
            "INSERT INTO fts_index (node_id, name, content, tags) VALUES (?, ?, ?, ?)",
            (node.id, node.name, fts_content, " ".join(node.tags)),
        )
        conn.commit()

    def delete_node(self, node_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        conn.execute("DELETE FROM fts_index WHERE node_id = ?", (node_id,))
        conn.execute("DELETE FROM edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
        conn.commit()

    def get_node(self, node_id: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_all_nodes(
        self, state: str | None = None, project: str | None = None
    ) -> list[dict]:
        conn = self._get_conn()
        query = "SELECT * FROM nodes WHERE 1=1"
        params: list = []
        if state:
            query += " AND state = ?"
            params.append(state)
        if project:
            query += " AND project = ?"
            params.append(project)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def search_fts(self, query: str, limit: int = 10) -> list[tuple[str, float]]:
        """Full-text search. Returns (node_id, bm25_score) pairs, best first."""
        conn = self._get_conn()
        safe_query = self._prepare_fts_query(query)
        if not safe_query:
            return []
        rows = conn.execute(
            """SELECT node_id, bm25(fts_index) as score
               FROM fts_index
               WHERE fts_index MATCH ?
               ORDER BY score ASC
               LIMIT ?""",
            (safe_query, limit),
        ).fetchall()
        return [(row["node_id"], -row["score"]) for row in rows]

    def _prepare_fts_query(self, query: str) -> str:
        terms = query.strip().split()
        if not terms:
            return ""
        safe_terms = []
        for t in terms:
            cleaned = "".join(c for c in t if c.isalnum() or c in "-_")
            if cleaned:
                safe_terms.append(f'"{cleaned}"')
        if not safe_terms:
            return ""
        return " OR ".join(safe_terms)

    def add_edge(
        self, source_id: str, target_id: str, edge_type: str = "links_to", weight: float = 1.0
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO edges (source_id, target_id, edge_type, weight, created)
               VALUES (?, ?, ?, ?, datetime('now'))""",
            (source_id, target_id, edge_type, weight),
        )
        conn.commit()

    def get_neighbors(self, node_id: str, edge_type: str | None = None) -> list[str]:
        conn = self._get_conn()
        if edge_type:
            rows = conn.execute(
                """SELECT target_id FROM edges WHERE source_id = ? AND edge_type = ?
                   UNION
                   SELECT source_id FROM edges WHERE target_id = ? AND edge_type = ?""",
                (node_id, edge_type, node_id, edge_type),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT target_id FROM edges WHERE source_id = ?
                   UNION
                   SELECT source_id FROM edges WHERE target_id = ?""",
                (node_id, node_id),
            ).fetchall()
        return [row[0] for row in rows]

    def get_all_edges(self) -> list[tuple[str, str, str, float]]:
        conn = self._get_conn()
        rows = conn.execute("SELECT source_id, target_id, edge_type, weight FROM edges").fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    def reconcile(self, filesystem_nodes: list[MemoryNode]) -> None:
        conn = self._get_conn()
        fs_ids = {node.id for node in filesystem_nodes}
        db_rows = conn.execute("SELECT id FROM nodes").fetchall()
        db_ids = {row["id"] for row in db_rows}

        to_delete = db_ids - fs_ids
        for node_id in to_delete:
            self.delete_node(node_id)

        for node in filesystem_nodes:
            self.upsert_node(node)

    def _ensure_vec_table(self, dimension: int) -> None:
        """Create the vec0 virtual table if sqlite-vec is available."""
        if self._vec_available is None:
            conn = self._get_conn()
            try:
                import sqlite_vec
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
                self._vec_available = True
            except (ImportError, Exception):
                self._vec_available = False

        if self._vec_available and not self._vec_initialized:
            conn = self._get_conn()
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_embeddings USING vec0("
                f"node_id TEXT PRIMARY KEY, embedding float[{dimension}])"
            )
            conn.commit()
            self._vec_initialized = True

    def search_vector(self, embedding: list[float], limit: int = 10) -> list[tuple[str, float]]:
        """Vector similarity search via sqlite-vec. Returns (node_id, distance) pairs.

        Falls back to empty results if sqlite-vec is not available.
        """
        if not getattr(self, "_vec_available", None):
            return []
        conn = self._get_conn()
        import struct
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        rows = conn.execute(
            "SELECT node_id, distance FROM vec_embeddings WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (blob, limit),
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def upsert_embedding(self, node_id: str, embedding: list[float]) -> None:
        """Store or update embedding for a node. No-op if sqlite-vec unavailable."""
        if not getattr(self, "_vec_available", None):
            return
        conn = self._get_conn()
        import struct
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        conn.execute(
            "INSERT OR REPLACE INTO vec_embeddings (node_id, embedding) VALUES (?, ?)",
            (node_id, blob),
        )
        conn.commit()

"""
JARVIS — Persistent fact memory with FTS5 full-text search.

Stores things JARVIS learns about Ricardo during conversation:
preferences, facts, project context, people, decisions.

No Qdrant required — SQLite FTS5 handles semantic-ish recall
via keyword matching + importance ranking.

Inspired by the memory system in JARVIS (ethanplusai).
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, List, Optional

from backend.utils.logger import get_logger

logger = get_logger("jarvis.memory.facts")

VALID_TYPES = {"fact", "preference", "project", "person", "decision", "task"}

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS facts (
    id            TEXT PRIMARY KEY,
    type          TEXT    NOT NULL DEFAULT 'fact',
    content       TEXT    NOT NULL,
    source        TEXT,               -- first 60 chars of the user message that triggered it
    importance    INTEGER DEFAULT 5,  -- 1 (trivial) … 10 (critical)
    created_at    TEXT    NOT NULL,
    last_accessed TEXT,
    access_count  INTEGER DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content,
    type,
    content='facts',
    content_rowid='rowid',
    tokenize='unicode61'
);

-- Keep FTS index in sync with the main table
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, content, type)
    VALUES (new.rowid, new.content, new.type);
END;

CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, type)
    VALUES ('delete', old.rowid, old.content, old.type);
END;

CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, type)
    VALUES ('delete', old.rowid, old.content, old.type);
    INSERT INTO facts_fts(rowid, content, type)
    VALUES (new.rowid, new.content, new.type);
END;

CREATE INDEX IF NOT EXISTS idx_facts_type       ON facts(type);
CREATE INDEX IF NOT EXISTS idx_facts_importance ON facts(importance DESC);
CREATE INDEX IF NOT EXISTS idx_facts_accessed   ON facts(last_accessed DESC);
"""


class FactMemory:
    """SQLite-backed fact store with FTS5 recall.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str = "data/facts.db") -> None:
        self._path = db_path

    def init(self) -> None:
        """Create tables and FTS index if they don't exist."""
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
        logger.info(f"[JARVIS] FactMemory initialised at {self._path}")

    # ── Write ──────────────────────────────────────────────────────────────────

    def add(
        self,
        content: str,
        fact_type: str = "fact",
        source: str = "",
        importance: int = 5,
    ) -> str:
        """Store a new fact and return its ID.

        Deduplicates by exact content match — if the same content already
        exists, bumps its importance and returns the existing ID.
        """
        content = content.strip()
        if not content:
            return ""
        fact_type = fact_type if fact_type in VALID_TYPES else "fact"
        importance = max(1, min(10, importance))

        with self._conn() as conn:
            # Dedup check
            row = conn.execute(
                "SELECT id, importance FROM facts WHERE content=? LIMIT 1",
                (content,),
            ).fetchone()
            if row:
                new_imp = max(row[1], importance)
                conn.execute(
                    "UPDATE facts SET importance=?, last_accessed=? WHERE id=?",
                    (new_imp, _now(), row[0]),
                )
                return row[0]

            fact_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO facts(id,type,content,source,importance,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (fact_id, fact_type, content, source[:60], importance, _now()),
            )
        logger.info(f"[JARVIS] FactMemory: stored [{fact_type}] imp={importance} — {content[:60]}")
        return fact_id

    def remove(self, fact_id: str) -> None:
        """Delete a fact by ID."""
        with self._conn() as conn:
            conn.execute("DELETE FROM facts WHERE id=?", (fact_id,))

    # ── Read ───────────────────────────────────────────────────────────────────

    def recall(self, query: str, limit: int = 6) -> List[dict]:
        """FTS5 full-text search ranked by relevance × importance.

        Falls back to recent high-importance facts if no FTS match.
        """
        if not query.strip():
            return self.important(limit)

        # Sanitise FTS query — wrap in quotes to avoid syntax errors
        fts_query = " OR ".join(
            f'"{w}"' for w in query.split()
            if len(w) >= 2 and w.isalnum()
        ) or f'"{query[:40]}"'

        with self._conn() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT f.id, f.type, f.content, f.importance, f.access_count
                    FROM facts_fts ft
                    JOIN facts f ON f.rowid = ft.rowid
                    WHERE facts_fts MATCH ?
                    ORDER BY (rank * -1) + (f.importance * 0.5) DESC
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []

        if not rows:
            return self.important(limit)

        ids = [r[0] for r in rows]
        self._bump_access(ids)
        return [
            {"id": r[0], "type": r[1], "content": r[2],
             "importance": r[3], "access_count": r[4]}
            for r in rows
        ]

    def important(self, limit: int = 5) -> List[dict]:
        """Return highest-importance facts (secondary sort: most accessed)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, type, content, importance, access_count "
                "FROM facts "
                "ORDER BY importance DESC, access_count DESC "
                "LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": r[0], "type": r[1], "content": r[2],
             "importance": r[3], "access_count": r[4]}
            for r in rows
        ]

    def recent(self, limit: int = 5) -> List[dict]:
        """Return most recently stored facts."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, type, content, importance, created_at "
                "FROM facts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": r[0], "type": r[1], "content": r[2],
             "importance": r[3], "created_at": r[4]}
            for r in rows
        ]

    def count(self) -> int:
        """Return total number of stored facts."""
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]

    # ── Prompt injection ───────────────────────────────────────────────────────

    def to_prompt_text(self, query: str = "", limit: int = 6) -> str:
        """Format relevant facts for LLM system prompt injection.

        Returns empty string if no facts are stored.
        """
        facts = self.recall(query, limit) if query else self.important(limit)
        if not facts:
            return ""

        lines = ["[LO QUE SE SOBRE RICARDO:]"]
        for f in facts:
            tag = f["type"].upper()
            lines.append(f"  [{tag}] {f['content']}")
        return "\n".join(lines)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _bump_access(self, ids: List[str]) -> None:
        if not ids:
            return
        with self._conn() as conn:
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE facts SET access_count=access_count+1, last_accessed=? "
                f"WHERE id IN ({placeholders})",
                [_now()] + ids,
            )

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

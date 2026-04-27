"""JARVIS — SQLite conversation history."""
from __future__ import annotations
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator, List
from backend.utils.logger import get_logger

logger = get_logger("jarvis.memory.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    language    TEXT DEFAULT 'en',
    timestamp   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session ON turns(session_id);
"""


class ConversationDB:
    def __init__(self, db_path: str = "data/conversations.db") -> None:
        self._path = db_path

    def init(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        try:
            conn.executescript(_SCHEMA)
        finally:
            conn.close()
        logger.info(f"[JARVIS] ConversationDB initialised at {self._path}")

    def save_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        language: str = "en",
    ) -> str:
        turn_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO turns(id,session_id,role,content,language,timestamp) "
                "VALUES(?,?,?,?,?,?)",
                (turn_id, session_id, role, content, language, ts),
            )
        return turn_id

    def get_session_turns(self, session_id: str, limit: int = 50) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content, language, timestamp FROM turns "
                "WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [
            {"role": r[0], "content": r[1], "language": r[2], "timestamp": r[3]}
            for r in reversed(rows)
        ]

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Open a connection, commit/rollback, then close (Windows-safe)."""
        conn = sqlite3.connect(self._path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

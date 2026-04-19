"""
C.Y.R.U.S — Task Planner module.

Persistent task/goal tracking inspired by JARVIS planner.py pattern.
Stores tasks in SQLite and exposes a simple API for the engine to use via
voice commands: "recuérdame hacer X", "qué tengo pendiente", "listo, terminé X".
"""
from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from backend.utils.logger import get_logger

logger = get_logger("cyrus.planner")


class TaskStatus(str, Enum):
    PENDING   = "pending"
    DONE      = "done"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id:          int
    description: str
    status:      TaskStatus
    created_at:  str
    updated_at:  str
    due_hint:    Optional[str] = None   # free-form reminder text ("mañana", "viernes")

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "description": self.description,
            "status":      self.status.value,
            "created_at":  self.created_at,
            "updated_at":  self.updated_at,
            "due_hint":    self.due_hint,
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    due_hint    TEXT
);
"""


class TaskPlanner:
    """SQLite-backed task planner.

    Args:
        db_path: Path to the SQLite database file.
        max_tasks: Maximum number of pending tasks to return in a summary.
    """

    def __init__(self, db_path: str = "data/planner.db", max_tasks: int = 100) -> None:
        self._db_path  = Path(db_path)
        self._max_tasks = max_tasks
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add_task(self, description: str, due_hint: Optional[str] = None) -> Task:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (description, status, created_at, updated_at, due_hint) "
                "VALUES (?, 'pending', ?, ?, ?)",
                (description, now, now, due_hint),
            )
            task_id = cur.lastrowid
        logger.info(f"[Planner] Task #{task_id} added: {description!r}")
        return Task(id=task_id, description=description, status=TaskStatus.PENDING,
                    created_at=now, updated_at=now, due_hint=due_hint)

    def complete_task(self, task_id: int) -> bool:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE tasks SET status='done', updated_at=? WHERE id=? AND status='pending'",
                (now, task_id),
            )
            changed = cur.rowcount > 0
        if changed:
            logger.info(f"[Planner] Task #{task_id} marked done")
        return changed

    def cancel_task(self, task_id: int) -> bool:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE tasks SET status='cancelled', updated_at=? WHERE id=? AND status='pending'",
                (now, task_id),
            )
            return cur.rowcount > 0

    def get_pending(self) -> List[Task]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status='pending' ORDER BY id DESC LIMIT ?",
                (self._max_tasks,),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def get_all(self, limit: int = 50) -> List[Task]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    # ── Summary for LLM context injection ─────────────────────────────────────

    def pending_summary(self) -> str:
        """Return a short human-readable list of pending tasks for LLM injection."""
        tasks = self.get_pending()
        if not tasks:
            return "No hay tareas pendientes."
        lines = [f"Tienes {len(tasks)} tarea(s) pendiente(s):"]
        for t in tasks:
            due = f" ({t.due_hint})" if t.due_hint else ""
            lines.append(f"  [{t.id}] {t.description}{due}")
        return "\n".join(lines)

    # ── Voice command helpers ──────────────────────────────────────────────────

    def handle_voice_command(self, text: str) -> Optional[str]:
        """Parse simple voice commands and execute them. Returns a reply or None."""
        import re
        low = text.lower().strip()

        # "recuérdame X" / "agrega tarea X" / "anota X"
        m = re.search(
            r"(?:rec[uú]erdame|agrega(?:\s+(?:una\s+)?tarea)?|anota(?:r)?(?:\s+que)?)\s+(.+)",
            low,
        )
        if m:
            desc = m.group(1).strip().capitalize()
            task = self.add_task(desc)
            return f"Anotado. Tarea #{task.id}: «{task.description}»."

        # "qué tengo pendiente" / "mis tareas" / "lista de tareas"
        if any(k in low for k in ["qué tengo pendiente", "mis tareas", "lista de tareas",
                                   "tareas pendientes", "qué debo hacer"]):
            return self.pending_summary()

        # "completé la tarea N" / "terminé la N" / "listo, tarea N"
        m = re.search(r"(?:complet[eé]|termin[eé]|listo[,.]?\s+tarea)\s+(?:la\s+)?(?:tarea\s+)?#?(\d+)", low)
        if m:
            tid = int(m.group(1))
            ok = self.complete_task(tid)
            return f"Tarea #{tid} marcada como completada." if ok else f"No encontré la tarea #{tid} pendiente."

        # "cancela la tarea N"
        m = re.search(r"cancela(?:r)?\s+(?:la\s+)?(?:tarea\s+)?#?(\d+)", low)
        if m:
            tid = int(m.group(1))
            ok = self.cancel_task(tid)
            return f"Tarea #{tid} cancelada." if ok else f"No encontré la tarea #{tid} pendiente."

        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            description=row["description"],
            status=TaskStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            due_hint=row["due_hint"],
        )

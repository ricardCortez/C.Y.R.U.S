"""
JARVIS — Task Planner con prioridad, fechas, tags y FTS5.

Inspirado en el planner de JARVIS (ethanplusai) + mejoras propias.
Schema migra automáticamente desde la versión anterior.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Generator, List, Optional

from backend.utils.logger import get_logger

logger = get_logger("jarvis.planner")


class TaskStatus(str, Enum):
    PENDING    = "pending"
    IN_PROGRESS = "in_progress"
    DONE       = "done"
    CANCELLED  = "cancelled"


class TaskPriority(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


@dataclass
class Task:
    id:          int
    description: str
    status:      TaskStatus
    priority:    TaskPriority
    created_at:  str
    updated_at:  str
    due_date:    Optional[str] = None   # ISO date YYYY-MM-DD
    due_time:    Optional[str] = None   # HH:MM
    project:     Optional[str] = None
    tags:        List[str] = field(default_factory=list)
    notes:       Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "description": self.description,
            "status": self.status.value, "priority": self.priority.value,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "due_date": self.due_date, "due_time": self.due_time,
            "project": self.project, "tags": self.tags,
            "notes": self.notes, "completed_at": self.completed_at,
        }

    @property
    def due_label(self) -> str:
        if not self.due_date:
            return ""
        try:
            d = date.fromisoformat(self.due_date)
            today = date.today()
            delta = (d - today).days
            if delta < 0:
                return f"vencida hace {-delta}d"
            if delta == 0:
                return "HOY"
            if delta == 1:
                return "mañana"
            if delta <= 7:
                return f"en {delta}d"
            return self.due_date
        except Exception:
            return self.due_date or ""


# Base table — runs first (IF NOT EXISTS is safe on old DBs)
_SCHEMA_TABLE = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    description  TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'pending',
    priority     TEXT    NOT NULL DEFAULT 'medium',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    due_date     TEXT,
    due_time     TEXT,
    project      TEXT,
    tags         TEXT    DEFAULT '[]',
    notes        TEXT,
    completed_at TEXT
);
"""

# FTS + indexes — run AFTER migrations so columns are guaranteed to exist
_SCHEMA_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
    description, project, tags,
    content=tasks, content_rowid=id,
    tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS tasks_ai AFTER INSERT ON tasks BEGIN
    INSERT INTO tasks_fts(rowid, description, project, tags)
    VALUES (new.id, new.description, COALESCE(new.project,''), COALESCE(new.tags,'[]'));
END;
CREATE TRIGGER IF NOT EXISTS tasks_ad AFTER DELETE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, description, project, tags)
    VALUES ('delete', old.id, old.description, COALESCE(old.project,''), COALESCE(old.tags,'[]'));
END;
CREATE TRIGGER IF NOT EXISTS tasks_au AFTER UPDATE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, description, project, tags)
    VALUES ('delete', old.id, old.description, COALESCE(old.project,''), COALESCE(old.tags,'[]'));
    INSERT INTO tasks_fts(rowid, description, project, tags)
    VALUES (new.id, new.description, COALESCE(new.project,''), COALESCE(new.tags,'[]'));
END;
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_due      ON tasks(due_date);
"""

_MIGRATE = [
    "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'",
    "ALTER TABLE tasks ADD COLUMN due_date TEXT",
    "ALTER TABLE tasks ADD COLUMN due_time TEXT",
    "ALTER TABLE tasks ADD COLUMN project TEXT",
    "ALTER TABLE tasks ADD COLUMN tags TEXT DEFAULT '[]'",
    "ALTER TABLE tasks ADD COLUMN notes TEXT",
    "ALTER TABLE tasks ADD COLUMN completed_at TEXT",
]

# ── Date parsing helpers ───────────────────────────────────────────────────────

_DAYS_ES = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}

def _parse_date_hint(text: str) -> Optional[str]:
    """Try to extract an ISO date from natural language like 'el viernes', 'mañana'."""
    low = text.lower()
    today = date.today()

    if "hoy" in low:
        return today.isoformat()
    if "mañana" in low or "manana" in low:
        return (today + timedelta(days=1)).isoformat()
    if "pasado mañana" in low or "pasado manana" in low:
        return (today + timedelta(days=2)).isoformat()

    for name, wd in _DAYS_ES.items():
        if name in low:
            days_ahead = (wd - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (today + timedelta(days=days_ahead)).isoformat()

    m = re.search(r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?", low)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        yr = int(m.group(3)) if m.group(3) else today.year
        if yr < 100:
            yr += 2000
        try:
            return date(yr, mo, d).isoformat()
        except ValueError:
            pass
    return None

def _parse_time_hint(text: str) -> Optional[str]:
    """Extract HH:MM from 'a las 3pm', 'a las 15:30'."""
    low = text.lower()
    m = re.search(r"a\s+las?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", low)
    if m:
        h, mi, meridiem = int(m.group(1)), int(m.group(2) or 0), m.group(3) or ""
        if meridiem == "pm" and h < 12:
            h += 12
        elif meridiem == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mi:02d}"
    return None

def _parse_priority(text: str) -> TaskPriority:
    low = text.lower()
    if any(w in low for w in ["alta", "urgente", "importante", "crítico", "critico", "asap"]):
        return TaskPriority.HIGH
    if any(w in low for w in ["baja", "cuando pueda", "opcional"]):
        return TaskPriority.LOW
    return TaskPriority.MEDIUM

def _parse_tags(text: str) -> List[str]:
    return re.findall(r"#(\w+)", text)


class TaskPlanner:
    def __init__(self, db_path: str = "data/planner.db", max_tasks: int = 100) -> None:
        self._db_path   = Path(db_path)
        self._max_tasks = max_tasks
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            # 1. Create base table (safe to run on both new and old DBs)
            conn.executescript(_SCHEMA_TABLE)
            # 2. Migrate old schema — add missing columns before creating indexes
            existing = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            for stmt in _MIGRATE:
                col = re.search(r"ADD COLUMN (\w+)", stmt)
                if col and col.group(1) not in existing:
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError:
                        pass
            # 3. Create FTS virtual table + indexes (all columns now guaranteed to exist)
            try:
                conn.executescript(_SCHEMA_FTS)
            except sqlite3.OperationalError:
                pass  # FTS might already exist

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add_task(
        self,
        description: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        due_date: Optional[str] = None,
        due_time: Optional[str] = None,
        project: Optional[str] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> Task:
        now = datetime.now().isoformat()
        tags_json = json.dumps(tags or [])
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO tasks(description,status,priority,created_at,updated_at,"
                "due_date,due_time,project,tags,notes) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (description, "pending", priority.value, now, now,
                 due_date, due_time, project, tags_json, notes),
            )
            tid = cur.lastrowid
        label = f" [{priority.value.upper()}]" + (f" — {due_date}" if due_date else "")
        logger.info(f"[Planner] Task #{tid} added{label}: {description!r}")
        return Task(id=tid, description=description, status=TaskStatus.PENDING,
                    priority=priority, created_at=now, updated_at=now,
                    due_date=due_date, due_time=due_time, project=project,
                    tags=tags or [], notes=notes)

    def complete_task(self, task_id: int) -> bool:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE tasks SET status='done', updated_at=?, completed_at=? "
                "WHERE id=? AND status IN ('pending','in_progress')",
                (now, now, task_id),
            )
        if cur.rowcount:
            logger.info(f"[Planner] Task #{task_id} done")
        return cur.rowcount > 0

    def cancel_task(self, task_id: int) -> bool:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE tasks SET status='cancelled', updated_at=? "
                "WHERE id=? AND status IN ('pending','in_progress')",
                (now, task_id),
            )
        return cur.rowcount > 0

    def set_priority(self, task_id: int, priority: TaskPriority) -> bool:
        now = datetime.now().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE tasks SET priority=?, updated_at=? WHERE id=?",
                (priority.value, now, task_id),
            )
        return cur.rowcount > 0

    def get_pending(self, project: Optional[str] = None) -> List[Task]:
        with self._conn() as conn:
            if project:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status='pending' AND project=? "
                    "ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, due_date LIMIT ?",
                    (project, self._max_tasks),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status='pending' "
                    "ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, "
                    "COALESCE(due_date,'9999') LIMIT ?",
                    (self._max_tasks,),
                ).fetchall()
        return [self._row(r) for r in rows]

    def get_today(self) -> List[Task]:
        today = date.today().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status='pending' AND due_date<=? "
                "ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END",
                (today,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> List[Task]:
        with self._conn() as conn:
            try:
                rows = conn.execute(
                    "SELECT t.* FROM tasks_fts ft JOIN tasks t ON t.id=ft.rowid "
                    "WHERE tasks_fts MATCH ? ORDER BY rank LIMIT ?",
                    (f'"{query}"', limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        return [self._row(r) for r in rows]

    # ── LLM context ───────────────────────────────────────────────────────────

    def pending_summary(self) -> str:
        tasks = self.get_pending()
        if not tasks:
            return "No hay tareas pendientes."
        today_tasks = self.get_today()
        lines = []
        if today_tasks:
            lines.append(f"TAREAS PARA HOY ({len(today_tasks)}):")
            for t in today_tasks:
                lines.append(f"  [{t.id}] [{t.priority.value.upper()}] {t.description}")
        pending_rest = [t for t in tasks if t not in today_tasks]
        if pending_rest:
            lines.append(f"PENDIENTES ({len(pending_rest)}):")
            for t in pending_rest[:8]:
                due = f" | {t.due_label}" if t.due_label else ""
                lines.append(f"  [{t.id}] [{t.priority.value.upper()}] {t.description}{due}")
            if len(pending_rest) > 8:
                lines.append(f"  ... y {len(pending_rest)-8} más.")
        return "\n".join(lines)

    # ── Voice commands ─────────────────────────────────────────────────────────

    def handle_voice_command(self, text: str) -> Optional[str]:
        low = text.lower().strip()

        # Add task — "recuérdame X", "agrega tarea X", "anota X"
        m = re.search(
            r"(?:recu[eé]rdame|recuérdame|recuerdame|"
            r"agrega(?:\s+(?:una\s+)?tarea)?|anota(?:r)?(?:\s+que)?|"
            r"crea(?:\s+una)?\s+tarea|nueva\s+tarea)\s+(.+)",
            low,
        )
        if m:
            raw = m.group(1).strip()
            desc  = re.sub(r"#\w+", "", raw).strip().capitalize()
            prio  = _parse_priority(raw)
            due_d = _parse_date_hint(raw)
            due_t = _parse_time_hint(raw)
            tags  = _parse_tags(raw)
            task  = self.add_task(desc, priority=prio, due_date=due_d,
                                  due_time=due_t, tags=tags)
            parts = [f"Anotado. Tarea #{task.id}: «{task.description}»."]
            if prio != TaskPriority.MEDIUM:
                parts.append(f"Prioridad {prio.value}.")
            if due_d:
                parts.append(f"Para el {task.due_label}.")
            return " ".join(parts)

        # List pending
        if any(k in low for k in ["qué tengo pendiente", "mis tareas", "lista de tareas",
                                   "tareas pendientes", "qué debo hacer", "agenda de hoy",
                                   "qué hay para hoy"]):
            return self.pending_summary()

        # Complete
        m = re.search(
            r"(?:complet[eé]|termin[eé]|listo[,.]?\s*(?:la\s+)?tarea|ya hice)\s+(?:la\s+)?(?:tarea\s+)?#?(\d+)",
            low,
        )
        if m:
            tid = int(m.group(1))
            ok  = self.complete_task(tid)
            return f"Tarea #{tid} completada." if ok else f"No encontré la tarea #{tid}."

        # Cancel
        m = re.search(r"cancela(?:r)?\s+(?:la\s+)?(?:tarea\s+)?#?(\d+)", low)
        if m:
            tid = int(m.group(1))
            ok  = self.cancel_task(tid)
            return f"Tarea #{tid} cancelada." if ok else f"No encontré la tarea #{tid}."

        # Set priority
        m = re.search(r"(?:cambia\s+)?prioridad\s+(?:de\s+)?(?:tarea\s+)?#?(\d+)\s+(?:a\s+)?(\w+)", low)
        if m:
            tid  = int(m.group(1))
            prio = _parse_priority(m.group(2))
            ok   = self.set_priority(tid, prio)
            return f"Prioridad de tarea #{tid} → {prio.value}." if ok else f"No encontré tarea #{tid}."

        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _row(r: sqlite3.Row) -> Task:
        tags = []
        try:
            tags = json.loads(r["tags"] or "[]")
        except Exception:
            pass
        return Task(
            id=r["id"], description=r["description"],
            status=TaskStatus(r["status"]),
            priority=TaskPriority(r["priority"] if r["priority"] else "medium"),
            created_at=r["created_at"], updated_at=r["updated_at"],
            due_date=r["due_date"], due_time=r["due_time"],
            project=r["project"], tags=tags,
            notes=r["notes"], completed_at=r["completed_at"],
        )

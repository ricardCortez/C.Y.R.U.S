"""
JARVIS — Agent Scheduler.

Runs registered async jobs on a schedule:
  daily HH:MM  — fires every day at that local time
  interval N   — fires every N seconds
  manual       — only fires on explicit trigger

Inspired by OpenJarvis scheduler.py, adapted for asyncio (no threads needed).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from backend.utils.logger import get_logger

logger = get_logger("jarvis.scheduler")


class JobStatus(str, Enum):
    IDLE    = "idle"
    RUNNING = "running"
    ERROR   = "error"


@dataclass
class ScheduledJob:
    job_id:       str
    label:        str
    fn:           Callable[[], Coroutine]
    schedule:     str            # "daily HH:MM" | "interval N" | "manual"
    status:       JobStatus = JobStatus.IDLE
    last_run:     Optional[datetime] = None
    last_error:   str = ""
    run_count:    int = 0
    _next_fire:   Optional[datetime] = field(default=None, repr=False)

    # ── Next fire calculation ─────────────────────────────────────────────

    def compute_next_fire(self, from_now: Optional[datetime] = None) -> Optional[datetime]:
        now = from_now or datetime.now()
        sched = self.schedule.strip().lower()

        if sched.startswith("daily "):
            hm = sched[6:].strip()          # "07:00"
            h, m = (int(x) for x in hm.split(":"))
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            self._next_fire = candidate
            return candidate

        if sched.startswith("interval "):
            secs = float(sched[9:].strip())
            self._next_fire = now + timedelta(seconds=secs)
            return self._next_fire

        # "manual" — no automatic fire
        self._next_fire = None
        return None

    @property
    def next_fire(self) -> Optional[datetime]:
        return self._next_fire

    def to_dict(self) -> dict:
        return {
            "job_id":    self.job_id,
            "label":     self.label,
            "schedule":  self.schedule,
            "status":    self.status.value,
            "last_run":  self.last_run.isoformat() if self.last_run else None,
            "next_fire": self._next_fire.isoformat() if self._next_fire else None,
            "run_count": self.run_count,
            "last_error": self.last_error,
        }


class AgentScheduler:
    """Async background scheduler.

    Args:
        tick_secs: How often the scheduler checks for due jobs (default 30s).
    """

    def __init__(self, tick_secs: float = 30.0) -> None:
        self._jobs:      Dict[str, ScheduledJob] = {}
        self._tick_secs  = tick_secs
        self._task:      Optional[asyncio.Task] = None
        self._callbacks: List[Callable[[str, dict], Coroutine]] = []

    # ── Job management ────────────────────────────────────────────────────────

    def register(
        self,
        job_id:   str,
        label:    str,
        fn:       Callable[[], Coroutine],
        schedule: str = "manual",
    ) -> ScheduledJob:
        job = ScheduledJob(job_id=job_id, label=label, fn=fn, schedule=schedule)
        job.compute_next_fire()
        self._jobs[job_id] = job
        logger.info(f"[Scheduler] Registered '{job_id}' ({schedule}) next={job.next_fire}")
        return job

    def unregister(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None

    def list_jobs(self) -> List[dict]:
        return [j.to_dict() for j in self._jobs.values()]

    def on_job_event(self, cb: Callable[[str, dict], Coroutine]) -> None:
        """Register callback called on job start/finish/error."""
        self._callbacks.append(cb)

    # ── Manual trigger ────────────────────────────────────────────────────────

    async def trigger(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        asyncio.create_task(self._run_job(job))
        return True

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("[Scheduler] Started")

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("[Scheduler] Stopped")

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._tick_secs)
                now = datetime.now()
                for job in list(self._jobs.values()):
                    if job.next_fire and now >= job.next_fire and job.status == JobStatus.IDLE:
                        asyncio.create_task(self._run_job(job))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[Scheduler] Loop error: {exc}")

    async def _run_job(self, job: ScheduledJob) -> None:
        if job.status == JobStatus.RUNNING:
            logger.warning(f"[Scheduler] '{job.job_id}' already running — skipped")
            return

        job.status   = JobStatus.RUNNING
        job.last_run = datetime.now()
        logger.info(f"[Scheduler] Running '{job.job_id}' ({job.label})")
        await self._emit("start", job)

        try:
            await job.fn()
            job.status    = JobStatus.IDLE
            job.run_count += 1
            job.last_error = ""
            logger.info(f"[Scheduler] '{job.job_id}' finished (run #{job.run_count})")
            await self._emit("done", job)
        except Exception as exc:
            job.status    = JobStatus.ERROR
            job.last_error = str(exc)
            logger.error(f"[Scheduler] '{job.job_id}' error: {exc}")
            await self._emit("error", job)
            job.status = JobStatus.IDLE  # reset so it can retry next cycle

        # Schedule next fire
        job.compute_next_fire()

    async def _emit(self, event: str, job: ScheduledJob) -> None:
        payload = {"event": event, **job.to_dict()}
        for cb in self._callbacks:
            try:
                await cb(job.job_id, payload)
            except Exception as exc:
                logger.error(f"[Scheduler] Callback error: {exc}")

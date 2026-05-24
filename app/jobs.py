"""In-process async job store for /detect mode='async'.

State is held in a module-level dict keyed by task_id. Jobs run as
asyncio.Tasks; results are kept for ``TTL_S`` after completion so
clients can poll until they collect, then are reaped.

This is deliberately not persistent. RelayProbe is a fire-and-poll tool
on the order of minutes per scan; if the container restarts mid-scan,
restarting the scan is the correct recovery. Persistence (SQLite,
Redis) was rejected as scope creep for v0.2 — see
docs/superpowers/specs/2026-05-24-relayprobe-async-detect-design.md.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from app.detector.types import DetectRequest, DetectResponse

log = logging.getLogger("detector.jobs")

# How long a completed/failed job sticks around before the reaper drops
# it. 1h is plenty for a 5s-poll client; for very slow consumers, the
# scan is cheap to re-run.
TTL_S = 3600.0

# Reaper sweep cadence. The TTL precision doesn't need to be tight.
REAPER_INTERVAL_S = 60.0


@dataclass
class JobRecord:
    task_id: str
    status: str  # "running" | "completed" | "failed"
    request: DetectRequest
    submitted_at: float
    result: DetectResponse | None = None
    error: str | None = None
    finished_at: float | None = None
    task: asyncio.Task | None = field(default=None, repr=False)


class JobStore:
    """Per-process job table. Safe for concurrent submit/get from a
    single asyncio event loop (no thread locking — uvicorn single-worker
    is the supported deployment).
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def submit(
        self,
        req: DetectRequest,
        runner: Callable[[DetectRequest], Awaitable[DetectResponse]],
    ) -> JobRecord:
        task_id = req.task_id or f"rp-{uuid.uuid4().hex[:16]}"
        if task_id in self._jobs:
            # Caller-supplied task_id collisions are their problem; we
            # don't silently merge.
            raise ValueError(f"task_id already in use: {task_id}")

        rec = JobRecord(
            task_id=task_id,
            status="running",
            request=req,
            submitted_at=time.time(),
        )
        self._jobs[task_id] = rec
        rec.task = asyncio.create_task(self._run(rec, runner))
        log.info("job submitted: task_id=%s model=%s", task_id, req.model)
        return rec

    def get(self, task_id: str) -> JobRecord | None:
        return self._jobs.get(task_id)

    def _drop(self, task_id: str) -> None:
        self._jobs.pop(task_id, None)

    async def _run(
        self,
        rec: JobRecord,
        runner: Callable[[DetectRequest], Awaitable[DetectResponse]],
    ) -> None:
        try:
            result = await runner(rec.request)
            rec.result = result
            rec.status = result.status if result.status in ("completed", "failed") else "completed"
        except asyncio.CancelledError:
            rec.status = "failed"
            rec.error = "cancelled"
            raise
        except Exception as e:
            log.exception("job failed: task_id=%s", rec.task_id)
            rec.status = "failed"
            rec.error = f"{type(e).__name__}: {e}"
        finally:
            rec.finished_at = time.time()

    def reap(self, now: float | None = None) -> int:
        """Drop finished jobs older than TTL_S. Returns count dropped."""
        now = now if now is not None else time.time()
        to_drop = [
            tid
            for tid, rec in self._jobs.items()
            if rec.finished_at is not None and (now - rec.finished_at) > TTL_S
        ]
        for tid in to_drop:
            self._drop(tid)
        if to_drop:
            log.info("reaped %d expired job(s)", len(to_drop))
        return len(to_drop)


# Module-level singleton wired into create_app()'s lifespan.
store = JobStore()


async def reaper_loop(interval_s: float = REAPER_INTERVAL_S) -> None:
    """Background task — sweeps expired jobs every ``interval_s``."""
    while True:
        try:
            await asyncio.sleep(interval_s)
            store.reap()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("reaper sweep failed; continuing")

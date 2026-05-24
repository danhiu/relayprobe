"""HTTP routes for synchronous and asynchronous detection.

- ``POST /detect`` with ``mode="sync"`` (default): blocks up to
  ``SYNC_TIMEOUT_S`` and returns the full DetectResponse. Behavior
  identical to v0.1; v0.2 left this path untouched for compatibility.
- ``POST /detect`` with ``mode="async"``: submits to an in-process job
  store and returns immediately with status="running" plus the task_id.
- ``GET /detect/{task_id}``: poll endpoint. Returns the current
  DetectResponse with status in {running, completed, failed}.
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.detector import run_detection
from app.detector.log_redact import redact
from app.detector.types import DetectRequest, DetectResponse, DimensionResult
from app.jobs import store

router = APIRouter()
log = logging.getLogger("detector.routes")

SYNC_TIMEOUT_S = 60.0


def _running_placeholder(task_id: str) -> DetectResponse:
    """Shape a DetectResponse for the not-yet-finished case.

    Pydantic requires score/verdict/summaries to be present. We fill
    safe defaults; clients should branch on ``status`` first and only
    consume the rest when status=="completed".
    """
    return DetectResponse(
        task_id=task_id,
        status="running",
        score=0,
        verdict="offline",
        summary_zh="检测进行中",
        summary_en="detection in progress",
        dimensions={},
        capability_flags={},
    )


def _failed_response(task_id: str, error: str) -> DetectResponse:
    return DetectResponse(
        task_id=task_id,
        status="failed",
        score=0,
        verdict="offline",
        summary_zh=f"检测失败：{error}",
        summary_en=f"detection failed: {error}",
        dimensions={
            "online": DimensionResult(
                name="online", score=0, status="error", error=error,
            )
        },
        capability_flags={},
        warnings=[error],
    )


@router.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest) -> DetectResponse:
    log.info(
        "detect request received: base=%s model=%s rounds=%s mode=%s",
        redact(req.base_url),
        req.model,
        req.rounds,
        req.mode,
    )

    if req.mode == "async":
        try:
            rec = store.submit(req, run_detection)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return _running_placeholder(rec.task_id)

    # Sync — preserves v0.1 behavior exactly.
    try:
        return await asyncio.wait_for(run_detection(req), timeout=SYNC_TIMEOUT_S)
    except TimeoutError as e:
        raise HTTPException(
            status_code=408,
            detail="detection exceeded 60s; use mode='async' for long runs",
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/detect/{task_id}", response_model=DetectResponse)
async def get_detect(task_id: str) -> DetectResponse:
    rec = store.get(task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")

    if rec.status == "completed" and rec.result is not None:
        return rec.result
    if rec.status == "failed":
        if rec.result is not None:
            return rec.result
        return _failed_response(rec.task_id, rec.error or "unknown error")
    return _running_placeholder(rec.task_id)

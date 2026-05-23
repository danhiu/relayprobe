import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.detector import run_detection
from app.detector.log_redact import redact
from app.detector.types import DetectRequest, DetectResponse

router = APIRouter()
log = logging.getLogger("detector.routes")

SYNC_TIMEOUT_S = 60.0


@router.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest) -> DetectResponse:
    log.info(
        "detect request received: base=%s model=%s rounds=%s",
        redact(req.base_url),
        req.model,
        req.rounds,
    )
    try:
        return await asyncio.wait_for(run_detection(req), timeout=SYNC_TIMEOUT_S)
    except TimeoutError as e:
        raise HTTPException(
            status_code=408,
            detail="detection exceeded 60s; use mode='async' for long runs",
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

import time

from fastapi import APIRouter

router = APIRouter()
_START = time.monotonic()


@router.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_s": int(time.monotonic() - _START),
    }

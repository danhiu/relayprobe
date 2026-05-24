import time

from fastapi import APIRouter

from app import __version__ as version

router = APIRouter()
_START = time.monotonic()


@router.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "version": version,
        "uptime_s": int(time.monotonic() - _START),
    }

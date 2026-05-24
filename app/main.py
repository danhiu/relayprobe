"""FastAPI application factory + uvicorn entry."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__ as version
from app.detector.log_redact import install_global_filter
from app.jobs import reaper_loop
from app.routes.detect import router as detect_router
from app.routes.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    reaper = asyncio.create_task(reaper_loop())
    try:
        yield
    finally:
        reaper.cancel()
        try:
            await reaper
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    install_global_filter()
    app = FastAPI(title="AI Relay Detector", version=version, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(detect_router)
    return app


app = create_app()

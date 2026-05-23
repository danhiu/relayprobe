"""FastAPI application factory + uvicorn entry."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.detector.log_redact import install_global_filter
from app.routes.detect import router as detect_router
from app.routes.health import router as health_router


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    install_global_filter()
    app = FastAPI(title="AI Relay Detector", version="0.1.0")
    app.include_router(health_router)
    app.include_router(detect_router)
    return app


app = create_app()

"""Detector core library — pure Python, no FastAPI deps."""
from app.detector.baselines import load_baselines
from app.detector.core import run_detection
from app.detector.types import DetectRequest, DetectResponse

__all__ = ["run_detection", "load_baselines", "DetectRequest", "DetectResponse"]

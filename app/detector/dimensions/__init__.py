"""Dimension registry — list order is also presentation order."""
from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.dimensions.identity_consistency import IdentityConsistency
from app.detector.dimensions.injection_safety import InjectionSafety
from app.detector.dimensions.online import Online
from app.detector.dimensions.token_billing import TokenBilling
from app.detector.dimensions.tool_use import ToolUse
from app.detector.dimensions.wrapper_detection import WrapperDetection

ALL_DIMENSIONS: list[type[Dimension]] = [
    Online,
    IdentityConsistency,
    WrapperDetection,
    TokenBilling,
    ToolUse,
    InjectionSafety,
]

__all__ = [
    "ALL_DIMENSIONS",
    "Dimension",
    "DimensionContext",
    "Online",
    "IdentityConsistency",
    "WrapperDetection",
    "TokenBilling",
    "ToolUse",
    "InjectionSafety",
]

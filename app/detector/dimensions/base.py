"""Dimension ABC. Each dimension is a self-contained probe that takes a context
(adapter + baseline + budget + RNG) and returns a DimensionResult."""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.detector.adapters.base import Adapter
from app.detector.baselines import Baseline
from app.detector.budget import BudgetTracker
from app.detector.types import DimensionResult, RoundLog


@dataclass
class DimensionContext:
    adapter: Adapter
    baseline: Baseline
    budget: BudgetTracker
    rng: random.Random
    rounds_log: list[RoundLog]
    rounds: int  # caller-requested round budget across all dimensions


class Dimension(ABC):
    name: str  # subclass sets this
    weight: float  # subclass sets this (used by scoring)

    @abstractmethod
    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        ...

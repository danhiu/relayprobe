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
    # Identifier sent on the wire to the upstream relay. Often equals
    # ``baseline.name`` but diverges when the relay publishes the model
    # under an alias / dated / runtime-knob suffix (e.g. caller passes
    # ``gpt-5.5`` which resolves to baseline ``gpt-5-5`` but must still
    # be the model field upstream sees).
    target_model: str
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

"""Top-level detection orchestrator. Used by both HTTP routes and CLI."""
from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path

from app.detector.adapters import get_adapter
from app.detector.adapters.base import Adapter
from app.detector.baselines import load_baselines
from app.detector.budget import BudgetExceeded, BudgetTracker
from app.detector.dimensions import ALL_DIMENSIONS
from app.detector.dimensions.base import DimensionContext
from app.detector.scoring import aggregate, summarize
from app.detector.types import (
    ChatResult,
    DetectRequest,
    DetectResponse,
    DimensionResult,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "data" / "mock_responses"


class _MockAdapter:
    """Returns canned responses from a fixture file. Used when dry_run=True."""

    def __init__(self, fixture_name: str, provider: str):
        with open(FIXTURES_DIR / fixture_name, encoding="utf-8") as f:
            self._data = json.load(f)
        self.provider = provider

    async def list_models(self):
        return list(self._data.get("list_models", []))

    async def chat(self, model, messages, max_tokens=256, temperature=0.0):
        d = self._data["chat"]
        return ChatResult(
            text=d["text"],
            prompt_tokens=d["prompt_tokens"],
            completion_tokens=d["completion_tokens"],
            total_latency_ms=d["total_latency_ms"],
            tool_calls=d.get("tool_calls", []),
            raw=d.get("raw", d),
        )

    async def chat_with_tools(
        self, model, messages, tools, max_tokens=256, temperature=0.0
    ):
        d = self._data["chat_with_tools"]
        return ChatResult(
            text=d["text"],
            prompt_tokens=d["prompt_tokens"],
            completion_tokens=d["completion_tokens"],
            total_latency_ms=d["total_latency_ms"],
            tool_calls=d.get("tool_calls", []),
            raw=d.get("raw", d),
        )


def _resolve_provider(model: str, override: str | None) -> str:
    if override:
        return override
    baselines = load_baselines()
    baseline = baselines.resolve(model)
    if baseline is None:
        raise ValueError(f"unknown model: {model!r}")
    return baseline.provider


def _build_adapter(req: DetectRequest, provider: str) -> Adapter | _MockAdapter:
    if req.dry_run:
        # provider -> default authentic fixture
        return _MockAdapter(
            fixture_name=f"{provider}_authentic.json", provider=provider
        )
    return get_adapter(provider, base_url=req.base_url, api_key=req.api_key)


async def run_detection(req: DetectRequest) -> DetectResponse:
    started = time.monotonic()
    task_id = req.task_id or uuid.uuid4().hex
    baselines = load_baselines()

    baseline = baselines.resolve(req.model)
    if baseline is None:
        raise ValueError(f"unknown model: {req.model!r}")

    provider = _resolve_provider(req.model, req.expected_provider)
    adapter = _build_adapter(req, provider)
    budget = BudgetTracker(budget_usd=req.budget_usd)
    rng = random.Random()

    rounds_log: list = []
    ctx = DimensionContext(
        adapter=adapter,
        baseline=baseline,
        # The caller's original identifier is what the upstream sees on
        # the wire. Resolution above only chooses the scoring baseline.
        target_model=req.model,
        budget=budget,
        rng=rng,
        rounds_log=rounds_log,
        rounds=req.rounds,
    )

    results: dict[str, DimensionResult] = {}
    over_budget = False
    warnings: list[str] = []

    for cls in ALL_DIMENSIONS:
        dim = cls()

        # short-circuit: if online failed, mark every later dim as skipped
        if (
            dim.name != "online"
            and "online" in results
            and results["online"].status == "missing"
        ):
            results[dim.name] = DimensionResult(
                name=dim.name, score=0, status="skipped",
                evidence={"reason": "online check failed; downstream skipped"},
            )
            continue

        try:
            r = await dim.evaluate(ctx)
        except BudgetExceeded as e:
            over_budget = True
            warnings.append(f"budget exceeded during {dim.name}: {e}")
            r = DimensionResult(
                name=dim.name, score=0, status="error",
                evidence={"budget_exceeded": True}, error=str(e),
            )
        except Exception as e:
            r = DimensionResult(
                name=dim.name, score=0, status="error",
                evidence={"unexpected_error": True}, error=str(e),
            )
        results[dim.name] = r

    score, verdict = aggregate(results)
    summary_zh, summary_en = summarize(
        results, score=score, verdict=verdict, model=req.model
    )

    capability_flags = {
        n: results[n].status if n in results else "skipped"
        for n in ("tool_use", "wrapper_detection")
    }

    duration_ms = int((time.monotonic() - started) * 1000)

    return DetectResponse(
        task_id=task_id,
        status="completed",
        score=score,
        verdict=verdict,
        summary_zh=summary_zh,
        summary_en=summary_en,
        dimensions=results,
        capability_flags=capability_flags,
        rounds_log=rounds_log if req.verbose else rounds_log[:20],
        actual_cost_usd=round(budget.spent_usd, 6),
        duration_ms=duration_ms,
        over_budget=over_budget,
        warnings=warnings,
    )

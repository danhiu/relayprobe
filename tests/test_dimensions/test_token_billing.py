import random
from unittest.mock import AsyncMock

from app.detector.baselines import load_baselines
from app.detector.budget import BudgetTracker
from app.detector.dimensions.base import DimensionContext
from app.detector.dimensions.token_billing import TokenBilling
from app.detector.types import ChatResult


def _ctx(adapter):
    baseline = load_baselines()["claude-opus-4-7"]
    return DimensionContext(
        adapter=adapter,
        baseline=baseline,
        budget=BudgetTracker(budget_usd=1.0),
        rng=random.Random(0),
        rounds_log=[],
        rounds=11,
    )


# Fixed prompt "Repeat after me: hello world" tokenizes to a small known count.
# We don't compute exact ground-truth — we test deviation behavior.

async def test_no_deviation_when_token_counts_close_to_expected():
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=8,
        completion_tokens=2,
        total_latency_ms=100,
        raw={"usage": {"input_tokens": 8, "output_tokens": 2}},
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.status == "ok"
    assert result.score >= 90
    assert result.evidence["deviation_pct"] < 15.0


async def test_high_deviation_flagged():
    adapter = AsyncMock()
    # Massively inflated: prompt_tokens=200 vs expected 9 -> 2122% deviation
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=200,
        completion_tokens=2,
        total_latency_ms=100,
        raw={"usage": {"input_tokens": 200, "output_tokens": 2}},
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.status == "missing"
    assert result.score == 0
    assert result.evidence["deviation_pct"] > 300.0


async def test_zero_tokens_marked_error():
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=0,
        completion_tokens=0,
        total_latency_ms=100,
        raw={"usage": {"input_tokens": 0, "output_tokens": 0}},
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.status == "error"


async def test_cache_read_excluded_from_effective_input():
    # Wrapper relay: input_tokens=9 (your actual prompt), cache_read=2516 (their system prompt).
    # Effective should be 9 -> 0% deviation -> ok 100
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=9,
        completion_tokens=2,
        total_latency_ms=100,
        raw={"usage": {
            "input_tokens": 9,
            "cache_read_input_tokens": 2516,
            "cache_creation_input_tokens": 0,
            "output_tokens": 2,
        }},
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.status == "ok"
    assert result.score == 100
    assert result.evidence["observed_median_cache_read"] == 2516
    assert result.evidence["observed_median_effective"] == 9


async def test_moderate_inflation_degraded():
    # 16 tokens vs expected 9 = 78% deviation -> degraded 60
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=16,
        completion_tokens=2,
        total_latency_ms=100,
        raw={"usage": {"input_tokens": 16, "output_tokens": 2}},
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.status == "degraded"
    assert result.score == 60

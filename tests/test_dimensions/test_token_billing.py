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
        target_model=baseline.name,
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


async def test_stable_inflation_floored_not_zeroed():
    """A relay that prepends a fixed-size system prompt produces an
    identical effective_input on every round. wrapper_detection already
    catches the constant overhead, so token_billing must not zero-out
    here — the model itself can still be authentic. The ladder bottoms
    out at 50 for huge stable wrappers, never 0."""
    adapter = AsyncMock()
    # 200 tokens every round -> stable across 3 rounds -> inflation 191
    # New ladder: stable + 50-200 inflation -> 75 ("small wrapper")
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=200,
        completion_tokens=2,
        total_latency_ms=100,
        raw={"usage": {"input_tokens": 200, "output_tokens": 2}},
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.evidence["stable_across_rounds"] is True
    assert result.evidence["inflation_tokens"] == 200 - 9
    assert result.score == 75
    assert result.status == "ok"


async def test_stable_huge_wrapper_floors_at_50():
    """Even a Kiro-class 1500-token wrapper, when stable, only drops the
    score to 50 in this dimension — wrapper_detection takes the brunt."""
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=1500,
        completion_tokens=2,
        total_latency_ms=100,
        raw={"usage": {"input_tokens": 1500, "output_tokens": 2}},
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.evidence["stable_across_rounds"] is True
    assert result.score == 50
    assert result.status == "degraded"


async def test_unstable_high_deviation_keeps_zero():
    """When token counts vary across rounds (real per-prompt counting,
    just against the wrong tokenizer), the aggressive ladder still
    applies — that's the strong "different model" signal."""
    adapter = AsyncMock()
    counts = iter([180, 215, 240])  # range = 60, far above the stability tolerance
    def _next(model, messages, max_tokens):  # noqa: ARG001
        n = next(counts)
        return ChatResult(
            text="hello world",
            prompt_tokens=n,
            completion_tokens=2,
            total_latency_ms=100,
            raw={"usage": {"input_tokens": n, "output_tokens": 2}},
        )
    adapter.chat.side_effect = _next
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.evidence["stable_across_rounds"] is False
    # median 215 / expected 9 -> 2289% deviation, unstable -> 0/missing
    assert result.score == 0
    assert result.status == "missing"


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


async def test_small_stable_overhead_keeps_high_score():
    """A small "be helpful" preamble (< 50 token overhead) is normal
    and should not drag the score: 90/ok, not 60."""
    # 16 tokens vs expected 9 = 78% deviation but only +7 absolute
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=16,
        completion_tokens=2,
        total_latency_ms=100,
        raw={"usage": {"input_tokens": 16, "output_tokens": 2}},
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.evidence["stable_across_rounds"] is True
    assert result.evidence["inflation_tokens"] == 7
    assert result.score == 90
    assert result.status == "ok"

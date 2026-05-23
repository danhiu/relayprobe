import random
from unittest.mock import AsyncMock

from app.detector.baselines import load_baselines
from app.detector.budget import BudgetTracker
from app.detector.dimensions.base import DimensionContext
from app.detector.dimensions.wrapper_detection import WrapperDetection
from app.detector.types import ChatResult


def _ctx(adapter):
    baseline = load_baselines()["claude-sonnet-4-6"]
    return DimensionContext(
        adapter=adapter,
        baseline=baseline,
        budget=BudgetTracker(budget_usd=1.0),
        rng=random.Random(0),
        rounds_log=[],
        rounds=11,
    )


async def test_clean_no_injection():
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="Hi!",
        prompt_tokens=5, completion_tokens=2, total_latency_ms=100,
        raw={"usage": {"input_tokens": 5, "output_tokens": 2}},
    )
    result = await WrapperDetection().evaluate(_ctx(adapter))
    assert result.status == "ok"
    assert result.score == 100
    assert result.evidence["injection_size"] == 0


async def test_kiro_class_heavy_wrapper_flagged():
    # cache_read 2516 = AWS Kiro signature
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="Hi!",
        prompt_tokens=5, completion_tokens=2, total_latency_ms=100,
        raw={"usage": {
            "input_tokens": 5, "cache_read_input_tokens": 2516,
            "cache_creation_input_tokens": 0, "output_tokens": 2,
        }},
    )
    result = await WrapperDetection().evaluate(_ctx(adapter))
    assert result.status == "missing"
    assert result.score == 0
    interp = result.evidence["interpretation"]
    assert "Kiro" in interp or "heavy" in interp


async def test_medium_wrapper_degraded():
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="Hi!",
        prompt_tokens=5, completion_tokens=2, total_latency_ms=100,
        raw={"usage": {
            "input_tokens": 5, "cache_read_input_tokens": 800,
            "cache_creation_input_tokens": 0, "output_tokens": 2,
        }},
    )
    result = await WrapperDetection().evaluate(_ctx(adapter))
    assert result.status == "degraded"
    assert result.score == 30


async def test_light_wrapper_warning():
    # small preamble injected — visible as inflated effective_input but no cache
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="Hi!",
        prompt_tokens=200, completion_tokens=2, total_latency_ms=100,
        raw={"usage": {"input_tokens": 200, "output_tokens": 2}},
    )
    result = await WrapperDetection().evaluate(_ctx(adapter))
    assert result.status == "degraded"
    assert result.score == 70

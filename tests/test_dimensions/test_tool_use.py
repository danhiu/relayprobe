import random
from unittest.mock import AsyncMock

from app.detector.baselines import load_baselines
from app.detector.budget import BudgetTracker
from app.detector.dimensions.base import DimensionContext
from app.detector.dimensions.tool_use import ToolUse
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


async def test_proper_tool_call_returns_ok():
    adapter = AsyncMock()
    adapter.chat_with_tools.return_value = ChatResult(
        text="",
        prompt_tokens=20, completion_tokens=8, total_latency_ms=200,
        tool_calls=[{"name": "get_weather", "arguments": {"location": "Tokyo"}}],
    )
    result = await ToolUse().evaluate(_ctx(adapter))
    assert result.status == "ok"
    assert result.score == 100


async def test_text_only_response_marked_degraded():
    adapter = AsyncMock()
    adapter.chat_with_tools.return_value = ChatResult(
        text="I would call the get_weather tool with location Tokyo.",
        prompt_tokens=20, completion_tokens=15, total_latency_ms=200,
        tool_calls=[],
    )
    result = await ToolUse().evaluate(_ctx(adapter))
    assert result.status == "degraded"
    assert result.score == 40


async def test_error_response_marked_missing():
    adapter = AsyncMock()
    adapter.chat_with_tools.side_effect = RuntimeError("tools not supported by upstream")
    result = await ToolUse().evaluate(_ctx(adapter))
    assert result.status == "missing"
    assert result.score == 0
    assert "tools not supported" in result.error


async def test_tool_call_with_wrong_args_partial_credit():
    adapter = AsyncMock()
    adapter.chat_with_tools.return_value = ChatResult(
        text="",
        prompt_tokens=20, completion_tokens=8, total_latency_ms=200,
        # called the right tool but missing required `location` arg
        tool_calls=[{"name": "get_weather", "arguments": {}}],
    )
    result = await ToolUse().evaluate(_ctx(adapter))
    assert result.status == "degraded"
    assert 40 <= result.score < 100

import random
from unittest.mock import AsyncMock

import httpx

from app.detector.baselines import load_baselines
from app.detector.budget import BudgetTracker
from app.detector.dimensions.base import DimensionContext
from app.detector.dimensions.online import Online
from app.detector.types import ChatResult


def _make_ctx(adapter):
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


async def test_online_when_models_and_chat_succeed():
    adapter = AsyncMock()
    adapter.list_models.return_value = ["claude-opus-4-7"]
    adapter.chat.return_value = ChatResult(
        text="hi", prompt_tokens=2, completion_tokens=1, total_latency_ms=100
    )
    result = await Online().evaluate(_make_ctx(adapter))
    assert result.score == 100
    assert result.status == "ok"
    assert result.evidence["models_endpoint_ok"] is True
    assert result.evidence["chat_endpoint_ok"] is True


async def test_online_when_models_endpoint_fails_but_chat_ok():
    adapter = AsyncMock()
    adapter.list_models.side_effect = httpx.HTTPError("404")
    adapter.chat.return_value = ChatResult(
        text="hi", prompt_tokens=2, completion_tokens=1, total_latency_ms=100
    )
    result = await Online().evaluate(_make_ctx(adapter))
    # chat succeeded, so still online but degraded
    assert result.status == "ok"
    assert result.evidence["models_endpoint_ok"] is False
    assert result.evidence["chat_endpoint_ok"] is True
    assert result.score < 100


async def test_online_when_chat_fails():
    adapter = AsyncMock()
    adapter.list_models.return_value = []
    adapter.chat.side_effect = httpx.HTTPError("connection refused")
    result = await Online().evaluate(_make_ctx(adapter))
    assert result.status == "missing"
    assert result.score == 0
    assert "connection refused" in result.evidence["error"]

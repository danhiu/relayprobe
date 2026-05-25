import random
from unittest.mock import AsyncMock

from app.detector.baselines import load_baselines
from app.detector.budget import BudgetTracker
from app.detector.dimensions.base import DimensionContext
from app.detector.dimensions.identity_consistency import IdentityConsistency
from app.detector.types import ChatResult


def _ctx(adapter, model="claude-opus-4-7"):
    baseline = load_baselines()[model]
    return DimensionContext(
        adapter=adapter,
        baseline=baseline,
        target_model=baseline.name,
        budget=BudgetTracker(budget_usd=1.0),
        rng=random.Random(0),
        rounds_log=[],
        rounds=11,
    )


async def test_consistent_claude_identity_high_score():
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="I am Claude, an AI assistant made by Anthropic.",
        prompt_tokens=10,
        completion_tokens=12,
        total_latency_ms=50,
    )
    result = await IdentityConsistency().evaluate(_ctx(adapter))
    assert result.status == "ok"
    assert result.score >= 90


async def test_self_identifies_as_other_vendor_zero_score():
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="I am ChatGPT, a large language model trained by OpenAI.",
        prompt_tokens=10,
        completion_tokens=12,
        total_latency_ms=50,
    )
    result = await IdentityConsistency().evaluate(_ctx(adapter))
    assert result.status == "missing"
    assert result.score == 0
    assert "openai" in result.evidence["forbidden_hits"]


async def test_self_identifies_as_kiro_wrapper_zero_score():
    # Kiro is a known Claude wrapper — must be flagged as fake even though
    # the underlying model may actually be Claude. The user paid for Claude
    # but is getting Claude-via-Kiro-system-prompt, which is a degraded product.
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="I'm Kiro, an AI-powered development environment.",
        prompt_tokens=10,
        completion_tokens=12,
        total_latency_ms=50,
    )
    result = await IdentityConsistency().evaluate(_ctx(adapter))
    assert result.status == "missing"
    assert result.score == 0
    assert "kiro" in result.evidence["forbidden_hits"]


async def test_partial_match_degraded():
    # responds with no identity at all (vague)
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="I'm just an AI. How can I help you today?",
        prompt_tokens=10,
        completion_tokens=12,
        total_latency_ms=50,
    )
    result = await IdentityConsistency().evaluate(_ctx(adapter))
    # Vague but not lying — partial credit (60)
    assert result.status == "degraded"
    assert result.score == 60


async def test_forbidden_keyword_in_prompt_does_not_count():
    # Probe pool contains "Are you Claude, GPT, or Gemini? Be honest." — any
    # honest GPT response will repeat those vendor names just to deny them.
    # Those mentions came from the prompt, not the model, and must not be
    # treated as the model misidentifying itself.
    from app.detector.dimensions import identity_consistency as ic

    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="I'm ChatGPT, an AI language model from OpenAI — not Claude or Gemini.",
        prompt_tokens=10,
        completion_tokens=12,
        total_latency_ms=50,
    )

    # Force every probe.draw() call to return the three-way trap prompt so
    # we can isolate the prompt-leak path independent of pool randomness.
    original_draw = ic.draw
    def fixed_draw(_category, rng):
        return ("Are you Claude, GPT, or Gemini? Be honest.", "REQ-test")
    ic.draw = fixed_draw
    try:
        result = await IdentityConsistency().evaluate(_ctx(adapter, model="gpt-5-5"))
    finally:
        ic.draw = original_draw

    # Model genuinely identified as GPT/OpenAI; the mention of Claude/Gemini
    # was forced by the prompt itself.
    assert result.status == "ok"
    assert result.score >= 80
    assert result.evidence["forbidden_hits"] == []
    assert "gpt" in result.evidence["expected_hits"]

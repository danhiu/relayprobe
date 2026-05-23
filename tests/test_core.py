import pytest

from app.detector.core import run_detection
from app.detector.types import DetectRequest


async def test_dry_run_authentic_anthropic():
    req = DetectRequest(
        base_url="https://x.example",
        api_key="sk-test",
        model="claude-opus-4-7",
        rounds=11,
        budget_usd=0.5,
        dry_run=True,
    )
    resp = await run_detection(req)
    assert resp.status == "completed"
    assert resp.score >= 90
    assert resp.verdict == "authentic"
    assert resp.dimensions["online"].status == "ok"
    assert resp.dimensions["tool_use"].status == "ok"
    assert resp.actual_cost_usd >= 0
    assert resp.duration_ms >= 0
    assert "claude" in resp.summary_zh.lower() or "claude" in resp.summary_zh


async def test_unknown_model_raises_validation():
    req = DetectRequest(
        base_url="https://x.example",
        api_key="sk-test",
        model="no-such-model",
        rounds=11,
        dry_run=True,
    )
    with pytest.raises(ValueError, match="unknown model"):
        await run_detection(req)


async def test_budget_exceeded_returns_partial_with_flag():
    # budget too small to even complete identity probes
    req = DetectRequest(
        base_url="https://x.example",
        api_key="sk-test",
        model="claude-opus-4-7",
        rounds=11,
        budget_usd=0.0000001,
        dry_run=True,
    )
    resp = await run_detection(req)
    assert resp.over_budget is True
    # partial result still returned, not crash
    assert resp.task_id

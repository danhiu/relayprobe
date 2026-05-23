from app.detector.scoring import aggregate, summarize
from app.detector.types import DimensionResult


def _r(name, score, status="ok"):
    return DimensionResult(name=name, score=score, status=status, evidence={})


def test_offline_short_circuit():
    results = {
        "online": _r("online", 0, status="missing"),
        "identity_consistency": _r("identity_consistency", 95),
        "token_billing": _r("token_billing", 90),
        "tool_use": _r("tool_use", 100),
    }
    score, verdict = aggregate(results)
    assert score == 0
    assert verdict == "offline"


def test_all_high_authentic():
    results = {
        "online": _r("online", 100),
        "identity_consistency": _r("identity_consistency", 95),
        "token_billing": _r("token_billing", 95),
        "tool_use": _r("tool_use", 100),
    }
    score, verdict = aggregate(results)
    assert score >= 90
    assert verdict == "authentic"


def test_likely_authentic_band():
    results = {
        "online": _r("online", 100),
        "identity_consistency": _r("identity_consistency", 80),
        "token_billing": _r("token_billing", 75),
        "tool_use": _r("tool_use", 80),
    }
    score, verdict = aggregate(results)
    assert 75 <= score < 90
    assert verdict == "likely_authentic"


def test_suspicious_band():
    results = {
        "online": _r("online", 100),
        "identity_consistency": _r("identity_consistency", 50),
        "token_billing": _r("token_billing", 50),
        "tool_use": _r("tool_use", 60),
    }
    score, verdict = aggregate(results)
    assert 50 <= score < 75
    assert verdict == "suspicious"


def test_likely_fake_band():
    results = {
        "online": _r("online", 100),
        "identity_consistency": _r("identity_consistency", 0, status="missing"),
        "token_billing": _r("token_billing", 30, status="degraded"),
        "tool_use": _r("tool_use", 0, status="missing"),
    }
    score, verdict = aggregate(results)
    assert score < 50
    assert verdict == "likely_fake"


def test_skipped_dimension_renormalizes_weights():
    results = {
        "online": _r("online", 100),
        "identity_consistency": _r("identity_consistency", 100),
        "token_billing": _r("token_billing", 100),
        "tool_use": _r("tool_use", 0, status="skipped"),  # exclude from sum
    }
    score, _ = aggregate(results)
    # tool_use skipped -> score should be 100 across remaining 3
    assert score == 100


def test_summarize_returns_zh_and_en():
    results = {
        "online": _r("online", 100),
        "identity_consistency": _r("identity_consistency", 95),
        "token_billing": _r("token_billing", 90),
        "tool_use": _r("tool_use", 100),
    }
    zh, en = summarize(results, score=95, verdict="authentic", model="claude-opus-4-7")
    assert isinstance(zh, str) and len(zh) > 5
    assert isinstance(en, str) and len(en) > 5
    assert "claude-opus-4-7" in zh or "Claude" in zh

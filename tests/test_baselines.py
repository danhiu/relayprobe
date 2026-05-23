import pytest

from app.detector.baselines import Baseline, load_baselines


def test_load_baselines_returns_dict():
    baselines = load_baselines()
    assert isinstance(baselines, dict)
    assert "claude-opus-4-7" in baselines


def test_baseline_has_required_fields():
    baselines = load_baselines()
    b = baselines["claude-opus-4-7"]
    assert isinstance(b, Baseline)
    assert b.provider == "anthropic"
    assert "claude" in b.expected_identity_keywords
    assert b.supports["tool_use"] is True


def test_unknown_model_lookup_raises():
    baselines = load_baselines()
    with pytest.raises(KeyError):
        baselines["no-such-model"]


def test_all_required_v01_models_present():
    baselines = load_baselines()
    required = {
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "gpt-5-5",
        "gpt-5-4",
        "gemini-3-1-pro",
    }
    assert required.issubset(baselines.keys())

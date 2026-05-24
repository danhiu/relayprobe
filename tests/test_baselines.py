"""Tests for the BaselinesIndex (load + resolve)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.detector.baselines import (
    BASELINES_PATH,
    Baseline,
    BaselinesIndex,
    load_baselines,
)


# ---------------------------------------------------------------------------
# Production catalog smoke tests
# ---------------------------------------------------------------------------


def test_load_baselines_returns_index():
    idx = load_baselines()
    assert isinstance(idx, BaselinesIndex)
    assert "claude-opus-4-7" in idx


def test_baseline_has_required_fields():
    idx = load_baselines()
    b = idx["claude-opus-4-7"]
    assert isinstance(b, Baseline)
    assert b.provider == "anthropic"
    assert "claude" in b.expected_identity_keywords
    assert b.supports["tool_use"] is True
    assert isinstance(b.aliases, list)


def test_unknown_canonical_lookup_raises():
    idx = load_baselines()
    with pytest.raises(KeyError):
        idx["no-such-model"]


def test_all_required_v01_models_present():
    idx = load_baselines()
    required = {
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "gpt-5-5",
        "gpt-5-4",
        "gemini-3-1-pro",
    }
    assert required.issubset(set(idx.keys()))


def test_runtime_suffixes_normalised():
    idx = load_baselines()
    # Every entry must start with a leading dash and be lowercase.
    for s in idx.runtime_suffixes:
        assert s.startswith("-")
        assert s == s.lower()


# ---------------------------------------------------------------------------
# Resolver: built off a fixture so the test owns its inputs
# ---------------------------------------------------------------------------


def _fixture_index() -> BaselinesIndex:
    """A minimal in-memory catalog covering every resolution rule.

    We do *not* load the production yaml here — relying on the real file
    means the test can pass purely because someone added an alias
    upstream. Constructing the catalog inline gives us a property-based
    sanity check on :meth:`BaselinesIndex.resolve` regardless of what's
    shipped to users.
    """
    raw = {
        "runtime_suffixes": ["-thinking", "-low", "-medium", "-high"],
        "dated_suffix_pattern": r"-\d{8}$",
        "models": {
            "claude-opus-4-7": {
                "aliases": [],
                "provider": "anthropic",
                "expected_identity_keywords": ["claude"],
                "forbidden_identity_keywords": ["gpt"],
                "expected_tokens_per_second": 30,
                "expected_latency_p50_ms": 1500,
                "tokenizer": "anthropic",
                "supports": {"tool_use": True},
            },
            "gpt-5-5": {
                "aliases": ["gpt-5.5"],
                "provider": "openai",
                "expected_identity_keywords": ["gpt"],
                "forbidden_identity_keywords": ["claude"],
                "expected_tokens_per_second": 80,
                "expected_latency_p50_ms": 700,
                "tokenizer": "openai",
                "supports": {"tool_use": True},
            },
            "gemini-3-1-pro": {
                "aliases": ["gemini-3.1-pro"],
                "provider": "google",
                "expected_identity_keywords": ["gemini"],
                "forbidden_identity_keywords": ["claude"],
                "expected_tokens_per_second": 70,
                "expected_latency_p50_ms": 1100,
                "tokenizer": "google",
                "supports": {"tool_use": True},
            },
        },
    }
    return BaselinesIndex.from_dict(raw)


def test_resolve_exact_canonical():
    idx = _fixture_index()
    assert idx.resolve("claude-opus-4-7").name == "claude-opus-4-7"


def test_resolve_alias_dotted_form():
    idx = _fixture_index()
    # The relay we're targeting publishes it with a dot; resolution must
    # still pick the dashed canonical baseline.
    assert idx.resolve("gpt-5.5").name == "gpt-5-5"
    assert idx.resolve("gemini-3.1-pro").name == "gemini-3-1-pro"


def test_resolve_runtime_suffix_strip():
    idx = _fixture_index()
    # `-thinking` is a runtime knob, not a different SKU; resolves to the
    # underlying baseline.
    assert idx.resolve("claude-opus-4-7-thinking").name == "claude-opus-4-7"
    assert idx.resolve("gemini-3.1-pro-low").name == "gemini-3-1-pro"


def test_resolve_stacked_suffixes():
    idx = _fixture_index()
    # Stacked runtime knobs (hypothetical) — resolver loops until no
    # known suffix remains.
    assert idx.resolve("gpt-5.5-thinking-high").name == "gpt-5-5"


def test_resolve_dated_suffix():
    idx = _fixture_index()
    assert idx.resolve("claude-opus-4-7-20251101").name == "claude-opus-4-7"


def test_resolve_dated_suffix_only_when_prefix_known():
    idx = _fixture_index()
    # A trailing 8-digit chunk on a non-baseline name must NOT be chopped
    # off and accepted — that would let `whatever-12345678` masquerade as
    # `whatever`.
    assert idx.resolve("phantom-model-20251101") is None


def test_resolve_unknown_returns_none():
    idx = _fixture_index()
    assert idx.resolve("claude-opus-4-1") is None  # no baseline yet
    assert idx.resolve("gpt-6") is None
    assert idx.resolve("") is None


def test_resolve_is_case_insensitive():
    idx = _fixture_index()
    assert idx.resolve("CLAUDE-OPUS-4-7").name == "claude-opus-4-7"
    assert idx.resolve("GPT-5.5").name == "gpt-5-5"


def test_resolve_strips_whitespace():
    idx = _fixture_index()
    assert idx.resolve("  gpt-5.5  ").name == "gpt-5-5"


def test_is_supported_matches_resolve():
    idx = _fixture_index()
    assert idx.is_supported("gpt-5.5") is True
    assert idx.is_supported("not-real") is False


def test_alias_collision_rejected():
    """Two baselines claiming the same alias should fail loudly at load
    time, not silently shadow each other at resolve time."""
    raw = {
        "runtime_suffixes": [],
        "dated_suffix_pattern": r"-\d{8}$",
        "models": {
            "model-a": {
                "aliases": ["shared"],
                "provider": "openai",
                "expected_identity_keywords": [],
                "forbidden_identity_keywords": [],
                "expected_tokens_per_second": 1,
                "expected_latency_p50_ms": 1,
                "tokenizer": "openai",
                "supports": {},
            },
            "model-b": {
                "aliases": ["shared"],
                "provider": "openai",
                "expected_identity_keywords": [],
                "forbidden_identity_keywords": [],
                "expected_tokens_per_second": 1,
                "expected_latency_p50_ms": 1,
                "tokenizer": "openai",
                "supports": {},
            },
        },
    }
    with pytest.raises(ValueError, match="collision"):
        BaselinesIndex.from_dict(raw)


# ---------------------------------------------------------------------------
# Production yaml resolver: at least confirm the known yyc-side names
# resolve. These guard against the v0.2 regression.
# ---------------------------------------------------------------------------


def test_production_yaml_resolves_known_yyc_aliases():
    idx = load_baselines()
    assert idx.resolve("gpt-5.5") is not None
    assert idx.resolve("gpt-5.4") is not None
    assert idx.resolve("gemini-3.1-pro") is not None
    assert idx.resolve("gemini-3.1-pro-low") is not None
    assert idx.resolve("claude-opus-4-7-thinking") is not None


def test_production_yaml_unsupported_models_stay_unsupported():
    idx = load_baselines()
    # Memory: yyc-pricing-audit-2026-05-23 — explicit "don't fake what
    # we don't have". claude-opus-4-1 is the canonical example.
    assert idx.resolve("claude-opus-4-1") is None
    assert idx.resolve("gpt-5.4-mini") is None  # smaller SKU, distinct baseline


def test_yaml_parses_to_dict_for_from_dict():
    """Sanity: the production yaml is shaped so from_dict accepts it
    without any wrapper logic. If someone restructures the file this
    test will catch it before runtime."""
    raw = yaml.safe_load(Path(BASELINES_PATH).read_text(encoding="utf-8"))
    idx = BaselinesIndex.from_dict(raw)
    assert isinstance(idx, BaselinesIndex)

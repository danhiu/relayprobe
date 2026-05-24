"""Load and access model baselines from data/baselines.yaml.

This module is the **single source of truth** for which model identifiers
the detector knows about. Both the HTTP routes and the CLI go through
:class:`BaselinesIndex` to translate a caller-supplied model name into
``(baseline, target_model)``:

* ``baseline`` is the canonical entry used for scoring (provider keywords,
  expected tokenizer, capability flags, …).
* ``target_model`` is the original string the caller passed in. It is
  what gets sent on the wire to the upstream relay, because the relay
  may publish the same model under a slightly different identifier
  (e.g. ``gpt-5.5`` vs ``gpt-5-5``).

Resolution rules live in :meth:`BaselinesIndex.resolve` and are
documented in the docstring there. The YAML file's top-level
``runtime_suffixes`` and ``dated_suffix_pattern`` keys feed those rules
directly so adding a new alias or suffix is a one-file change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

BASELINES_PATH = Path(__file__).resolve().parents[2] / "data" / "baselines.yaml"


@dataclass(frozen=True)
class Baseline:
    name: str
    provider: str
    expected_identity_keywords: list[str]
    forbidden_identity_keywords: list[str]
    expected_tokens_per_second: float
    expected_latency_p50_ms: int
    tokenizer: str
    supports: dict[str, bool]
    aliases: list[str] = field(default_factory=list)
    strengths_zh: list[str] = field(default_factory=list)
    weaknesses_zh: list[str] = field(default_factory=list)
    vendor_baseline_score: int = 80


@dataclass(frozen=True)
class BaselinesIndex:
    """Read-only registry of baselines plus the resolution rules.

    Built once per file load and cached. Treat it as immutable; the
    detector calls :meth:`resolve` per request and never mutates state.
    """

    baselines: dict[str, Baseline]
    runtime_suffixes: tuple[str, ...]
    dated_suffix_pattern: re.Pattern[str]
    # Pre-built lookup: alias OR canonical name (lowercased) -> Baseline.
    _by_alias: dict[str, Baseline] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict) -> "BaselinesIndex":
        baselines: dict[str, Baseline] = {}
        for name, fields in raw["models"].items():
            baselines[name] = Baseline(
                name=name,
                provider=fields["provider"],
                expected_identity_keywords=fields["expected_identity_keywords"],
                forbidden_identity_keywords=fields["forbidden_identity_keywords"],
                expected_tokens_per_second=fields["expected_tokens_per_second"],
                expected_latency_p50_ms=fields["expected_latency_p50_ms"],
                tokenizer=fields["tokenizer"],
                supports=fields["supports"],
                aliases=list(fields.get("aliases", []) or []),
                strengths_zh=fields.get("strengths_zh", []),
                weaknesses_zh=fields.get("weaknesses_zh", []),
                vendor_baseline_score=fields.get("vendor_baseline_score", 80),
            )

        suffixes_raw = raw.get("runtime_suffixes", []) or []
        # Lowercase + ensure leading dash for forgiving authoring.
        runtime_suffixes = tuple(
            (s if s.startswith("-") else f"-{s}").lower() for s in suffixes_raw
        )

        dated_pattern_raw = raw.get("dated_suffix_pattern") or r"-\d{8}$"
        dated_pattern = re.compile(dated_pattern_raw)

        by_alias: dict[str, Baseline] = {}
        for b in baselines.values():
            by_alias[b.name.lower()] = b
            for a in b.aliases:
                key = a.lower()
                if key in by_alias and by_alias[key].name != b.name:
                    raise ValueError(
                        f"baseline alias collision: {a!r} maps to both "
                        f"{by_alias[key].name!r} and {b.name!r}"
                    )
                by_alias[key] = b

        return cls(
            baselines=baselines,
            runtime_suffixes=runtime_suffixes,
            dated_suffix_pattern=dated_pattern,
            _by_alias=by_alias,
        )

    def __getitem__(self, name: str) -> Baseline:
        # Backward-compat: some callers still index by canonical name.
        return self.baselines[name]

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self.baselines

    def keys(self):
        return self.baselines.keys()

    def values(self):
        return self.baselines.values()

    def items(self):
        return self.baselines.items()

    def resolve(self, model: str) -> Baseline | None:
        """Map a caller-supplied model identifier to its baseline.

        Resolution order, first match wins:

        1. exact match against a canonical baseline ``name``
        2. exact match against any baseline's ``aliases``
        3. punctuation normalization: ``.`` → ``-``, then re-check 1+2
        4. strip a trailing token from ``runtime_suffixes``, re-check 1+2
           (loops while a known suffix is present, so stacked tokens like
           ``-thinking-low`` resolve)
        5. strip a trailing dated snapshot matching
           ``dated_suffix_pattern``, but only accept the strip when the
           prefix itself resolves — protects us from chopping random
           digits off non-baseline names

        Returns the matching :class:`Baseline` or ``None`` if no rule
        applied. The detector wraps this in a clear error; we don't
        raise here so callers can do their own diagnostic messaging.

        The original ``model`` string is what the upstream call should
        use; this method only chooses the baseline.
        """
        if not model:
            return None

        candidate = model.strip().lower()
        b = self._by_alias.get(candidate)
        if b is not None:
            return b

        if "." in candidate:
            dotted = candidate.replace(".", "-")
            b = self._by_alias.get(dotted)
            if b is not None:
                return b
            candidate = dotted

        # Repeat-strip runtime suffixes; protects against future stacking
        # like `-thinking-low` even though we don't ship one today.
        changed = True
        while changed:
            changed = False
            for suf in self.runtime_suffixes:
                if candidate.endswith(suf) and len(candidate) > len(suf):
                    candidate = candidate[: -len(suf)]
                    b = self._by_alias.get(candidate)
                    if b is not None:
                        return b
                    changed = True
                    break

        # Trailing dated snapshot: only strip if the prefix is itself known.
        match = self.dated_suffix_pattern.search(candidate)
        if match and match.start() > 0:
            head = candidate[: match.start()]
            b = self._by_alias.get(head)
            if b is not None:
                return b

        return None

    def is_supported(self, model: str) -> bool:
        return self.resolve(model) is not None


@lru_cache(maxsize=1)
def load_baselines(path: Path | None = None) -> BaselinesIndex:
    p = path or BASELINES_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return BaselinesIndex.from_dict(raw)

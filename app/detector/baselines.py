"""Load and access model baselines from data/baselines.yaml."""
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
    strengths_zh: list[str] = field(default_factory=list)
    weaknesses_zh: list[str] = field(default_factory=list)
    vendor_baseline_score: int = 80


@lru_cache(maxsize=1)
def load_baselines(path: Path | None = None) -> dict[str, Baseline]:
    p = path or BASELINES_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    out: dict[str, Baseline] = {}
    for name, fields in raw["models"].items():
        out[name] = Baseline(
            name=name,
            provider=fields["provider"],
            expected_identity_keywords=fields["expected_identity_keywords"],
            forbidden_identity_keywords=fields["forbidden_identity_keywords"],
            expected_tokens_per_second=fields["expected_tokens_per_second"],
            expected_latency_p50_ms=fields["expected_latency_p50_ms"],
            tokenizer=fields["tokenizer"],
            supports=fields["supports"],
            strengths_zh=fields.get("strengths_zh", []),
            weaknesses_zh=fields.get("weaknesses_zh", []),
            vendor_baseline_score=fields.get("vendor_baseline_score", 80),
        )
    return out

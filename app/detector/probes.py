"""Probe pool loader. Each draw appends a unique nonce to defeat upstream caching."""
import random
import uuid
from functools import lru_cache
from pathlib import Path

import yaml

PROBES_PATH = Path(__file__).resolve().parents[2] / "data" / "probes.yaml"


@lru_cache(maxsize=1)
def load_probes(path: Path | None = None) -> dict[str, list[str]]:
    p = path or PROBES_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return {k: list(v) for k, v in raw.items()}


def draw(category: str, rng: random.Random | None = None) -> tuple[str, str]:
    """Pick a random prompt from `category` and append a nonce.

    Returns: (prompt_with_nonce, nonce_string)
    """
    probes = load_probes()
    if category not in probes:
        raise KeyError(category)
    r = rng or random
    base = r.choice(probes[category])
    nonce = f"REQ-{uuid.uuid4().hex[:8]}"
    return f"{base} [{nonce}]", nonce

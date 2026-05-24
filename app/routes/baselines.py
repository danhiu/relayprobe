"""Read-only baseline catalog endpoint.

This is the authoritative answer to "which model identifiers does the
detector know about, and how does it map them to baselines?". External
clients (notably the new-api gateway) hit this at startup and on a
periodic refresh so they can show users a coherent list without
re-implementing the resolution rules in their own code.

Two callable shapes:

* ``GET /baselines`` — returns the full catalog, the active runtime
  suffix list, and the dated-suffix regex. Sufficient to mirror the
  detector's :meth:`BaselinesIndex.resolve` behavior on the client side
  (or, more simply, to enumerate "what should the picker show?").

* ``GET /baselines/resolve?model=<id>`` — single-shot resolver.
  Returns ``{baseline, target_model, supported}`` so a client can ask
  "would you accept this name?" without having to re-implement the
  rules. Useful for admin UIs that want to grey out unsupported models
  before submitting a scan.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.detector.baselines import load_baselines

router = APIRouter()


class BaselineEntry(BaseModel):
    name: str
    aliases: list[str]
    provider: str
    tokenizer: str
    expected_identity_keywords: list[str]
    forbidden_identity_keywords: list[str]
    supports: dict[str, bool]
    strengths_zh: list[str]
    weaknesses_zh: list[str]
    vendor_baseline_score: int


class BaselinesCatalog(BaseModel):
    baselines: list[BaselineEntry]
    runtime_suffixes: list[str]
    dated_suffix_pattern: str


class ResolveResponse(BaseModel):
    supported: bool
    baseline: str | None
    target_model: str
    aliases: list[str]


@router.get("/baselines", response_model=BaselinesCatalog)
async def get_baselines() -> BaselinesCatalog:
    idx = load_baselines()
    entries = [
        BaselineEntry(
            name=b.name,
            aliases=list(b.aliases),
            provider=b.provider,
            tokenizer=b.tokenizer,
            expected_identity_keywords=list(b.expected_identity_keywords),
            forbidden_identity_keywords=list(b.forbidden_identity_keywords),
            supports=dict(b.supports),
            strengths_zh=list(b.strengths_zh),
            weaknesses_zh=list(b.weaknesses_zh),
            vendor_baseline_score=b.vendor_baseline_score,
        )
        for b in idx.values()
    ]
    return BaselinesCatalog(
        baselines=entries,
        runtime_suffixes=list(idx.runtime_suffixes),
        dated_suffix_pattern=idx.dated_suffix_pattern.pattern,
    )


@router.get("/baselines/resolve", response_model=ResolveResponse)
async def resolve(model: str) -> ResolveResponse:
    if not model:
        raise HTTPException(status_code=400, detail="model query param required")
    idx = load_baselines()
    baseline = idx.resolve(model)
    if baseline is None:
        return ResolveResponse(
            supported=False, baseline=None, target_model=model, aliases=[]
        )
    return ResolveResponse(
        supported=True,
        baseline=baseline.name,
        target_model=model,
        aliases=list(baseline.aliases),
    )

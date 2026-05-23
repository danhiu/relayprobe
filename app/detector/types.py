"""Public types shared between adapters, dimensions, scoring, routes, and CLI."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Provider = Literal["anthropic", "openai", "google"]
Verdict = Literal[
    "authentic", "likely_authentic", "suspicious", "likely_fake", "offline"
]
DimensionStatus = Literal["ok", "degraded", "missing", "error", "skipped"]


class DetectRequest(BaseModel):
    base_url: str
    api_key: str
    model: str
    expected_provider: Provider | None = None
    rounds: int = Field(default=11, ge=5, le=50)
    budget_usd: float = Field(default=0.5, gt=0)
    task_id: str | None = None
    mode: Literal["sync", "async"] = "sync"
    dry_run: bool = False
    verbose: bool = False


class DimensionResult(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)
    status: DimensionStatus
    weight: float = 0.0  # filled in by scoring layer
    evidence: dict = Field(default_factory=dict)
    error: str | None = None


class RoundLog(BaseModel):
    round: int
    dimension: str
    prompt: str
    response_excerpt: str
    verdict: str
    duration_ms: int


class DetectResponse(BaseModel):
    task_id: str
    status: Literal["completed", "running", "failed"] = "completed"
    score: int = Field(ge=0, le=100)
    verdict: Verdict
    summary_zh: str
    summary_en: str
    dimensions: dict[str, DimensionResult]
    capability_flags: dict[str, DimensionStatus]
    rounds_log: list[RoundLog] = Field(default_factory=list)
    actual_cost_usd: float = 0.0
    duration_ms: int = 0
    over_budget: bool = False
    warnings: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON schema


class ChatResult(BaseModel):
    """Adapter-normalized chat response — shape is identical for all 3 vendors."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    total_latency_ms: int
    first_token_latency_ms: int | None = None
    tool_calls: list[dict] = Field(default_factory=list)  # [{name, arguments}]
    raw: dict = Field(default_factory=dict)  # raw vendor response, redacted

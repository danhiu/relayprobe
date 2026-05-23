# AI 中转站检测服务 v0.1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 v0.1 MVP — Python FastAPI HTTP 服务 + 检测核心库 + CLI，支持 Anthropic/OpenAI/Google 三家共 5 个模型，跑通 4 个检测维度（online + identity_consistency + token_billing + tool_use），可 Docker 部署，由 yyc.lat Go 后端调用。

**Architecture:**
- `app/detector/` 为纯 Python 库（无 HTTP 依赖），CLI 和 FastAPI 共享
- 每家厂商一个 adapter（adapters/anthropic.py、openai.py、google.py），每个维度一个 module（dimensions/online.py 等）
- 异步 httpx 调用上游 API，BudgetTracker 守卫成本，log_redact 全局脱敏 sk-key
- 同步路径只有 `POST /detect`（v0.1 不支持 async / cache / benchmark / compare）

**Tech Stack:** Python 3.11+, FastAPI 0.110+, uvicorn, httpx (async), pydantic v2, PyYAML, pytest, pytest-asyncio, respx (httpx mock), ruff, Docker (python:3.11-slim 基底)

**Spec reference:** `docs/superpowers/specs/2026-05-23-ai-relay-detector-design.md`

---

## File Structure (v0.1)

**Created:**
- `pyproject.toml` — 项目元数据、依赖、ruff/pytest 配置
- `.gitignore` — Python 标准 + `.venv/`、`__pycache__/`、`*.db`
- `Dockerfile` — python:3.11-slim 基底，COPY app/ + data/，启动 uvicorn
- `docker-compose.yml` — 暴露 127.0.0.1:8800
- `README.md` — 快速启动、API 示例、CLI 示例、yyc 接入示例
- `data/baselines.yaml` — 5 个模型基线
- `data/probes.yaml` — identity / capability prompt 池
- `app/__init__.py`
- `app/main.py` — FastAPI 入口（include 路由）
- `app/cli.py` — `python -m app.cli` 入口
- `app/routes/__init__.py`
- `app/routes/detect.py` — `POST /detect`
- `app/routes/health.py` — `GET /healthz`
- `app/detector/__init__.py` — 导出 `run_detection`、`load_baseline`
- `app/detector/types.py` — pydantic 模型 `DetectRequest`、`DetectResponse`、`DimensionResult` 等
- `app/detector/log_redact.py` — sk-key 脱敏（logger filter）
- `app/detector/budget.py` — `BudgetTracker` + `BudgetExceeded`
- `app/detector/probes.py` — probes.yaml 加载 + 随机抽样 + nonce
- `app/detector/baselines.py` — baselines.yaml 加载 + 校验
- `app/detector/adapters/__init__.py` — `get_adapter(provider)` 工厂
- `app/detector/adapters/base.py` — `Adapter` ABC：`async def chat(...)`、`async def list_models()`、`async def chat_with_tools(...)`
- `app/detector/adapters/anthropic.py`
- `app/detector/adapters/openai.py`
- `app/detector/adapters/google.py`
- `app/detector/dimensions/__init__.py` — `ALL_DIMENSIONS = [Online, IdentityConsistency, TokenBilling, ToolUse]`
- `app/detector/dimensions/base.py` — `Dimension` ABC + `DimensionResult` 数据类
- `app/detector/dimensions/online.py`
- `app/detector/dimensions/identity_consistency.py`
- `app/detector/dimensions/token_billing.py`
- `app/detector/dimensions/tool_use.py`
- `app/detector/scoring.py` — `aggregate(results) -> (score, verdict)` + `summarize(results) -> (summary_zh, summary_en)`
- `app/detector/core.py` — `async def run_detection(req: DetectRequest) -> DetectResponse`
- `tests/__init__.py`
- `tests/fixtures/mock_responses/` — 三家厂商的固化响应 JSON（用于 dry_run + 单测）
- `tests/test_log_redact.py`
- `tests/test_budget.py`
- `tests/test_probes.py`
- `tests/test_baselines.py`
- `tests/test_adapters/test_anthropic.py`
- `tests/test_adapters/test_openai.py`
- `tests/test_adapters/test_google.py`
- `tests/test_dimensions/test_online.py`
- `tests/test_dimensions/test_identity_consistency.py`
- `tests/test_dimensions/test_token_billing.py`
- `tests/test_dimensions/test_tool_use.py`
- `tests/test_scoring.py`
- `tests/test_core.py`
- `tests/test_routes.py`
- `tests/test_cli.py`

**Modified:** none (all new)

---

## Task 1: 初始化项目骨架

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: 创建 `pyproject.toml`**

```toml
[project]
name = "ai-relay-detector"
version = "0.1.0"
description = "AI relay station authenticity & capability detector for yyc.lat"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "httpx>=0.27.0",
    "pydantic>=2.6.0",
    "PyYAML>=6.0.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "respx>=0.20.0",
    "ruff>=0.3.0",
]

[project.scripts]
detector = "app.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

- [ ] **Step 2: 创建 `.gitignore`**

```
__pycache__/
*.py[cod]
.venv/
.env
*.db
*.sqlite
.pytest_cache/
.ruff_cache/
.coverage
dist/
build/
*.egg-info/
```

- [ ] **Step 3: 创建空包文件**

```python
# app/__init__.py
"""AI relay station detector."""
__version__ = "0.1.0"
```

```python
# tests/__init__.py
```

- [ ] **Step 4: 验证 ruff 与 pytest 可以加载**

Run: `python -m pip install -e ".[dev]"`
Expected: 安装成功，无错误。

Run: `python -m ruff check .`
Expected: `All checks passed!`

Run: `python -m pytest tests/ -v`
Expected: `no tests ran`（目录空）。

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml .gitignore app/__init__.py tests/__init__.py
git commit -m "chore: bootstrap python project skeleton"
```

---

## Task 2: 实现日志脱敏 `log_redact.py`

**Files:**
- Create: `app/detector/__init__.py`
- Create: `app/detector/log_redact.py`
- Test: `tests/test_log_redact.py`

- [ ] **Step 1: 创建 `app/detector/__init__.py`**

```python
"""Detector core library — pure Python, no FastAPI deps."""
```

- [ ] **Step 2: 写失败的测试**

`tests/test_log_redact.py`:

```python
from app.detector.log_redact import redact


def test_redact_sk_key():
    assert redact("Bearer sk-abcdef1234567890") == "Bearer sk-abc***90"


def test_redact_short_sk_key_fully_masked():
    assert redact("sk-abc") == "sk-***"


def test_redact_multiple_keys_in_string():
    text = "key1=sk-AAAAAAAAAA and key2=sk-BBBBBBBBBB"
    out = redact(text)
    assert "sk-AAA***AA" in out
    assert "sk-BBB***BB" in out


def test_redact_no_key():
    assert redact("hello world") == "hello world"


def test_redact_handles_none_safely():
    assert redact(None) == None
```

- [ ] **Step 3: Run test，确认失败**

Run: `python -m pytest tests/test_log_redact.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.detector.log_redact'`

- [ ] **Step 4: 实现 `app/detector/log_redact.py`**

```python
"""Mask API keys in log output. Used by both the logging filter and ad-hoc string masking."""
import logging
import re

# Match sk-XXXXXX style keys (Anthropic, OpenAI, generic relay keys all use this prefix family)
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]+")


def _mask(match: re.Match) -> str:
    raw = match.group(0)
    # raw looks like "sk-XXXX..."
    body = raw[3:]
    if len(body) <= 5:
        return "sk-***"
    return f"sk-{body[:3]}***{body[-2:]}"


def redact(value):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    return _SK_PATTERN.sub(_mask, value)


class RedactFilter(logging.Filter):
    """Logging filter that masks API keys in record messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(a) if isinstance(a, str) else a for a in record.args
            )
        return True


def install_global_filter() -> None:
    """Attach RedactFilter to the root logger so every emitter goes through it."""
    root = logging.getLogger()
    if not any(isinstance(f, RedactFilter) for f in root.filters):
        root.addFilter(RedactFilter())
```

- [ ] **Step 5: Run test，确认通过**

Run: `python -m pytest tests/test_log_redact.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add app/detector/__init__.py app/detector/log_redact.py tests/test_log_redact.py
git commit -m "feat(detector): add api key redaction utility and logging filter"
```

---

## Task 3: 实现 `BudgetTracker`

**Files:**
- Create: `app/detector/budget.py`
- Test: `tests/test_budget.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_budget.py`:

```python
import pytest

from app.detector.budget import BudgetExceeded, BudgetTracker


def test_charge_accumulates_cost():
    bt = BudgetTracker(budget_usd=1.0)
    # claude-opus-4-7 pricing: $15/MTok input, $75/MTok output (placeholder values)
    bt.charge(model="claude-opus-4-7", prompt_tokens=1000, completion_tokens=500)
    assert bt.spent_usd > 0
    assert bt.spent_usd < 1.0


def test_charge_raises_when_over_budget():
    bt = BudgetTracker(budget_usd=0.001)
    with pytest.raises(BudgetExceeded):
        bt.charge(
            model="claude-opus-4-7", prompt_tokens=10000, completion_tokens=10000
        )


def test_unknown_model_uses_default_pricing():
    bt = BudgetTracker(budget_usd=1.0)
    # should not crash; uses fallback price
    bt.charge(model="some-unknown-model", prompt_tokens=100, completion_tokens=100)
    assert bt.spent_usd > 0


def test_remaining_reflects_charges():
    bt = BudgetTracker(budget_usd=1.0)
    bt.charge(model="claude-opus-4-7", prompt_tokens=100, completion_tokens=50)
    assert bt.remaining_usd == bt.budget_usd - bt.spent_usd
    assert bt.remaining_usd >= 0
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_budget.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 实现 `app/detector/budget.py`**

```python
"""Track per-detection USD spend and abort when over budget."""
from dataclasses import dataclass, field

# Approximate USD per 1M tokens. Source: vendor official pricing as of 2026-05.
# Used only as a coarse safety guard — exact billing happens upstream.
PRICING_PER_MTOK = {
    "claude-opus-4-7":   (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "gpt-5-5":           (1.25, 10.0),
    "gpt-5-4":           (2.5, 10.0),
    "gemini-3-1-pro":    (3.5, 21.0),
}
DEFAULT_PRICING = (5.0, 25.0)  # conservative fallback


class BudgetExceeded(Exception):
    """Raised by BudgetTracker.charge when a charge would push spend past the budget."""


@dataclass
class BudgetTracker:
    budget_usd: float
    spent_usd: float = 0.0
    charges: list[dict] = field(default_factory=list)

    def charge(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        in_price, out_price = PRICING_PER_MTOK.get(model, DEFAULT_PRICING)
        cost = (prompt_tokens / 1_000_000) * in_price + (
            completion_tokens / 1_000_000
        ) * out_price
        new_spent = self.spent_usd + cost
        if new_spent > self.budget_usd:
            raise BudgetExceeded(
                f"budget {self.budget_usd:.4f} USD exceeded "
                f"(would be {new_spent:.4f} USD after this charge)"
            )
        self.spent_usd = new_spent
        self.charges.append(
            {
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": cost,
            }
        )
        return cost

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_usd - self.spent_usd)
```

- [ ] **Step 4: Run test，确认通过**

Run: `python -m pytest tests/test_budget.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/detector/budget.py tests/test_budget.py
git commit -m "feat(detector): add USD budget tracker with vendor pricing fallback"
```

---

## Task 4: 创建 `data/baselines.yaml` + 加载器

**Files:**
- Create: `data/baselines.yaml`
- Create: `app/detector/baselines.py`
- Test: `tests/test_baselines.py`

- [ ] **Step 1: 写 `data/baselines.yaml`**

```yaml
# 5 个 v0.1 支持的模型基线。新增模型时需保持字段齐全。
models:
  claude-opus-4-7:
    provider: anthropic
    expected_identity_keywords: ["claude", "anthropic"]
    forbidden_identity_keywords: ["openai", "gpt", "google", "gemini", "glm", "qwen", "deepseek"]
    expected_tokens_per_second: 35
    expected_latency_p50_ms: 1500
    tokenizer: anthropic
    supports:
      tool_use: true
      web_search: true
      sub_agent: true
      streaming: true
    strengths_zh: ["代码生成", "长上下文", "复杂推理"]
    weaknesses_zh: ["数学推理偏弱"]
    vendor_baseline_score: 95

  claude-sonnet-4-6:
    provider: anthropic
    expected_identity_keywords: ["claude", "anthropic"]
    forbidden_identity_keywords: ["openai", "gpt", "google", "gemini", "glm", "qwen", "deepseek"]
    expected_tokens_per_second: 60
    expected_latency_p50_ms: 900
    tokenizer: anthropic
    supports:
      tool_use: true
      web_search: true
      sub_agent: true
      streaming: true
    strengths_zh: ["性价比", "代码生成"]
    weaknesses_zh: []
    vendor_baseline_score: 88

  gpt-5-5:
    provider: openai
    expected_identity_keywords: ["gpt", "openai"]
    forbidden_identity_keywords: ["claude", "anthropic", "google", "gemini", "glm", "qwen", "deepseek"]
    expected_tokens_per_second: 80
    expected_latency_p50_ms: 700
    tokenizer: openai
    supports:
      tool_use: true
      web_search: true
      sub_agent: true
      streaming: true
    strengths_zh: ["综合能力", "通用推理"]
    weaknesses_zh: []
    vendor_baseline_score: 90

  gpt-5-4:
    provider: openai
    expected_identity_keywords: ["gpt", "openai"]
    forbidden_identity_keywords: ["claude", "anthropic", "google", "gemini", "glm", "qwen", "deepseek"]
    expected_tokens_per_second: 90
    expected_latency_p50_ms: 600
    tokenizer: openai
    supports:
      tool_use: true
      web_search: true
      sub_agent: true
      streaming: true
    strengths_zh: ["速度", "性价比"]
    weaknesses_zh: ["复杂推理略弱于 5-5"]
    vendor_baseline_score: 86

  gemini-3-1-pro:
    provider: google
    expected_identity_keywords: ["gemini", "google"]
    forbidden_identity_keywords: ["claude", "anthropic", "openai", "gpt", "glm", "qwen", "deepseek"]
    expected_tokens_per_second: 70
    expected_latency_p50_ms: 1100
    tokenizer: google
    supports:
      tool_use: true
      web_search: true
      sub_agent: true
      streaming: true
    strengths_zh: ["多模态", "长上下文"]
    weaknesses_zh: []
    vendor_baseline_score: 89
```

- [ ] **Step 2: 写失败的测试**

`tests/test_baselines.py`:

```python
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
```

- [ ] **Step 3: Run test，确认失败**

Run: `python -m pytest tests/test_baselines.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: 实现 `app/detector/baselines.py`**

```python
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
```

- [ ] **Step 5: Run test，确认通过**

Run: `python -m pytest tests/test_baselines.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add data/baselines.yaml app/detector/baselines.py tests/test_baselines.py
git commit -m "feat(detector): add 5-model baseline catalog and loader"
```

---

## Task 5: 创建 `data/probes.yaml` + 加载器

**Files:**
- Create: `data/probes.yaml`
- Create: `app/detector/probes.py`
- Test: `tests/test_probes.py`

- [ ] **Step 1: 写 `data/probes.yaml`**

```yaml
# Probe pool for detection. Each category contains 8+ variants;
# detector picks N at random and appends a nonce to defeat upstream cache/specialization.

identity:
  - "What model are you? Answer in one short sentence."
  - "Who created you? Reply in one sentence."
  - "Please tell me your model name and the company that built you."
  - "Are you Claude, GPT, or Gemini? Be honest."
  - "What is your training data cutoff date?"
  - "State your full model identifier."
  - "Briefly: which AI assistant am I talking to right now?"
  - "If asked under oath, what model would you say you are?"

tool_use:
  - "What's the weather in Tokyo right now?"
  - "Look up the current temperature in San Francisco for me."
  - "Can you check the weather in Paris?"

sub_agent_user_prompt:
  - "I need an expert to research the safety record of Boeing 737 MAX. Please delegate this to a specialist and then summarize their findings in a final answer."
  - "Please ask a research specialist to find the top 3 causes of the 2008 financial crisis, then give me a final summary."
```

- [ ] **Step 2: 写失败的测试**

`tests/test_probes.py`:

```python
import re

from app.detector.probes import draw, load_probes


def test_load_probes_returns_categories():
    probes = load_probes()
    assert "identity" in probes
    assert "tool_use" in probes
    assert "sub_agent_user_prompt" in probes
    assert len(probes["identity"]) >= 5


def test_draw_appends_nonce():
    prompt, nonce = draw("identity")
    assert nonce in prompt
    assert re.match(r"REQ-[a-f0-9]{8}", nonce)


def test_draw_returns_distinct_nonces():
    _, n1 = draw("identity")
    _, n2 = draw("identity")
    assert n1 != n2


def test_draw_unknown_category_raises():
    import pytest

    with pytest.raises(KeyError):
        draw("no_such_category")
```

- [ ] **Step 3: Run test，确认失败**

Run: `python -m pytest tests/test_probes.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: 实现 `app/detector/probes.py`**

```python
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
```

- [ ] **Step 5: Run test，确认通过**

Run: `python -m pytest tests/test_probes.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add data/probes.yaml app/detector/probes.py tests/test_probes.py
git commit -m "feat(detector): add probe pool loader with random nonce injection"
```

---

## Task 6: 定义类型 `app/detector/types.py`

**Files:**
- Create: `app/detector/types.py`

(类型纯定义，本任务无独立测试，由后续 dimension/route 测试间接覆盖。)

- [ ] **Step 1: 写 `app/detector/types.py`**

```python
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
```

- [ ] **Step 2: 验证导入无错**

Run: `python -c "from app.detector.types import DetectRequest, DetectResponse, ChatResult; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/detector/types.py
git commit -m "feat(detector): add shared pydantic types for request, response, and adapter results"
```

---

## Task 7: Adapter 抽象 + 工厂 `adapters/base.py` + `adapters/__init__.py`

**Files:**
- Create: `app/detector/adapters/__init__.py`
- Create: `app/detector/adapters/base.py`
- Test: `tests/test_adapters/__init__.py`
- Test: `tests/test_adapters/test_factory.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_adapters/__init__.py`:

```python
```

`tests/test_adapters/test_factory.py`:

```python
import pytest

from app.detector.adapters import get_adapter
from app.detector.adapters.base import Adapter


def test_get_adapter_anthropic():
    a = get_adapter("anthropic", base_url="https://x", api_key="sk-test")
    assert isinstance(a, Adapter)
    assert a.provider == "anthropic"


def test_get_adapter_openai():
    a = get_adapter("openai", base_url="https://x", api_key="sk-test")
    assert a.provider == "openai"


def test_get_adapter_google():
    a = get_adapter("google", base_url="https://x", api_key="sk-test")
    assert a.provider == "google"


def test_get_adapter_unknown_provider_raises():
    with pytest.raises(ValueError):
        get_adapter("xai", base_url="https://x", api_key="sk-test")
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_adapters/test_factory.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 实现 `app/detector/adapters/base.py`**

```python
"""Adapter ABC. Three concrete subclasses (anthropic/openai/google) speak each vendor's
native protocol but expose the same normalized interface to the rest of the detector."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from app.detector.types import ChatMessage, ChatResult, Provider, ToolDefinition


class Adapter(ABC):
    provider: Provider

    def __init__(self, base_url: str, api_key: str, timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Return model IDs available at the upstream's `/v1/models` (or equivalent)."""

    @abstractmethod
    async def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        """Single-turn or multi-turn chat with no tools."""

    @abstractmethod
    async def chat_with_tools(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        tools: list[ToolDefinition],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        """Chat with function-calling tools enabled."""

    async def aclose(self) -> None:
        """Override if subclass holds an httpx.AsyncClient."""
```

- [ ] **Step 4: 实现 `app/detector/adapters/__init__.py`**

```python
"""Adapter factory."""
from __future__ import annotations

from app.detector.adapters.base import Adapter
from app.detector.types import Provider


def get_adapter(provider: Provider, *, base_url: str, api_key: str) -> Adapter:
    if provider == "anthropic":
        from app.detector.adapters.anthropic import AnthropicAdapter
        return AnthropicAdapter(base_url=base_url, api_key=api_key)
    if provider == "openai":
        from app.detector.adapters.openai import OpenAIAdapter
        return OpenAIAdapter(base_url=base_url, api_key=api_key)
    if provider == "google":
        from app.detector.adapters.google import GoogleAdapter
        return GoogleAdapter(base_url=base_url, api_key=api_key)
    raise ValueError(f"unknown provider: {provider!r}")
```

- [ ] **Step 5: 创建占位的三个 adapter 文件以让 import 不报错**

`app/detector/adapters/anthropic.py`:
```python
from app.detector.adapters.base import Adapter


class AnthropicAdapter(Adapter):
    provider = "anthropic"

    async def list_models(self):
        raise NotImplementedError

    async def chat(self, model, messages, max_tokens=256, temperature=0.0):
        raise NotImplementedError

    async def chat_with_tools(self, model, messages, tools, max_tokens=256, temperature=0.0):
        raise NotImplementedError
```

`app/detector/adapters/openai.py`:
```python
from app.detector.adapters.base import Adapter


class OpenAIAdapter(Adapter):
    provider = "openai"

    async def list_models(self):
        raise NotImplementedError

    async def chat(self, model, messages, max_tokens=256, temperature=0.0):
        raise NotImplementedError

    async def chat_with_tools(self, model, messages, tools, max_tokens=256, temperature=0.0):
        raise NotImplementedError
```

`app/detector/adapters/google.py`:
```python
from app.detector.adapters.base import Adapter


class GoogleAdapter(Adapter):
    provider = "google"

    async def list_models(self):
        raise NotImplementedError

    async def chat(self, model, messages, max_tokens=256, temperature=0.0):
        raise NotImplementedError

    async def chat_with_tools(self, model, messages, tools, max_tokens=256, temperature=0.0):
        raise NotImplementedError
```

- [ ] **Step 6: Run test，确认通过**

Run: `python -m pytest tests/test_adapters/test_factory.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add app/detector/adapters/ tests/test_adapters/__init__.py tests/test_adapters/test_factory.py
git commit -m "feat(adapters): add adapter ABC and provider factory with three placeholders"
```

---

## Task 8: AnthropicAdapter 实现

**Files:**
- Modify: `app/detector/adapters/anthropic.py`
- Test: `tests/test_adapters/test_anthropic.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_adapters/test_anthropic.py`:

```python
import httpx
import pytest
import respx

from app.detector.adapters.anthropic import AnthropicAdapter
from app.detector.types import ChatMessage, ToolDefinition


@respx.mock
async def test_chat_basic():
    respx.post("https://up.example.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there"}],
                "model": "claude-opus-4-7",
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )
    )
    a = AnthropicAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat(
        model="claude-opus-4-7",
        messages=[ChatMessage(role="user", content="hello")],
    )
    assert result.text == "Hi there"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 3
    assert result.tool_calls == []


@respx.mock
async def test_chat_with_tools_returns_tool_calls():
    respx.post("https://up.example.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_2",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "get_weather",
                        "input": {"location": "Tokyo"},
                    }
                ],
                "model": "claude-opus-4-7",
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 50, "output_tokens": 20},
            },
        )
    )
    a = AnthropicAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat_with_tools(
        model="claude-opus-4-7",
        messages=[ChatMessage(role="user", content="weather in Tokyo?")],
        tools=[
            ToolDefinition(
                name="get_weather",
                description="Get weather",
                parameters={
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            )
        ],
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "get_weather"
    assert result.tool_calls[0]["arguments"] == {"location": "Tokyo"}


@respx.mock
async def test_list_models():
    respx.get("https://up.example.com/v1/models").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": "claude-opus-4-7", "type": "model"},
                    {"id": "claude-sonnet-4-6", "type": "model"},
                ]
            },
        )
    )
    a = AnthropicAdapter(base_url="https://up.example.com", api_key="sk-test")
    models = await a.list_models()
    assert "claude-opus-4-7" in models
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_adapters/test_anthropic.py -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: 实现 `app/detector/adapters/anthropic.py`**

```python
"""Anthropic /v1/messages adapter. Native protocol — required for true authenticity check."""
from __future__ import annotations

import time
from typing import Iterable

import httpx

from app.detector.adapters.base import Adapter
from app.detector.types import ChatMessage, ChatResult, ToolDefinition

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter(Adapter):
    provider = "anthropic"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _to_messages(self, messages: Iterable[ChatMessage]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if m.role == "system":
                # Anthropic uses top-level `system`; we attach via separate field in payload.
                continue
            out.append({"role": m.role, "content": m.content})
        return out

    def _system(self, messages: Iterable[ChatMessage]) -> str | None:
        for m in messages:
            if m.role == "system":
                return m.content
        return None

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.get(
                f"{self.base_url}/v1/models", headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]

    async def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        msgs = list(messages)
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._to_messages(msgs),
        }
        sys = self._system(msgs)
        if sys:
            payload["system"] = sys

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()
        latency_ms = int((time.monotonic() - start) * 1000)

        text_parts = [
            blk["text"] for blk in body.get("content", []) if blk.get("type") == "text"
        ]
        return ChatResult(
            text="".join(text_parts),
            prompt_tokens=body.get("usage", {}).get("input_tokens", 0),
            completion_tokens=body.get("usage", {}).get("output_tokens", 0),
            total_latency_ms=latency_ms,
            tool_calls=[],
            raw=body,
        )

    async def chat_with_tools(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        tools: list[ToolDefinition],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        msgs = list(messages)
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._to_messages(msgs),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ],
        }
        sys = self._system(msgs)
        if sys:
            payload["system"] = sys

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()
        latency_ms = int((time.monotonic() - start) * 1000)

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for blk in body.get("content", []):
            if blk.get("type") == "text":
                text_parts.append(blk["text"])
            elif blk.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": blk.get("id"),
                        "name": blk["name"],
                        "arguments": blk.get("input", {}),
                    }
                )
        return ChatResult(
            text="".join(text_parts),
            prompt_tokens=body.get("usage", {}).get("input_tokens", 0),
            completion_tokens=body.get("usage", {}).get("output_tokens", 0),
            total_latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw=body,
        )
```

- [ ] **Step 4: Run test，确认通过**

Run: `python -m pytest tests/test_adapters/test_anthropic.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/detector/adapters/anthropic.py tests/test_adapters/test_anthropic.py
git commit -m "feat(adapters): implement Anthropic /v1/messages adapter with tool_use parsing"
```

---

## Task 9: OpenAIAdapter 实现

**Files:**
- Modify: `app/detector/adapters/openai.py`
- Test: `tests/test_adapters/test_openai.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_adapters/test_openai.py`:

```python
import httpx
import respx

from app.detector.adapters.openai import OpenAIAdapter
from app.detector.types import ChatMessage, ToolDefinition


@respx.mock
async def test_chat_basic():
    respx.post("https://up.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cmpl_1",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hi"},
                        "finish_reason": "stop",
                        "index": 0,
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            },
        )
    )
    a = OpenAIAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat(
        model="gpt-5-5", messages=[ChatMessage(role="user", content="hi")]
    )
    assert result.text == "Hi"
    assert result.prompt_tokens == 5


@respx.mock
async def test_chat_with_tools_returns_tool_calls():
    respx.post("https://up.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cmpl_2",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"location": "Tokyo"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                        "index": 0,
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            },
        )
    )
    a = OpenAIAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat_with_tools(
        model="gpt-5-5",
        messages=[ChatMessage(role="user", content="weather in Tokyo?")],
        tools=[
            ToolDefinition(
                name="get_weather",
                description="Get weather",
                parameters={
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            )
        ],
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "get_weather"
    assert result.tool_calls[0]["arguments"] == {"location": "Tokyo"}


@respx.mock
async def test_chat_text_when_tool_calls_arguments_invalid_json():
    respx.post("https://up.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cmpl_3",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_x",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": "{not-json}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5},
            },
        )
    )
    a = OpenAIAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat_with_tools(
        model="gpt-5-5",
        messages=[ChatMessage(role="user", content="x")],
        tools=[
            ToolDefinition(
                name="get_weather", description="", parameters={"type": "object"}
            )
        ],
    )
    # invalid json arguments still surface, but as raw string under "arguments_raw"
    assert result.tool_calls[0]["name"] == "get_weather"
    assert result.tool_calls[0]["arguments"] == {}
    assert result.tool_calls[0]["arguments_raw"] == "{not-json}"
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_adapters/test_openai.py -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: 实现 `app/detector/adapters/openai.py`**

```python
"""OpenAI /v1/chat/completions adapter."""
from __future__ import annotations

import json
import time
from typing import Iterable

import httpx

from app.detector.adapters.base import Adapter
from app.detector.types import ChatMessage, ChatResult, ToolDefinition


class OpenAIAdapter(Adapter):
    provider = "openai"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }

    def _to_messages(self, messages: Iterable[ChatMessage]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.get(
                f"{self.base_url}/v1/models", headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]

    async def _post_chat(self, payload: dict) -> tuple[dict, int]:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()
        latency_ms = int((time.monotonic() - start) * 1000)
        return body, latency_ms

    async def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        body, latency_ms = await self._post_chat(
            {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": self._to_messages(messages),
            }
        )
        choice = body.get("choices", [{}])[0]
        msg = choice.get("message", {})
        return ChatResult(
            text=msg.get("content") or "",
            prompt_tokens=body.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=body.get("usage", {}).get("completion_tokens", 0),
            total_latency_ms=latency_ms,
            tool_calls=[],
            raw=body,
        )

    async def chat_with_tools(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        tools: list[ToolDefinition],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        body, latency_ms = await self._post_chat(
            {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": self._to_messages(messages),
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        },
                    }
                    for t in tools
                ],
                "tool_choice": "auto",
            }
        )
        choice = body.get("choices", [{}])[0]
        msg = choice.get("message", {})
        tool_calls: list[dict] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw_args = fn.get("arguments", "")
            try:
                parsed = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                parsed = {}
            tool_calls.append(
                {
                    "id": tc.get("id"),
                    "name": fn.get("name"),
                    "arguments": parsed,
                    "arguments_raw": raw_args,
                }
            )
        return ChatResult(
            text=msg.get("content") or "",
            prompt_tokens=body.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=body.get("usage", {}).get("completion_tokens", 0),
            total_latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw=body,
        )
```

- [ ] **Step 4: Run test，确认通过**

Run: `python -m pytest tests/test_adapters/test_openai.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/detector/adapters/openai.py tests/test_adapters/test_openai.py
git commit -m "feat(adapters): implement OpenAI /v1/chat/completions adapter with tool_calls parsing"
```

---

## Task 10: GoogleAdapter 实现

**Files:**
- Modify: `app/detector/adapters/google.py`
- Test: `tests/test_adapters/test_google.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_adapters/test_google.py`:

```python
import httpx
import respx

from app.detector.adapters.google import GoogleAdapter
from app.detector.types import ChatMessage, ToolDefinition


@respx.mock
async def test_chat_basic():
    respx.post(
        "https://up.example.com/v1beta/models/gemini-3-1-pro:generateContent"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "Hi"}],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 4,
                    "candidatesTokenCount": 1,
                    "totalTokenCount": 5,
                },
            },
        )
    )
    a = GoogleAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat(
        model="gemini-3-1-pro",
        messages=[ChatMessage(role="user", content="hi")],
    )
    assert result.text == "Hi"
    assert result.prompt_tokens == 4
    assert result.completion_tokens == 1


@respx.mock
async def test_chat_with_tools_returns_function_call():
    respx.post(
        "https://up.example.com/v1beta/models/gemini-3-1-pro:generateContent"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "get_weather",
                                        "args": {"location": "Tokyo"},
                                    }
                                }
                            ],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 50,
                    "candidatesTokenCount": 10,
                    "totalTokenCount": 60,
                },
            },
        )
    )
    a = GoogleAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat_with_tools(
        model="gemini-3-1-pro",
        messages=[ChatMessage(role="user", content="weather?")],
        tools=[
            ToolDefinition(
                name="get_weather",
                description="Get weather",
                parameters={
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            )
        ],
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "get_weather"
    assert result.tool_calls[0]["arguments"] == {"location": "Tokyo"}


@respx.mock
async def test_list_models():
    respx.get("https://up.example.com/v1beta/models").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {"name": "models/gemini-3-1-pro"},
                    {"name": "models/gemini-3-flash"},
                ]
            },
        )
    )
    a = GoogleAdapter(base_url="https://up.example.com", api_key="sk-test")
    models = await a.list_models()
    assert "gemini-3-1-pro" in models
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_adapters/test_google.py -v`
Expected: FAIL — `NotImplementedError`.

- [ ] **Step 3: 实现 `app/detector/adapters/google.py`**

```python
"""Google Gemini generateContent adapter."""
from __future__ import annotations

import time
from typing import Iterable

import httpx

from app.detector.adapters.base import Adapter
from app.detector.types import ChatMessage, ChatResult, ToolDefinition


class GoogleAdapter(Adapter):
    provider = "google"

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self.api_key,
            "content-type": "application/json",
        }

    def _to_contents(self, messages: Iterable[ChatMessage]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if m.role == "system":
                continue  # passed via systemInstruction below
            role = "user" if m.role == "user" else "model"
            out.append({"role": role, "parts": [{"text": m.content}]})
        return out

    def _system(self, messages: Iterable[ChatMessage]) -> dict | None:
        for m in messages:
            if m.role == "system":
                return {"parts": [{"text": m.content}]}
        return None

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.get(
                f"{self.base_url}/v1beta/models", headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
            # name format: "models/gemini-3-1-pro"
            return [
                m["name"].split("/", 1)[1] if "/" in m["name"] else m["name"]
                for m in data.get("models", [])
            ]

    async def _post(self, model: str, payload: dict) -> tuple[dict, int]:
        url = f"{self.base_url}/v1beta/models/{model}:generateContent"
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            body = resp.json()
        latency_ms = int((time.monotonic() - start) * 1000)
        return body, latency_ms

    def _parse(self, body: dict, latency_ms: int) -> ChatResult:
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for cand in body.get("candidates", []):
            for p in cand.get("content", {}).get("parts", []):
                if "text" in p:
                    text_parts.append(p["text"])
                elif "functionCall" in p:
                    fc = p["functionCall"]
                    tool_calls.append(
                        {
                            "id": None,
                            "name": fc.get("name"),
                            "arguments": fc.get("args", {}),
                        }
                    )
        usage = body.get("usageMetadata", {})
        return ChatResult(
            text="".join(text_parts),
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
            total_latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw=body,
        )

    async def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        msgs = list(messages)
        payload: dict = {
            "contents": self._to_contents(msgs),
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        sys = self._system(msgs)
        if sys:
            payload["systemInstruction"] = sys

        body, latency_ms = await self._post(model, payload)
        return self._parse(body, latency_ms)

    async def chat_with_tools(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        tools: list[ToolDefinition],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        msgs = list(messages)
        payload: dict = {
            "contents": self._to_contents(msgs),
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        }
                        for t in tools
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        sys = self._system(msgs)
        if sys:
            payload["systemInstruction"] = sys

        body, latency_ms = await self._post(model, payload)
        return self._parse(body, latency_ms)
```

- [ ] **Step 4: Run test，确认通过**

Run: `python -m pytest tests/test_adapters/test_google.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/detector/adapters/google.py tests/test_adapters/test_google.py
git commit -m "feat(adapters): implement Google generateContent adapter with functionCall parsing"
```

---

## Task 11: Dimension 抽象基类 + 注册表

**Files:**
- Create: `app/detector/dimensions/__init__.py`
- Create: `app/detector/dimensions/base.py`
- Test: `tests/test_dimensions/__init__.py`

- [ ] **Step 1: 创建 `tests/test_dimensions/__init__.py`**

```python
```

- [ ] **Step 2: 实现 `app/detector/dimensions/base.py`**

```python
"""Dimension ABC. Each dimension is a self-contained probe that takes a context
(adapter + baseline + budget + RNG) and returns a DimensionResult."""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.detector.adapters.base import Adapter
from app.detector.baselines import Baseline
from app.detector.budget import BudgetTracker
from app.detector.types import DimensionResult, RoundLog


@dataclass
class DimensionContext:
    adapter: Adapter
    baseline: Baseline
    budget: BudgetTracker
    rng: random.Random
    rounds_log: list[RoundLog]
    rounds: int  # caller-requested round budget across all dimensions


class Dimension(ABC):
    name: str  # subclass sets this
    weight: float  # subclass sets this (used by scoring)

    @abstractmethod
    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        ...
```

- [ ] **Step 3: 实现 `app/detector/dimensions/__init__.py`**

```python
"""Dimension registry — list order is also presentation order."""
from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.dimensions.identity_consistency import IdentityConsistency
from app.detector.dimensions.online import Online
from app.detector.dimensions.token_billing import TokenBilling
from app.detector.dimensions.tool_use import ToolUse

ALL_DIMENSIONS: list[type[Dimension]] = [
    Online,
    IdentityConsistency,
    TokenBilling,
    ToolUse,
]

__all__ = [
    "ALL_DIMENSIONS",
    "Dimension",
    "DimensionContext",
    "Online",
    "IdentityConsistency",
    "TokenBilling",
    "ToolUse",
]
```

(注：Step 3 中 import 的 4 个 dimension 类将在 Task 12-15 中创建。本任务只验证 base.py。完整 import 通过会在 Task 15 末尾实现。)

- [ ] **Step 4: 验证 base 可导入**

Run: `python -c "from app.detector.dimensions.base import Dimension, DimensionContext; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add app/detector/dimensions/base.py tests/test_dimensions/__init__.py
git commit -m "feat(dimensions): add Dimension ABC and DimensionContext"
```

---

## Task 12: Dimension `Online`

**Files:**
- Create: `app/detector/dimensions/online.py`
- Test: `tests/test_dimensions/test_online.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_dimensions/test_online.py`:

```python
import random
from unittest.mock import AsyncMock

import httpx
import pytest

from app.detector.baselines import load_baselines
from app.detector.budget import BudgetTracker
from app.detector.dimensions.base import DimensionContext
from app.detector.dimensions.online import Online
from app.detector.types import ChatResult


def _make_ctx(adapter):
    baseline = load_baselines()["claude-opus-4-7"]
    return DimensionContext(
        adapter=adapter,
        baseline=baseline,
        budget=BudgetTracker(budget_usd=1.0),
        rng=random.Random(0),
        rounds_log=[],
        rounds=11,
    )


async def test_online_when_models_and_chat_succeed():
    adapter = AsyncMock()
    adapter.list_models.return_value = ["claude-opus-4-7"]
    adapter.chat.return_value = ChatResult(
        text="hi", prompt_tokens=2, completion_tokens=1, total_latency_ms=100
    )
    result = await Online().evaluate(_make_ctx(adapter))
    assert result.score == 100
    assert result.status == "ok"
    assert result.evidence["models_endpoint_ok"] is True
    assert result.evidence["chat_endpoint_ok"] is True


async def test_online_when_models_endpoint_fails_but_chat_ok():
    adapter = AsyncMock()
    adapter.list_models.side_effect = httpx.HTTPError("404")
    adapter.chat.return_value = ChatResult(
        text="hi", prompt_tokens=2, completion_tokens=1, total_latency_ms=100
    )
    result = await Online().evaluate(_make_ctx(adapter))
    # chat succeeded, so still online but degraded
    assert result.status == "ok"
    assert result.evidence["models_endpoint_ok"] is False
    assert result.evidence["chat_endpoint_ok"] is True
    assert result.score < 100


async def test_online_when_chat_fails():
    adapter = AsyncMock()
    adapter.list_models.return_value = []
    adapter.chat.side_effect = httpx.HTTPError("connection refused")
    result = await Online().evaluate(_make_ctx(adapter))
    assert result.status == "missing"
    assert result.score == 0
    assert "connection refused" in result.evidence["error"]
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_dimensions/test_online.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 实现 `app/detector/dimensions/online.py`**

```python
"""Online check: hit /v1/models + a single minimal chat. Short-circuit gate for the rest."""
from __future__ import annotations

from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.types import ChatMessage, DimensionResult


class Online(Dimension):
    name = "online"
    weight = 0.20

    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        evidence: dict = {
            "models_endpoint_ok": False,
            "chat_endpoint_ok": False,
            "error": None,
        }

        try:
            models = await ctx.adapter.list_models()
            evidence["models_endpoint_ok"] = True
            evidence["model_count"] = len(models)
        except Exception as e:  # network, 4xx, 5xx, parse — all fall through to chat probe
            evidence["models_endpoint_ok"] = False
            evidence["models_error"] = str(e)

        try:
            chat = await ctx.adapter.chat(
                model=ctx.baseline.name,
                messages=[ChatMessage(role="user", content="hi")],
                max_tokens=10,
            )
            evidence["chat_endpoint_ok"] = True
            evidence["sample_response_excerpt"] = chat.text[:80]
            ctx.budget.charge(
                model=ctx.baseline.name,
                prompt_tokens=chat.prompt_tokens,
                completion_tokens=chat.completion_tokens,
            )
        except Exception as e:
            evidence["chat_endpoint_ok"] = False
            evidence["error"] = str(e)
            return DimensionResult(
                name=self.name, score=0, status="missing", evidence=evidence,
                error=str(e),
            )

        # chat ok; partial credit if /v1/models broken
        score = 100 if evidence["models_endpoint_ok"] else 80
        return DimensionResult(
            name=self.name, score=score, status="ok", evidence=evidence
        )
```

- [ ] **Step 4: Run test，确认通过**

Run: `python -m pytest tests/test_dimensions/test_online.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/detector/dimensions/online.py tests/test_dimensions/test_online.py
git commit -m "feat(dimensions): add online dimension (models + minimal chat probe)"
```

---

## Task 13: Dimension `IdentityConsistency`

**Files:**
- Create: `app/detector/dimensions/identity_consistency.py`
- Test: `tests/test_dimensions/test_identity_consistency.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_dimensions/test_identity_consistency.py`:

```python
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
    assert result.status in ("degraded", "missing")
    assert result.score < 90
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_dimensions/test_identity_consistency.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 实现 `app/detector/dimensions/identity_consistency.py`**

```python
"""Multi-round identity probe. Cross-checks self-reported identity against baseline."""
from __future__ import annotations

from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.probes import draw
from app.detector.types import ChatMessage, DimensionResult, RoundLog

DEFAULT_PROBE_ROUNDS = 5


class IdentityConsistency(Dimension):
    name = "identity_consistency"
    weight = 0.35

    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        baseline = ctx.baseline
        n_rounds = min(DEFAULT_PROBE_ROUNDS, max(3, ctx.rounds // 3))

        responses: list[str] = []
        forbidden_hits: list[str] = []
        expected_hits: list[str] = []
        per_round: list[dict] = []

        for i in range(n_rounds):
            prompt, nonce = draw("identity", rng=ctx.rng)
            try:
                result = await ctx.adapter.chat(
                    model=baseline.name,
                    messages=[ChatMessage(role="user", content=prompt)],
                    max_tokens=80,
                )
                ctx.budget.charge(
                    model=baseline.name,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                )
            except Exception as e:
                per_round.append({"round": i, "error": str(e)})
                continue

            text = result.text.lower()
            responses.append(result.text)
            round_expected = [
                kw for kw in baseline.expected_identity_keywords if kw.lower() in text
            ]
            round_forbidden = [
                kw for kw in baseline.forbidden_identity_keywords if kw.lower() in text
            ]
            expected_hits.extend(round_expected)
            forbidden_hits.extend(round_forbidden)

            verdict = "match" if round_expected and not round_forbidden else (
                "mismatch" if round_forbidden else "vague"
            )
            ctx.rounds_log.append(
                RoundLog(
                    round=len(ctx.rounds_log) + 1,
                    dimension=self.name,
                    prompt=prompt,
                    response_excerpt=result.text[:200],
                    verdict=verdict,
                    duration_ms=result.total_latency_ms,
                )
            )
            per_round.append(
                {
                    "round": i,
                    "prompt": prompt,
                    "response_excerpt": result.text[:200],
                    "verdict": verdict,
                }
            )

        evidence = {
            "rounds_completed": len(responses),
            "expected_hits": list(set(expected_hits)),
            "forbidden_hits": list(set(forbidden_hits)),
            "per_round": per_round,
        }

        # If any forbidden vendor leaked, this is fake.
        if forbidden_hits:
            return DimensionResult(
                name=self.name, score=0, status="missing", evidence=evidence
            )

        if len(responses) == 0:
            return DimensionResult(
                name=self.name, score=0, status="error", evidence=evidence,
                error="no successful identity probe rounds"
            )

        match_rate = len(set(expected_hits)) / max(1, len(baseline.expected_identity_keywords))
        # 80%+ keyword coverage => 95
        # 50-80%                => 70
        # <50%                  => 30
        if match_rate >= 0.8:
            score, status = 95, "ok"
        elif match_rate >= 0.5:
            score, status = 70, "degraded"
        else:
            score, status = 30, "degraded"

        return DimensionResult(
            name=self.name, score=score, status=status, evidence=evidence
        )
```

- [ ] **Step 4: Run test，确认通过**

Run: `python -m pytest tests/test_dimensions/test_identity_consistency.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/detector/dimensions/identity_consistency.py tests/test_dimensions/test_identity_consistency.py
git commit -m "feat(dimensions): add identity consistency multi-round probe"
```

---

## Task 14: Dimension `TokenBilling`

**Files:**
- Create: `app/detector/dimensions/token_billing.py`
- Test: `tests/test_dimensions/test_token_billing.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_dimensions/test_token_billing.py`:

```python
import random
from unittest.mock import AsyncMock

from app.detector.baselines import load_baselines
from app.detector.budget import BudgetTracker
from app.detector.dimensions.base import DimensionContext
from app.detector.dimensions.token_billing import TokenBilling
from app.detector.types import ChatResult


def _ctx(adapter):
    baseline = load_baselines()["claude-opus-4-7"]
    return DimensionContext(
        adapter=adapter,
        baseline=baseline,
        budget=BudgetTracker(budget_usd=1.0),
        rng=random.Random(0),
        rounds_log=[],
        rounds=11,
    )


# Fixed prompt "Repeat after me: hello world" tokenizes to a small known count.
# We don't compute exact ground-truth — we test deviation behavior.

async def test_no_deviation_when_token_counts_close_to_expected():
    # Use realistic counts; prompt itself in the dimension is fixed.
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=8,  # near expected
        completion_tokens=2,
        total_latency_ms=100,
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.status == "ok"
    assert result.score >= 90
    assert result.evidence["deviation_pct"] < 15.0


async def test_high_deviation_flagged():
    adapter = AsyncMock()
    # Massively inflated prompt token count: > 30% deviation
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=200,
        completion_tokens=2,
        total_latency_ms=100,
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.status in ("degraded", "missing")
    assert result.score <= 70
    assert result.evidence["deviation_pct"] > 30.0


async def test_zero_tokens_marked_error():
    adapter = AsyncMock()
    adapter.chat.return_value = ChatResult(
        text="hello world",
        prompt_tokens=0,
        completion_tokens=0,
        total_latency_ms=100,
    )
    result = await TokenBilling().evaluate(_ctx(adapter))
    assert result.status == "error"
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_dimensions/test_token_billing.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 实现 `app/detector/dimensions/token_billing.py`**

```python
"""Token-billing deviation. Sends the same fixed prompt 3 times, computes deviation
from a tokenizer-family-specific expected count."""
from __future__ import annotations

import statistics

from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.types import ChatMessage, DimensionResult, RoundLog

# Fixed prompt designed so tokenizer count is stable & low-cost.
FIXED_PROMPT = "Repeat after me: hello world"

# Approximate prompt_token expectation per tokenizer family.
# Real systems would use vendor tokenizer libs; here we use a coarse heuristic.
EXPECTED_PROMPT_TOKENS = {
    "anthropic": 9,   # claude tokenizer: ~9 tokens for "Repeat after me: hello world"
    "openai":    8,   # cl100k_base: ~8 tokens
    "google":    9,
}


class TokenBilling(Dimension):
    name = "token_billing"
    weight = 0.20
    rounds_used = 3

    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        baseline = ctx.baseline
        expected = EXPECTED_PROMPT_TOKENS.get(baseline.tokenizer, 9)

        observed: list[int] = []
        per_round: list[dict] = []
        last_error: str | None = None

        for i in range(self.rounds_used):
            try:
                result = await ctx.adapter.chat(
                    model=baseline.name,
                    messages=[ChatMessage(role="user", content=FIXED_PROMPT)],
                    max_tokens=20,
                )
                ctx.budget.charge(
                    model=baseline.name,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                )
                observed.append(result.prompt_tokens)
                per_round.append(
                    {
                        "round": i,
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                    }
                )
                ctx.rounds_log.append(
                    RoundLog(
                        round=len(ctx.rounds_log) + 1,
                        dimension=self.name,
                        prompt=FIXED_PROMPT,
                        response_excerpt=result.text[:200],
                        verdict=f"prompt_tokens={result.prompt_tokens}",
                        duration_ms=result.total_latency_ms,
                    )
                )
            except Exception as e:
                last_error = str(e)
                per_round.append({"round": i, "error": last_error})

        if not observed or all(v == 0 for v in observed):
            return DimensionResult(
                name=self.name, score=0, status="error",
                evidence={"per_round": per_round, "expected": expected},
                error=last_error or "no observed token counts",
            )

        median_actual = statistics.median(observed)
        deviation_pct = abs(median_actual - expected) / expected * 100

        # 0-5%   -> 100
        # 5-15%  -> 90 -> 70
        # 15-30% -> 70 -> 40
        # >30%   -> 0
        if deviation_pct < 5:
            score, status = 100, "ok"
        elif deviation_pct < 15:
            score, status = max(70, int(100 - deviation_pct * 2)), "ok"
        elif deviation_pct < 30:
            score, status = max(40, int(100 - deviation_pct * 2)), "degraded"
        else:
            score, status = 0, "missing"

        return DimensionResult(
            name=self.name, score=score, status=status,
            evidence={
                "expected": expected,
                "observed_median": median_actual,
                "observed_all": observed,
                "deviation_pct": round(deviation_pct, 2),
                "per_round": per_round,
            },
        )
```

- [ ] **Step 4: Run test，确认通过**

Run: `python -m pytest tests/test_dimensions/test_token_billing.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/detector/dimensions/token_billing.py tests/test_dimensions/test_token_billing.py
git commit -m "feat(dimensions): add token billing deviation probe"
```

---

## Task 15: Dimension `ToolUse`

**Files:**
- Create: `app/detector/dimensions/tool_use.py`
- Test: `tests/test_dimensions/test_tool_use.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_dimensions/test_tool_use.py`:

```python
import random
from unittest.mock import AsyncMock

from app.detector.baselines import load_baselines
from app.detector.budget import BudgetTracker
from app.detector.dimensions.base import DimensionContext
from app.detector.dimensions.tool_use import ToolUse
from app.detector.types import ChatResult


def _ctx(adapter):
    baseline = load_baselines()["claude-opus-4-7"]
    return DimensionContext(
        adapter=adapter,
        baseline=baseline,
        budget=BudgetTracker(budget_usd=1.0),
        rng=random.Random(0),
        rounds_log=[],
        rounds=11,
    )


async def test_proper_tool_call_returns_ok():
    adapter = AsyncMock()
    adapter.chat_with_tools.return_value = ChatResult(
        text="",
        prompt_tokens=20, completion_tokens=8, total_latency_ms=200,
        tool_calls=[{"name": "get_weather", "arguments": {"location": "Tokyo"}}],
    )
    result = await ToolUse().evaluate(_ctx(adapter))
    assert result.status == "ok"
    assert result.score == 100


async def test_text_only_response_marked_degraded():
    adapter = AsyncMock()
    adapter.chat_with_tools.return_value = ChatResult(
        text="I would call the get_weather tool with location Tokyo.",
        prompt_tokens=20, completion_tokens=15, total_latency_ms=200,
        tool_calls=[],
    )
    result = await ToolUse().evaluate(_ctx(adapter))
    assert result.status == "degraded"
    assert result.score == 40


async def test_error_response_marked_missing():
    adapter = AsyncMock()
    adapter.chat_with_tools.side_effect = RuntimeError("tools not supported by upstream")
    result = await ToolUse().evaluate(_ctx(adapter))
    assert result.status == "missing"
    assert result.score == 0
    assert "tools not supported" in result.error


async def test_tool_call_with_wrong_args_partial_credit():
    adapter = AsyncMock()
    adapter.chat_with_tools.return_value = ChatResult(
        text="",
        prompt_tokens=20, completion_tokens=8, total_latency_ms=200,
        # called the right tool but missing required `location` arg
        tool_calls=[{"name": "get_weather", "arguments": {}}],
    )
    result = await ToolUse().evaluate(_ctx(adapter))
    assert result.status == "degraded"
    assert 40 <= result.score < 100
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_dimensions/test_tool_use.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 实现 `app/detector/dimensions/tool_use.py`**

```python
"""tool_use capability probe. Detects whether function calling is genuinely supported."""
from __future__ import annotations

from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.probes import draw
from app.detector.types import ChatMessage, DimensionResult, RoundLog, ToolDefinition

WEATHER_TOOL = ToolDefinition(
    name="get_weather",
    description="Get current weather for a given location.",
    parameters={
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"],
    },
)


class ToolUse(Dimension):
    name = "tool_use"
    weight = 0.25

    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        if not ctx.baseline.supports.get("tool_use", False):
            return DimensionResult(
                name=self.name, score=0, status="skipped",
                evidence={"reason": "baseline marks model as not supporting tool_use"},
            )

        prompt, _nonce = draw("tool_use", rng=ctx.rng)

        try:
            result = await ctx.adapter.chat_with_tools(
                model=ctx.baseline.name,
                messages=[ChatMessage(role="user", content=prompt)],
                tools=[WEATHER_TOOL],
                max_tokens=200,
            )
            ctx.budget.charge(
                model=ctx.baseline.name,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )
        except Exception as e:
            return DimensionResult(
                name=self.name, score=0, status="missing",
                evidence={"prompt": prompt, "error": str(e)},
                error=str(e),
            )

        evidence = {
            "prompt": prompt,
            "tool_calls": result.tool_calls,
            "response_excerpt": result.text[:200],
        }

        if not result.tool_calls:
            ctx.rounds_log.append(
                RoundLog(
                    round=len(ctx.rounds_log) + 1, dimension=self.name,
                    prompt=prompt, response_excerpt=result.text[:200],
                    verdict="text_only", duration_ms=result.total_latency_ms,
                )
            )
            return DimensionResult(
                name=self.name, score=40, status="degraded", evidence=evidence
            )

        # Did the call target the right tool with required args?
        call = result.tool_calls[0]
        right_tool = call.get("name") == WEATHER_TOOL.name
        args = call.get("arguments") or {}
        has_required = "location" in args and bool(args.get("location"))

        if right_tool and has_required:
            score, status, verdict = 100, "ok", "tool_call_ok"
        elif right_tool:
            score, status, verdict = 60, "degraded", "tool_call_missing_args"
        else:
            score, status, verdict = 40, "degraded", "wrong_tool"

        ctx.rounds_log.append(
            RoundLog(
                round=len(ctx.rounds_log) + 1, dimension=self.name,
                prompt=prompt, response_excerpt=str(call)[:200],
                verdict=verdict, duration_ms=result.total_latency_ms,
            )
        )
        return DimensionResult(
            name=self.name, score=score, status=status, evidence=evidence
        )
```

- [ ] **Step 4: Run test，确认通过**

Run: `python -m pytest tests/test_dimensions/test_tool_use.py -v`
Expected: 4 passed.

- [ ] **Step 5: 验证 dimensions 注册表完整 import**

Run: `python -c "from app.detector.dimensions import ALL_DIMENSIONS; print([d.name for d in (cls() for cls in ALL_DIMENSIONS)])"`
Expected: `['online', 'identity_consistency', 'token_billing', 'tool_use']`

- [ ] **Step 6: Commit**

```bash
git add app/detector/dimensions/__init__.py app/detector/dimensions/tool_use.py tests/test_dimensions/test_tool_use.py
git commit -m "feat(dimensions): add tool_use capability probe and register all dimensions"
```

---

## Task 16: 打分聚合 `scoring.py`

**Files:**
- Create: `app/detector/scoring.py`
- Test: `tests/test_scoring.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_scoring.py`:

```python
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
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 实现 `app/detector/scoring.py`**

```python
"""Aggregate per-dimension scores into a final 0-100 score, verdict, and bilingual summary."""
from __future__ import annotations

from app.detector.types import DimensionResult, Verdict

# v0.1 weights (4 dimensions). Dimensions with status="skipped" drop out and
# the remainder is renormalized.
V01_WEIGHTS: dict[str, float] = {
    "online":               0.20,
    "identity_consistency": 0.35,
    "token_billing":        0.20,
    "tool_use":             0.25,
}


def aggregate(results: dict[str, DimensionResult]) -> tuple[int, Verdict]:
    online = results.get("online")
    if online is not None and (online.status == "missing" or online.score == 0):
        return 0, "offline"

    weighted_sum = 0.0
    weight_total = 0.0
    for name, weight in V01_WEIGHTS.items():
        r = results.get(name)
        if r is None or r.status == "skipped":
            continue
        weighted_sum += r.score * weight
        weight_total += weight

    if weight_total == 0:
        return 0, "offline"

    score = round(weighted_sum / weight_total)

    if score >= 90:
        verdict: Verdict = "authentic"
    elif score >= 75:
        verdict = "likely_authentic"
    elif score >= 50:
        verdict = "suspicious"
    else:
        verdict = "likely_fake"

    return score, verdict


_VERDICT_BLURB_ZH = {
    "authentic":         "模型行为高度自洽，符合官方特征。",
    "likely_authentic":  "模型行为大致正常，存在轻微偏差。",
    "suspicious":        "存在多处可疑指标，建议谨慎使用。",
    "likely_fake":       "强烈怀疑模型被替换或能力被阉割。",
    "offline":           "上游接口不可达，无法完成检测。",
}
_VERDICT_BLURB_EN = {
    "authentic":         "Model behavior is highly consistent with official baselines.",
    "likely_authentic":  "Model behavior is mostly correct with minor deviations.",
    "suspicious":        "Several indicators look suspicious; use with caution.",
    "likely_fake":       "Strong evidence the model has been swapped or crippled.",
    "offline":           "Upstream is unreachable; detection could not run.",
}


def summarize(
    results: dict[str, DimensionResult],
    *,
    score: int,
    verdict: Verdict,
    model: str,
) -> tuple[str, str]:
    """Generate bilingual summary by composing per-dimension findings — no LLM call."""
    zh_parts = [_VERDICT_BLURB_ZH[verdict]]
    en_parts = [_VERDICT_BLURB_EN[verdict]]

    # Highlight worst dimension (excluding skipped/online)
    candidates = [
        r for n, r in results.items()
        if n != "online" and r.status not in ("skipped",)
    ]
    if candidates:
        worst = min(candidates, key=lambda r: r.score)
        if worst.score < 70:
            zh_parts.append(f"最弱维度：{worst.name}（{worst.score} 分）。")
            en_parts.append(f"Weakest dimension: {worst.name} (score {worst.score}).")

    zh_parts.append(f"目标模型：{model}，综合得分 {score}/100。")
    en_parts.append(f"Target model: {model}, overall score {score}/100.")

    return " ".join(zh_parts), " ".join(en_parts)
```

- [ ] **Step 4: Run test，确认通过**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add app/detector/scoring.py tests/test_scoring.py
git commit -m "feat(detector): add v0.1 weighted aggregator and bilingual summarizer"
```

---

## Task 17: 编排核心 `core.py` + dry_run 支持

**Files:**
- Create: `app/detector/core.py`
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/mock_responses/anthropic_authentic.json`
- Create: `tests/test_core.py`

- [ ] **Step 1: 创建固化 mock 响应**

`tests/fixtures/__init__.py`:

```python
```

`tests/fixtures/mock_responses/anthropic_authentic.json`:

```json
{
  "list_models": ["claude-opus-4-7", "claude-sonnet-4-6"],
  "chat": {
    "text": "I am Claude, an AI assistant made by Anthropic.",
    "prompt_tokens": 9,
    "completion_tokens": 12,
    "total_latency_ms": 800
  },
  "chat_with_tools": {
    "text": "",
    "prompt_tokens": 25,
    "completion_tokens": 8,
    "total_latency_ms": 950,
    "tool_calls": [
      {"name": "get_weather", "arguments": {"location": "Tokyo"}}
    ]
  }
}
```

- [ ] **Step 2: 写失败的测试**

`tests/test_core.py`:

```python
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
    assert resp.duration_ms > 0
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
```

- [ ] **Step 3: Run test，确认失败**

Run: `python -m pytest tests/test_core.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: 实现 `app/detector/core.py`**

```python
"""Top-level detection orchestrator. Used by both HTTP routes and CLI."""
from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path

from app.detector.adapters import get_adapter
from app.detector.adapters.base import Adapter
from app.detector.baselines import load_baselines
from app.detector.budget import BudgetExceeded, BudgetTracker
from app.detector.dimensions import ALL_DIMENSIONS
from app.detector.dimensions.base import DimensionContext
from app.detector.scoring import aggregate, summarize
from app.detector.types import (
    ChatResult,
    DetectRequest,
    DetectResponse,
    DimensionResult,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mock_responses"


class _MockAdapter:
    """Returns canned responses from a fixture file. Used when dry_run=True."""

    def __init__(self, fixture_name: str, provider: str):
        with open(FIXTURES_DIR / fixture_name, encoding="utf-8") as f:
            self._data = json.load(f)
        self.provider = provider

    async def list_models(self):
        return list(self._data.get("list_models", []))

    async def chat(self, model, messages, max_tokens=256, temperature=0.0):
        d = self._data["chat"]
        return ChatResult(
            text=d["text"],
            prompt_tokens=d["prompt_tokens"],
            completion_tokens=d["completion_tokens"],
            total_latency_ms=d["total_latency_ms"],
            tool_calls=d.get("tool_calls", []),
            raw=d,
        )

    async def chat_with_tools(
        self, model, messages, tools, max_tokens=256, temperature=0.0
    ):
        d = self._data["chat_with_tools"]
        return ChatResult(
            text=d["text"],
            prompt_tokens=d["prompt_tokens"],
            completion_tokens=d["completion_tokens"],
            total_latency_ms=d["total_latency_ms"],
            tool_calls=d.get("tool_calls", []),
            raw=d,
        )


def _resolve_provider(model: str, override: str | None) -> str:
    if override:
        return override
    baselines = load_baselines()
    if model not in baselines:
        raise ValueError(f"unknown model: {model!r}")
    return baselines[model].provider


def _build_adapter(req: DetectRequest, provider: str) -> Adapter | _MockAdapter:
    if req.dry_run:
        # provider -> default authentic fixture
        return _MockAdapter(
            fixture_name=f"{provider}_authentic.json", provider=provider
        )
    return get_adapter(provider, base_url=req.base_url, api_key=req.api_key)


async def run_detection(req: DetectRequest) -> DetectResponse:
    started = time.monotonic()
    task_id = req.task_id or uuid.uuid4().hex
    baselines = load_baselines()

    if req.model not in baselines:
        raise ValueError(f"unknown model: {req.model!r}")
    baseline = baselines[req.model]

    provider = _resolve_provider(req.model, req.expected_provider)
    adapter = _build_adapter(req, provider)
    budget = BudgetTracker(budget_usd=req.budget_usd)
    rng = random.Random()

    rounds_log: list = []
    ctx = DimensionContext(
        adapter=adapter,
        baseline=baseline,
        budget=budget,
        rng=rng,
        rounds_log=rounds_log,
        rounds=req.rounds,
    )

    results: dict[str, DimensionResult] = {}
    over_budget = False
    warnings: list[str] = []

    for cls in ALL_DIMENSIONS:
        dim = cls()

        # short-circuit: if online failed, mark every later dim as skipped
        if (
            dim.name != "online"
            and "online" in results
            and results["online"].status == "missing"
        ):
            results[dim.name] = DimensionResult(
                name=dim.name, score=0, status="skipped",
                evidence={"reason": "online check failed; downstream skipped"},
            )
            continue

        try:
            r = await dim.evaluate(ctx)
        except BudgetExceeded as e:
            over_budget = True
            warnings.append(f"budget exceeded during {dim.name}: {e}")
            r = DimensionResult(
                name=dim.name, score=0, status="error",
                evidence={"budget_exceeded": True}, error=str(e),
            )
        except Exception as e:
            r = DimensionResult(
                name=dim.name, score=0, status="error",
                evidence={"unexpected_error": True}, error=str(e),
            )
        results[dim.name] = r

    score, verdict = aggregate(results)
    summary_zh, summary_en = summarize(
        results, score=score, verdict=verdict, model=req.model
    )

    capability_flags = {
        n: results[n].status if n in results else "skipped"
        for n in ("tool_use",)  # v0.1 only tool_use; v0.2 adds web_search, sub_agent
    }

    duration_ms = int((time.monotonic() - started) * 1000)

    return DetectResponse(
        task_id=task_id,
        status="completed",
        score=score,
        verdict=verdict,
        summary_zh=summary_zh,
        summary_en=summary_en,
        dimensions=results,
        capability_flags=capability_flags,
        rounds_log=rounds_log if req.verbose else rounds_log[:20],
        actual_cost_usd=round(budget.spent_usd, 6),
        duration_ms=duration_ms,
        over_budget=over_budget,
        warnings=warnings,
    )
```

- [ ] **Step 5: 创建 OpenAI 和 Google 的 fixture（让其他 provider 也能 dry_run）**

`tests/fixtures/mock_responses/openai_authentic.json`:

```json
{
  "list_models": ["gpt-5-5", "gpt-5-4"],
  "chat": {
    "text": "I'm GPT, a large language model from OpenAI.",
    "prompt_tokens": 8,
    "completion_tokens": 11,
    "total_latency_ms": 600
  },
  "chat_with_tools": {
    "text": "",
    "prompt_tokens": 22,
    "completion_tokens": 7,
    "total_latency_ms": 720,
    "tool_calls": [
      {"name": "get_weather", "arguments": {"location": "Tokyo"}}
    ]
  }
}
```

`tests/fixtures/mock_responses/google_authentic.json`:

```json
{
  "list_models": ["gemini-3-1-pro"],
  "chat": {
    "text": "I am Gemini, a model developed by Google.",
    "prompt_tokens": 9,
    "completion_tokens": 11,
    "total_latency_ms": 1000
  },
  "chat_with_tools": {
    "text": "",
    "prompt_tokens": 24,
    "completion_tokens": 8,
    "total_latency_ms": 1100,
    "tool_calls": [
      {"name": "get_weather", "arguments": {"location": "Tokyo"}}
    ]
  }
}
```

- [ ] **Step 6: 导出 public 接口**

修改 `app/detector/__init__.py`:

```python
"""Detector core library — pure Python, no FastAPI deps."""
from app.detector.core import run_detection
from app.detector.baselines import load_baselines
from app.detector.types import DetectRequest, DetectResponse

__all__ = ["run_detection", "load_baselines", "DetectRequest", "DetectResponse"]
```

- [ ] **Step 7: Run test，确认通过**

Run: `python -m pytest tests/test_core.py -v`
Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add app/detector/core.py app/detector/__init__.py tests/fixtures/ tests/test_core.py
git commit -m "feat(detector): add core orchestrator with dry-run mock adapter"
```

---

## Task 18: FastAPI 入口 + 路由 `/detect` 与 `/healthz`

**Files:**
- Create: `app/main.py`
- Create: `app/routes/__init__.py`
- Create: `app/routes/detect.py`
- Create: `app/routes/health.py`
- Test: `tests/test_routes.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_detect_dry_run_authentic(client):
    r = client.post(
        "/detect",
        json={
            "base_url": "https://x",
            "api_key": "sk-test",
            "model": "claude-opus-4-7",
            "rounds": 11,
            "budget_usd": 0.5,
            "dry_run": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["score"] >= 90
    assert body["verdict"] == "authentic"
    assert "claude-opus-4-7" in body["summary_zh"] or "Claude" in body["summary_zh"]
    assert "online" in body["dimensions"]


def test_detect_unknown_model_returns_400(client):
    r = client.post(
        "/detect",
        json={
            "base_url": "https://x",
            "api_key": "sk-test",
            "model": "no-such-model",
            "dry_run": True,
        },
    )
    assert r.status_code == 400
    assert "unknown model" in r.json()["detail"].lower()


def test_detect_validation_rounds_too_high_returns_422(client):
    r = client.post(
        "/detect",
        json={
            "base_url": "https://x",
            "api_key": "sk-test",
            "model": "claude-opus-4-7",
            "rounds": 9999,
        },
    )
    assert r.status_code == 422


def test_detect_does_not_leak_api_key(client, caplog):
    import logging

    caplog.set_level(logging.INFO)
    client.post(
        "/detect",
        json={
            "base_url": "https://x",
            "api_key": "sk-VERYSECRETKEY12345",
            "model": "claude-opus-4-7",
            "dry_run": True,
        },
    )
    full = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "sk-VERYSECRETKEY12345" not in full
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_routes.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 实现 `app/routes/__init__.py`**

```python
```

- [ ] **Step 4: 实现 `app/routes/health.py`**

```python
import time

from fastapi import APIRouter

router = APIRouter()
_START = time.monotonic()


@router.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_s": int(time.monotonic() - _START),
    }
```

- [ ] **Step 5: 实现 `app/routes/detect.py`**

```python
import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.detector import run_detection
from app.detector.log_redact import redact
from app.detector.types import DetectRequest, DetectResponse

router = APIRouter()
log = logging.getLogger("detector.routes")

SYNC_TIMEOUT_S = 60.0


@router.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest) -> DetectResponse:
    log.info(
        "detect request received: base=%s model=%s rounds=%s",
        redact(req.base_url),
        req.model,
        req.rounds,
    )
    try:
        return await asyncio.wait_for(run_detection(req), timeout=SYNC_TIMEOUT_S)
    except asyncio.TimeoutError as e:
        raise HTTPException(
            status_code=408,
            detail="detection exceeded 60s; use mode='async' for long runs",
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
```

- [ ] **Step 6: 实现 `app/main.py`**

```python
"""FastAPI application factory + uvicorn entry."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.detector.log_redact import install_global_filter
from app.routes.detect import router as detect_router
from app.routes.health import router as health_router


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    install_global_filter()
    app = FastAPI(title="AI Relay Detector", version="0.1.0")
    app.include_router(health_router)
    app.include_router(detect_router)
    return app


app = create_app()
```

- [ ] **Step 7: Run test，确认通过**

Run: `python -m pytest tests/test_routes.py -v`
Expected: 5 passed.

- [ ] **Step 8: 手动启动验证**

Run: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8800`
Expected: 服务启动，输出包含 `Uvicorn running on http://127.0.0.1:8800`。
Stop with Ctrl+C.

- [ ] **Step 9: Commit**

```bash
git add app/main.py app/routes/ tests/test_routes.py
git commit -m "feat(api): add FastAPI app with /detect and /healthz routes plus 60s sync timeout"
```

---

## Task 19: CLI 入口 `app/cli.py`

**Files:**
- Create: `app/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_cli.py`:

```python
import json
import sys

from app.cli import main


def test_cli_dry_run_prints_report(capsys, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detector",
            "--base", "https://x.example",
            "--key", "sk-test",
            "--model", "claude-opus-4-7",
            "--rounds", "11",
            "--budget", "0.5",
            "--dry-run",
            "--json",
        ],
    )
    rc = main()
    assert rc == 0
    out = capsys.readouterr().out
    body = json.loads(out)
    assert body["verdict"] == "authentic"
    assert body["score"] >= 90


def test_cli_unknown_model_returns_2(capsys, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detector",
            "--base", "https://x",
            "--key", "sk-test",
            "--model", "no-such",
            "--dry-run",
        ],
    )
    rc = main()
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown model" in err.lower()


def test_cli_pretty_output_human_readable(capsys, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detector",
            "--base", "https://x",
            "--key", "sk-test",
            "--model", "claude-opus-4-7",
            "--dry-run",
        ],
    )
    rc = main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "verdict" in out.lower()
    assert "score" in out.lower()
```

- [ ] **Step 2: Run test，确认失败**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 实现 `app/cli.py`**

```python
"""CLI entry: `python -m app.cli --base ... --key ... --model ...`."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from app.detector import run_detection
from app.detector.log_redact import install_global_filter
from app.detector.types import DetectRequest


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="detector", description="AI relay station detector")
    p.add_argument("--base", required=True, help="upstream base URL, e.g. https://api.example.com")
    p.add_argument("--key", required=True, help="API key")
    p.add_argument("--model", required=True, help="target model id")
    p.add_argument("--provider", default=None, help="optional provider override")
    p.add_argument("--rounds", type=int, default=11)
    p.add_argument("--budget", type=float, default=0.5, help="USD budget cap")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--json", action="store_true", help="emit raw JSON only")
    return p.parse_args(argv)


def _format_pretty(report: dict) -> str:
    lines = [
        f"Verdict: {report['verdict']}",
        f"Score:   {report['score']}/100",
        f"Model:   {report.get('summary_en', '')}",
        "",
        "Dimensions:",
    ]
    for name, dim in report["dimensions"].items():
        lines.append(f"  - {name:<22} {dim['score']:>3}  [{dim['status']}]")
    lines.append("")
    lines.append(f"Cost:     ${report['actual_cost_usd']:.4f}")
    lines.append(f"Duration: {report['duration_ms']} ms")
    if report.get("over_budget"):
        lines.append("⚠ over_budget=true")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    install_global_filter()

    req = DetectRequest(
        base_url=args.base,
        api_key=args.key,
        model=args.model,
        expected_provider=args.provider,
        rounds=args.rounds,
        budget_usd=args.budget,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    try:
        resp = asyncio.run(run_detection(req))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    body = resp.model_dump()
    if args.json:
        print(json.dumps(body, ensure_ascii=False, indent=2))
    else:
        print(_format_pretty(body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test，确认通过**

Run: `python -m pytest tests/test_cli.py -v`
Expected: 3 passed.

- [ ] **Step 5: 手动验证 CLI**

Run: `python -m app.cli --base https://x --key sk-test --model claude-opus-4-7 --dry-run`
Expected: 输出包含 `Verdict: authentic`, `Score: 9X/100`。

- [ ] **Step 6: Commit**

```bash
git add app/cli.py tests/test_cli.py
git commit -m "feat(cli): add command-line entry for detector with pretty and JSON output"
```

---

## Task 20: Dockerfile + docker-compose.yml

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: 写 `.dockerignore`**

```
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.git/
.gitignore
*.md
docs/
tests/
.coverage
*.egg-info/
build/
dist/
```

- [ ] **Step 2: 写 `Dockerfile`**

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# system deps kept minimal — only what httpx + pyyaml need
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e .

COPY app/ ./app/
COPY data/ ./data/

EXPOSE 8800

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://127.0.0.1:8800/healthz', timeout=2).raise_for_status()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8800", "--workers", "1"]
```

- [ ] **Step 3: 写 `docker-compose.yml`**

```yaml
services:
  detector:
    build: .
    image: ai-relay-detector:0.1.0
    container_name: ai-relay-detector
    restart: unless-stopped
    ports:
      - "127.0.0.1:8800:8800"
    environment:
      DETECTOR_LOG_LEVEL: INFO
      DETECTOR_DEFAULT_BUDGET_USD: "0.5"
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
```

- [ ] **Step 4: 构建并验证镜像**

Run: `docker compose build`
Expected: 构建成功，无错误。

Run: `docker compose up -d`
Expected: 容器启动。

Run: `curl http://127.0.0.1:8800/healthz`
Expected: `{"status":"ok","version":"0.1.0",...}`

Run:
```bash
curl -X POST http://127.0.0.1:8800/detect \
  -H "Content-Type: application/json" \
  -d '{"base_url":"https://x","api_key":"sk-test","model":"claude-opus-4-7","dry_run":true}'
```
Expected: JSON 响应，`"verdict":"authentic"`，`"score">=90`。

Run: `docker compose down`

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "build: add Dockerfile and docker-compose for single-host deployment"
```

---

## Task 21: README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: 写 `README.md`**

````markdown
# AI 中转站真伪与能力残缺检测服务

为 yyc.lat AI 网关提供的内部 HTTP 检测服务。给定 `(base_url, api_key, model)` 三元组，返回该上游中转站的真伪可信度评分（0–100）+ verdict 标签 + 维度报告。

## v0.1 支持的模型

| Provider  | Model              |
|-----------|--------------------|
| Anthropic | claude-opus-4-7    |
| Anthropic | claude-sonnet-4-6  |
| OpenAI    | gpt-5-5            |
| OpenAI    | gpt-5-4            |
| Google    | gemini-3-1-pro     |

## v0.1 检测维度

- `online` — `/v1/models` + 最简 chat
- `identity_consistency` — 多轮身份探测，与 baseline 关键词比对
- `token_billing` — 同 prompt 多次调用，检测计费 token 数偏离
- `tool_use` — function calling 能力检测（核心差异化点）

## 快速启动（Docker）

```bash
docker compose up -d
curl http://127.0.0.1:8800/healthz
```

## HTTP API

### `POST /detect`

```bash
curl -X POST http://127.0.0.1:8800/detect \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://upstream.example.com",
    "api_key": "sk-...",
    "model": "claude-opus-4-7",
    "rounds": 11,
    "budget_usd": 0.5
  }'
```

字段说明见 `app/detector/types.py` 的 `DetectRequest`。

响应字段见 `DetectResponse`，关键字段：
- `score`: 0–100
- `verdict`: `authentic | likely_authentic | suspicious | likely_fake | offline`
- `dimensions[name].evidence`: 该维度的原始 prompt/response/判定证据
- `capability_flags`: 能力残缺标签
- `actual_cost_usd`: 实际花费（基于 baseline 估算）
- `over_budget`: 是否触发预算上限

### `GET /healthz`

```bash
curl http://127.0.0.1:8800/healthz
# {"status":"ok","version":"0.1.0","uptime_s":42}
```

## CLI 调试

```bash
# 真实检测
python -m app.cli --base https://upstream.example.com --key sk-xxx \
  --model claude-opus-4-7 --rounds 11 --budget 0.5

# 不调用真实 API，验证流程
python -m app.cli --base https://x --key sk-test \
  --model claude-opus-4-7 --dry-run

# JSON 输出（便于 jq 处理）
python -m app.cli --base https://x --key sk-test \
  --model claude-opus-4-7 --dry-run --json
```

## 开发

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -e ".[dev]"
pytest -v
ruff check .
```

## 部署到 yyc.lat

服务监听 `127.0.0.1:8800`，由 yyc.lat 的 nginx 内网代理：

```nginx
location /api/relay-detector/ {
  proxy_pass http://127.0.0.1:8800/;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_read_timeout 90s;
}
```

Go 后端调用示例：

```go
type DetectReq struct {
    BaseURL   string  `json:"base_url"`
    APIKey    string  `json:"api_key"`
    Model     string  `json:"model"`
    Rounds    int     `json:"rounds"`
    BudgetUSD float64 `json:"budget_usd"`
}

resp, err := http.Post(
    "http://127.0.0.1:8800/detect",
    "application/json",
    bytes.NewReader(payload),
)
```

## 安全

- API key 全程脱敏：日志中只保留 `sk-XXX***XX` 形式
- 服务仅监听 127.0.0.1，由 nginx 控制对外暴露
- 单次请求设有 USD 预算上限，超出立即中止
- Docker 容器运行在 `read_only` + `no-new-privileges`

## Roadmap

- v0.2: 加 `protocol_consistency` / `knowledge_signature` / `web_search` / `sub_agent` + 异步任务 + SQLite 缓存
- v0.3: `/compare` + baseline 扩到 50+ 模型
- v0.4: 完整双语 summary 自动组装
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with API, CLI, deployment, and security notes"
```

---

## Task 22: 全量测试 + E2E 烟测 + 验收

**Files:** none new, validation only.

- [ ] **Step 1: 全量测试**

Run: `python -m pytest -v --tb=short`
Expected: 所有测试通过；总数应 ≥ 35。

- [ ] **Step 2: 覆盖率检查**

Run: `pip install pytest-cov && python -m pytest --cov=app/detector --cov-report=term-missing`
Expected: `app/detector/` 覆盖率 ≥ 85%。

如果覆盖率不足 85%，**不要标记任务完成**——回看哪个文件覆盖率最低，补一个针对性测试再来。

- [ ] **Step 3: ruff 检查**

Run: `python -m ruff check .`
Expected: `All checks passed!`

- [ ] **Step 4: 启动服务并 E2E 烟测**

Run: `docker compose up -d`

Run:
```bash
# 1) healthz
curl -sS http://127.0.0.1:8800/healthz | python -m json.tool
# Expected: {"status":"ok",...}

# 2) authentic detect via dry-run
curl -sS -X POST http://127.0.0.1:8800/detect \
  -H "Content-Type: application/json" \
  -d '{"base_url":"https://x","api_key":"sk-VERYSECRET","model":"claude-opus-4-7","dry_run":true}' \
  | python -m json.tool
# Expected: verdict="authentic", score >= 90, dimensions has 4 entries

# 3) unknown model should 400
curl -sS -X POST http://127.0.0.1:8800/detect \
  -H "Content-Type: application/json" \
  -d '{"base_url":"https://x","api_key":"sk-test","model":"no-such-model","dry_run":true}' \
  -w "\nHTTP %{http_code}\n"
# Expected: HTTP 400

# 4) check logs do not leak api_key
docker logs ai-relay-detector 2>&1 | grep -E "sk-VERYSECRET" || echo "PASS: no key leak"
# Expected: PASS: no key leak
```

Run: `docker compose down`

- [ ] **Step 5: 走完验收清单**

打勾每项（每项失败必须先修复，禁止继续）：

- [ ] `POST /detect` 用 `dry_run=true` 检测 `claude-opus-4-7` 返回 score ≥ 90 且 verdict=`authentic`
- [ ] `tool_use` 维度对返回纯文本（无 tool_calls）的 mock 上游正确判定 `degraded`，score=40
- [ ] 日志中 API key 全部脱敏为 `sk-***xx`
- [ ] 预算超限时返回 `over_budget=true` 且不抛异常给 client
- [ ] CLI `python -m app.cli --dry-run` 能完整跑出报告
- [ ] Docker 容器启动后 `curl 127.0.0.1:8800/healthz` 返回 200
- [ ] 所有 pytest 通过，覆盖率 ≥ 85%
- [ ] README 包含：快速启动、HTTP API 示例、CLI 示例、yyc 接入示例

- [ ] **Step 6: 最终 commit**

```bash
git add -A
git commit -m "test: pass v0.1 acceptance smoke tests" || echo "nothing to commit"
git tag v0.1.0
```

---

## v0.1 完成后的下一步

提交给 yyc.lat 后端联调。yyc Go 后端通过 `POST /detect` 拿到 JSON 报告，落到自己的 DB 做模型市场页展示。

v0.2 计划开始：补齐 `protocol_consistency` / `knowledge_signature` / `web_search` / `sub_agent` + 异步任务接口。

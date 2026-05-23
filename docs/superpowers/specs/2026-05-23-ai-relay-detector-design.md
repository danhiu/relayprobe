# AI 中转站真伪与能力残缺检测服务 — 设计文档

**Status**: Draft
**Date**: 2026-05-23
**Author**: yyc.lat 团队
**Topic slug**: ai-relay-detector

---

## 1. 背景与目标

`yyc.lat` 是一个 AI 网关 / API 中转聚合平台。当用户接入第三方上游中转站作为后端时，常见以下风险：

- 上游声称转发 Claude Opus 4.7，实际偷换成 GLM、Haiku 或 Sonnet
- 协议返回字段结构不符合官方规范（多/少字段、字段类型异常）
- 模型能力被阉割：tool_use 不可用、function calling 返回纯文本、子 agent 嵌套调用失败、web_search 工具被吞
- 计费 token 数异常偏离基线
- 延迟、稳定性不达预期

参考行业内已有的两个工具：

- **cctest.ai** — 黑盒探测，11 轮请求，主要检测 token 计费异常
- **hvoy.ai** — 多维交叉验证（协议结构 / 知识表现 / 身份一致性 / 思维链 / 签名指纹）

本服务在前两者基础上增加**能力残缺检测**（tool_use / web_search / sub_agent），输出统一打分报告，由 yyc.lat 后端调用，最终在模型市场页和模型接入页对用户展示。

## 2. 范围

### In-scope

- Python 后端 HTTP 服务（FastAPI + httpx + SQLite）
- 检测核心库 `app/detector/`，可被 CLI 和 HTTP 共用
- 三家厂商支持：**Anthropic / OpenAI / Google**
- 5 个固定模型：`claude-opus-4-7`、`claude-sonnet-4-6`、`gpt-5-5`、`gpt-5-4`、`gemini-3-1-pro`
- 8 项检测维度（5 项真伪 + 3 项能力残缺）
- Docker 部署，监听 `127.0.0.1:8800`
- yyc.lat 通过 nginx 内网代理调用，不公开

### Out-of-scope

- 任何前端 UI（yyc.lat 自己实现）
- 用户登录、计费、限流（yyc 网关侧负责）
- 落库长期存储（仅 1h TTL 缓存）
- Telemetry 上报第三方
- 50+ 模型基线（v0.4 再补）

## 3. 架构

```
┌──────────────────────────┐
│  yyc.lat Go backend      │
│  (caller, OpenAI-compat) │
└──────────┬───────────────┘
           │ HTTP (POST /detect)
           ▼
┌──────────────────────────────────────────┐
│  FastAPI app (127.0.0.1:8800)            │
│  ├── routes: /detect /detect/{id}        │
│  │           /benchmark/{model}          │
│  │           /compare /healthz           │
│  ├── cache layer (SQLite, 1h TTL)        │
│  └── async task runner (in-process)      │
└──────────┬───────────────────────────────┘
           │ uses
           ▼
┌──────────────────────────────────────────┐
│  app/detector/  (pure library)           │
│  ├── core.py        scoring + aggregator │
│  ├── adapters/      anthropic/openai/    │
│  │                  google native probes │
│  ├── dimensions/    8 dimension modules  │
│  ├── probes.py      probe pool loader    │
│  ├── budget.py      USD budget guard     │
│  └── log_redact.py  api key masking      │
└──────────┬───────────────────────────────┘
           │ uses
           ▼
   data/baselines.yaml  data/probes.yaml
```

### 关键设计决策

- **核心库与 HTTP 解耦**：`app/detector/` 不依赖 FastAPI/httpx 之外的任何东西，CLI 直接 `from detector import run_detection` 即可
- **三家厂商 = 三个 adapter**：`adapters/anthropic.py`、`openai.py`、`google.py`，每个适配器负责发原生协议请求并把响应归一化为内部统一结构。**对外（yyc 调用方）是 OpenAI 兼容输入**（base_url + api_key + model），但内部对每家走它的原生协议探测，只有原生协议能验出真伪
- **每个维度一个独立 module**：`dimensions/online.py`、`dimensions/identity_consistency.py`、`dimensions/tool_use.py` 等。每个 module 暴露一个 `async def evaluate(ctx) -> DimensionResult`，便于单测、并行、增量上线
- **同步 / 异步双模式**：`rounds <= 20` 默认同步执行；`rounds > 20` 或显式 `mode: "async"` 走 in-process 后台任务，结果存 SQLite，前端通过 `task_id` 轮询
- **预算守卫**：每次 detect 持有一个 `BudgetTracker`，在每次 httpx 调用返回时累加 token 成本，超出 `budget_usd` 立即取消剩余轮次并标记 `over_budget`
- **黑盒防对抗**：probes.yaml 池子里每类问题准备 30+ 条变体，每轮随机抽 + 加随机 nonce（如 `[REQ-{uuid}]`）拼到 prompt 末尾，避免中转站针对固定 prompt 做缓存/特化

## 4. 检测维度详细设计

### A 组 — 真伪检测（5 项）

#### A1. `online`
- **检测方法**: 调 `/v1/models`（或厂商等价端点）+ 一次最简 chat completion (`"hi"`, max_tokens=10)
- **输出**: `{ online: bool, error?: string, models_endpoint_ok: bool, chat_endpoint_ok: bool }`
- **失败短路**: 若 `online=false`，跳过其余 7 项，verdict 直接 `offline`

#### A2. `protocol_consistency`
- **检测方法**: 用厂商原生 SDK 协议格式发请求（Anthropic 走 `/v1/messages`、OpenAI 走 `/v1/chat/completions`、Google 走 `/v1beta/models/.../generateContent`），校验返回字段：
  - 必需字段是否齐全（如 Anthropic 的 `content[].type='text'`、OpenAI 的 `choices[].message.content`、Google 的 `candidates[].content.parts[]`）
  - 字段类型是否正确
  - SSE 流式格式是否合规（独立子项）
- **输出**: 0-100 分，每个缺失/异常字段扣分；附带 raw response 节选

#### A3. `identity_consistency`
- **检测方法**: 5-7 轮身份探测，prompt 来自 `probes.yaml` 的 `identity_probes` 池：
  - "What model are you? Answer in one short sentence."
  - "Who created you?"
  - "What's your training cutoff date?"
  - "Are you Claude / GPT / Gemini?"（针对反向确认）
  - 加 nonce
- **判定**:
  - 所有回答中提取 model_name / vendor / cutoff，与 baselines.yaml 期望对比
  - 跨轮自洽性（同一 session 不同回合不能自相矛盾）
  - 命中率：≥80% → 95 分；50-80% → 70 分；<50% → 30 分；明确自报为其他厂商 → 0 分
- **输出**: 0-100 分 + 每轮 prompt/response/判定理由

#### A4. `knowledge_signature`
- **检测方法**: 厂商指纹问题（`probes.yaml` 的 `signature_probes`）
  - **Anthropic Claude**: 问 Constitutional AI 相关问题、问 "honest, harmless, helpful"；Claude 措辞特征（"I should note..."、"To be clear..."）
  - **OpenAI GPT**: ChatGPT-isms（"As an AI language model"、"It's important to note"、安全免责声明的特定模板）
  - **Google Gemini**: thinking trace 标记（如果是 thinking 模型）、"I'd be happy to help" 句式
- **判定**: 词频/句式打分 + 反向指纹（出现其他厂商指纹则扣分）
- **输出**: 0-100 分

#### A5. `token_billing`
- **检测方法**: 同一固定 prompt 调用 3 次，统计返回的 `usage.prompt_tokens` 和 `usage.completion_tokens`，与该模型/厂商 tokenizer 计算出的预期值比对
- **判定**: 偏离百分比 = `|actual - expected| / expected`
  - <5%: 正常
  - 5-15%: 轻度异常
  - 15-30%: 显著掺水嫌疑
  - >30%: 高度可疑（很可能换了 tokenizer 不同的模型）
- **输出**: `{ deviation_pct: float, expected: int, actual: int }`

### B 组 — 能力残缺检测（3 项，差异化点）

#### B1. `tool_use`
- **检测方法**: 发一个标准 function calling 请求：
  ```python
  tools = [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get current weather for a location",
      "parameters": {
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"]
      }
    }
  }]
  messages = [{"role": "user", "content": "What's the weather in Tokyo?"}]
  ```
- **判定**:
  - 返回正确的 `tool_calls` / `content[].type='tool_use'` 字段 + 参数 JSON 合法 → `ok` (100)
  - 返回纯文本说"我会调用 get_weather 工具" → `degraded` (40)
  - 直接拒绝 / 忽略 tools 参数 / 报错 → `missing` (0)
- **输出**: `{ status: ok|degraded|missing, score: 0-100, raw_response_excerpt }`

#### B2. `web_search`
- **检测方法**: 两步探测
  1. 不带任何工具，问"今天纽约天气怎么样"——baseline：模型应说"我无法联网"或给出训练截止前的常识回答（如果照实回答了具体天气数字 → 可能私自接了搜索）
  2. 带 web_search 工具（如果该模型 baseline 支持），看是否触发 `tool_use` 调用搜索
- **判定**:
  - baseline 行为正确（按厂商应答模式） → `ok`
  - 编造具体实时数据 → `degraded`（说明上游可能私自加了 RAG/搜索且伪装成模型原生输出）
  - 完全无响应 / 忽略工具 → `missing`
- **输出**: `{ status, score, evidence }`

#### B3. `sub_agent`
- **检测方法**: 多轮嵌套 tool_use 测试（厂商无关的统一探测方式）
  - 给模型 2 个工具：`delegate_to_specialist(task)` 和 `final_answer(text)`
  - 用户问一个需要分解的复杂问题
  - 期望：模型先调 delegate，收到 tool_result 后再调 final_answer（=支持嵌套上下文 / 多轮 tool 调用链）
- **三家差异说明**:
  - **Anthropic**: 通过 `/v1/messages` 的多轮 `tool_use` + `tool_result` content block 测试
  - **OpenAI**: 通过 `/v1/chat/completions` 的 `tool_calls` + 多轮 message 测试（tool role）
  - **Google**: 通过 `generateContent` 的 `functionCall` + `functionResponse` part 测试
  - 三家都能用统一的"嵌套 tool 调用链是否完整"标准评估，不依赖厂商特定的"sub-agent SDK 概念"
- **判定**:
  - 完成完整链路（≥2 轮 tool 调用且最终给出 final_answer） → `ok` (100)
  - 第一轮 tool_use ok，第二轮丢失上下文 / 不调 final_answer → `degraded` (40)
  - 第一轮就失败 → `missing` (0)
- **输出**: `{ status, score, turn_count, evidence }`

### 维度汇总打分

仅对已实现的维度计算加权平均。每次发布版本时，只把 enabled 维度纳入分母重新归一化。

**v0.1 权重（4 维度）**:

```python
weights_v01 = {
    "online":               0.20,  # online=false 直接短路返回 verdict=offline
    "identity_consistency": 0.35,
    "token_billing":        0.20,  # deviation_pct → 100 - min(deviation_pct*3, 100)
    "tool_use":             0.25,
}
```

**v0.2 完整权重（8 维度）**:

```python
weights_v02 = {
    "online":               0.05,  # online=false 仍走短路
    "protocol_consistency": 0.15,
    "identity_consistency": 0.20,
    "knowledge_signature":  0.10,
    "token_billing":        0.15,
    "tool_use":             0.15,
    "web_search":           0.05,  # 权重低：很多情况下 baseline 是"应该说不能联网"
    "sub_agent":            0.15,
}
```

**短路规则**：
- `online.score == 0` → 跳过其余维度，verdict=`offline`，final_score=0
- baselines.yaml 中标注 `supports.tool_use: false` 的模型，相关能力维度跳过且**从权重分母中移除**（重新归一化）

**verdict 阈值**:
- 90-100 → `authentic`
- 75-89 → `likely_authentic`
- 50-74 → `suspicious`
- 0-49 → `likely_fake`
- online=false → `offline`

`capability_flags` 单独输出（不计入主分数，只做信息展示），yyc 模型市场页可以用它来打"残缺标签"：
```json
{
  "tool_use": "ok",
  "web_search": "degraded",
  "sub_agent": "missing"
}
```

## 5. HTTP API 规格

### `POST /detect`

**Request**:
```json
{
  "base_url": "https://upstream.example.com",
  "api_key": "sk-...",
  "model": "claude-opus-4-7",
  "expected_provider": "anthropic",
  "rounds": 11,
  "budget_usd": 0.5,
  "task_id": "uuid",
  "mode": "sync",
  "dry_run": false,
  "verbose": false
}
```

字段：
- `base_url` (required)
- `api_key` (required)
- `model` (required, 必须在 baselines.yaml 中)
- `expected_provider` (optional, 加速 adapter 选择，否则用 model→provider 映射)
- `rounds` (optional, default 11, 范围 5-50)
- `budget_usd` (optional, default 0.5)
- `task_id` (optional, 幂等 key, 同 task_id 在 1h 内返回缓存)
- `mode` (optional, `sync` | `async`, default 自动: `rounds<=20` 用 sync)
- `dry_run` (optional, default false, true 时使用 mock 数据)
- `verbose` (optional, default false, true 时 rounds_log 返回完整 response)

**Response (200)**:
```json
{
  "task_id": "uuid",
  "status": "completed",
  "score": 87,
  "verdict": "likely_authentic",
  "summary_zh": "模型行为高度自洽，token 计费正常，符合 Claude Opus 4.7 特征。tool_use 与 sub_agent 完整可用，web_search 行为略偏离基线。",
  "summary_en": "Model behavior is highly consistent and token billing matches expectations for Claude Opus 4.7. Tool use and sub-agent capabilities are fully available; web search behavior slightly deviates from baseline.",
  "dimensions": {
    "online":               { "score": 100, "status": "ok",  "evidence": {...} },
    "protocol_consistency": { "score": 92,  "status": "ok",  "evidence": {...} },
    "identity_consistency": { "score": 95,  "status": "ok",  "evidence": {...} },
    "knowledge_signature":  { "score": 88,  "status": "ok",  "evidence": {...} },
    "token_billing":        { "score": 96,  "deviation_pct": 3.2, "evidence": {...} },
    "tool_use":             { "score": 100, "status": "ok",  "evidence": {...} },
    "web_search":           { "score": 60,  "status": "degraded", "evidence": {...} },
    "sub_agent":            { "score": 100, "status": "ok",  "evidence": {...} }
  },
  "capability_flags": {
    "tool_use":   "ok",
    "web_search": "degraded",
    "sub_agent":  "ok"
  },
  "performance": {
    "first_token_latency_ms": { "p50": 820,  "p95": 1450 },
    "total_latency_ms":       { "p50": 1240, "p95": 3100 },
    "tokens_per_second":      37.2
  },
  "rounds_log": [
    {
      "round": 1,
      "dimension": "identity_consistency",
      "prompt": "What model are you? [REQ-9f8e]",
      "response_excerpt": "I am Claude, made by Anthropic...",
      "verdict": "match",
      "duration_ms": 1180
    }
  ],
  "actual_cost_usd": 0.28,
  "duration_ms": 45000,
  "over_budget": false,
  "warnings": []
}
```

**错误**:
- `400` validation error
- `408` timeout (sync mode 超 60s)
- `402` over_budget（仍返回 partial result）
- `502` upstream offline
- `500` internal

### `POST /detect/async` + `GET /detect/{task_id}`

`POST /detect/async` 立即返回 `{task_id, status: "running"}`，后台执行。

`GET /detect/{task_id}` 返回:
- `status: "running"` → `{task_id, status, progress: {completed_dimensions: 3, total: 8}}`
- `status: "completed"` → 完整 response
- `status: "failed"` → `{task_id, status, error}`

### `GET /benchmark/{model_name}`

```json
{
  "model": "claude-opus-4-7",
  "provider": "anthropic",
  "expected_signatures": ["honest, harmless, helpful", "Constitutional AI"],
  "expected_identity_keywords": ["claude", "anthropic"],
  "expected_latency_p50_ms": 1500,
  "expected_tokens_per_second": 35,
  "tokenizer": "anthropic-claude-3",
  "supports": {
    "tool_use": true,
    "web_search": true,
    "sub_agent": true,
    "streaming": true
  },
  "strengths_zh": ["代码生成", "长上下文", "复杂推理"],
  "weaknesses_zh": ["数学推理偏弱"],
  "strengths_en": [...],
  "weaknesses_en": [...],
  "vendor_baseline_score": 95
}
```

### `POST /compare`

```json
{
  "targets": [
    {"base_url": "...", "api_key": "...", "model": "...", "label": "PackyCode"},
    {"base_url": "...", "api_key": "...", "model": "...", "label": "RightCode"}
  ],
  "rounds": 11,
  "budget_usd": 1.0
}
```

要求 `2 <= len(targets) <= 4`。返回每个 target 的完整 detect 报告 + diff 矩阵（每个维度并列对比）。

### `GET /healthz`

`{"status": "ok", "version": "0.1.0", "uptime_s": 12345}`

## 6. 项目结构

```
D:\projects\检测模型\
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI 入口
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── detect.py          # POST /detect, /detect/async, GET /detect/{id}
│   │   ├── benchmark.py       # GET /benchmark/{model}
│   │   ├── compare.py         # POST /compare
│   │   └── health.py          # GET /healthz
│   ├── cli.py                 # python -m app.cli ...
│   ├── cache.py               # SQLite cache (1h TTL)
│   ├── async_runner.py        # in-process task queue
│   └── detector/
│       ├── __init__.py        # public: run_detection, load_baseline
│       ├── core.py            # 编排 + 聚合
│       ├── scoring.py         # weighted_average + verdict 阈值
│       ├── budget.py          # BudgetTracker
│       ├── log_redact.py      # mask sk-***xxx
│       ├── probes.py          # probes.yaml loader
│       ├── adapters/
│       │   ├── __init__.py    # get_adapter(provider)
│       │   ├── base.py        # Adapter ABC
│       │   ├── anthropic.py
│       │   ├── openai.py
│       │   └── google.py
│       └── dimensions/
│           ├── __init__.py    # registry: ALL_DIMENSIONS
│           ├── base.py        # Dimension ABC, DimensionResult
│           ├── online.py
│           ├── protocol_consistency.py
│           ├── identity_consistency.py
│           ├── knowledge_signature.py
│           ├── token_billing.py
│           ├── tool_use.py
│           ├── web_search.py
│           └── sub_agent.py
├── data/
│   ├── baselines.yaml         # 5 模型基线
│   └── probes.yaml            # identity / signature / capability prompt 池
├── tests/
│   ├── conftest.py            # mock httpx fixtures
│   ├── test_adapters/
│   ├── test_dimensions/       # 每维度独立测试
│   ├── test_routes.py
│   ├── test_cli.py
│   ├── test_budget.py
│   └── test_log_redact.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── README.md
└── .gitignore
```

## 7. 关键非功能性需求

| 需求 | 实现 |
|---|---|
| API key 不入日志 | `log_redact.py` 全局过滤器，所有 logger.info/error 中字符串经过 `redact()`，匹配 `sk-[a-zA-Z0-9_-]{6,}` 替换为 `sk-***xxx`（保留前 3 后 2 字符）|
| 60s sync 阈值 | sync 路径加 `asyncio.wait_for(task, timeout=60)`，超时返回 408 |
| 预算 USD 限额 | `BudgetTracker.charge(prompt_tokens, completion_tokens, model)` 累加，触限抛 `BudgetExceeded` |
| 1h 缓存 TTL | SQLite `cache(key TEXT PRIMARY KEY, value BLOB, expires_at INTEGER)`，key = `sha256(base_url + key_fingerprint + model + rounds)` |
| dry_run | adapter 注入 `MockTransport`，从 `tests/fixtures/mock_responses/` 读取固化数据 |
| 防对抗 nonce | `probes.draw(category)` 每次返回 `(prompt + " [REQ-{uuid4_hex8}]", expected)` |
| 不暴露第三方 telemetry | 不引入 sentry/posthog/datadog；只本地 logging（stderr） |
| Docker 单文件部署 | `python:3.11-slim` 基底，`docker-compose.yml` 暴露 `127.0.0.1:8800` |

## 8. MVP 切分

### v0.1（本次交付，先发给 yyc 接入）
- 4 维度：`online` + `identity_consistency` + `token_billing` + `tool_use`
- 3 adapter：anthropic / openai / google
- `POST /detect`（仅同步模式，rounds 默认 11）
- `GET /healthz`
- CLI: `python -m app.cli --base ... --key ... --model ...`
- baselines.yaml 内置 5 个模型
- 完整 dry_run 支持
- 完整测试覆盖（每维度 ≥3 测试用例）
- Dockerfile + docker-compose.yml + README

### v0.2
- 补 `protocol_consistency` + `knowledge_signature` + `web_search` + `sub_agent`
- `POST /detect/async` + `GET /detect/{task_id}` + SQLite 缓存
- `GET /benchmark/{model_name}`
- 性能指标 latency p50/p95、TPS

### v0.3
- `POST /compare`
- baselines.yaml 扩到 50+ 模型（Grok / DeepSeek / Qwen / Moonshot / 智谱 等）
- 完整双语 summary 生成（基于 dimensions 自动组装，不调 LLM）

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| 上游中转站针对固定 prompt 缓存伪造 | 每次随机抽 + nonce 注入，且每发布版本会更新 probes.yaml |
| baseline 偏差导致误判 | baseline 数据公开在仓库，用户可 PR 修正；判定阈值留 buffer，单维度低分需 ≥2 维度共同低分才下 likely_fake 结论 |
| 检测耗 token 过多 | 默认 budget=0.5 USD；CLI 默认 dry_run=true 帮调试 |
| Anthropic / Google 协议变更 | adapter 隔离 + version pin；测试 fixture 季度更新 |
| sub_agent 维度因模型限制误判残缺 | baselines.yaml 标注每个模型 `supports.sub_agent`，不支持的模型该维度跳过、不计入分数 |

## 10. 测试策略

- **单测**: 每个 dimension module 独立测试（mock httpx），覆盖 ok / degraded / missing / error 四种路径
- **集成测试**: 通过 `dry_run=true` 走完整 `/detect` 流程，断言 score / verdict / capability_flags 与固化期望一致
- **端到端**: tests/e2e/ 用 `responses` 库模拟三家厂商真实响应序列
- **CI**: GitHub Actions 矩阵 (Python 3.11, 3.12) × (Linux, Windows)，pytest + ruff + mypy
- **覆盖率门槛**: 核心 `app/detector/` ≥ 85%

## 11. 部署

```yaml
# docker-compose.yml
services:
  detector:
    build: .
    ports: ["127.0.0.1:8800:8800"]
    volumes:
      - ./data:/app/data:ro
      - detector-cache:/app/cache
    environment:
      DETECTOR_LOG_LEVEL: INFO
      DETECTOR_DEFAULT_BUDGET_USD: "0.5"
      DETECTOR_CACHE_TTL_SECONDS: "3600"
    restart: unless-stopped
volumes:
  detector-cache:
```

yyc.lat nginx 配置示例（不在本仓库）：

```nginx
location /api/relay-detector/ {
  proxy_pass http://127.0.0.1:8800/;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_read_timeout 90s;
}
```

## 12. 验收标准（v0.1）

- [ ] `POST /detect` 用真实 Anthropic 官方 key 检测 `claude-opus-4-7` 返回 score ≥ 90 且 verdict=`authentic`
- [ ] `POST /detect` 用 `dry_run=true` 注入"被掺水"mock 数据时返回 verdict=`likely_fake`
- [ ] `tool_use` 维度对返回纯文本（不返回 tool_calls）的 mock 上游正确判定 `degraded`
- [ ] 日志中 API key 全部脱敏为 `sk-***xx`
- [ ] 预算超限时返回 `over_budget=true` 且 `actual_cost_usd <= budget_usd * 1.05`
- [ ] CLI `python -m app.cli --dry-run` 能完整跑出报告
- [ ] Docker 容器启动后 `curl 127.0.0.1:8800/healthz` 返回 200
- [ ] 所有 pytest 通过，覆盖率 ≥ 85%
- [ ] README 包含：快速启动、HTTP API 示例、CLI 示例、yyc 接入示例

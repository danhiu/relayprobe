# RelayProbe

> Authenticity, integrity, and capability audit for AI API gateways. Verify the model behind any Anthropic / OpenAI / Google compatible endpoint.

[![tests](https://img.shields.io/badge/tests-68%20passing-brightgreen)]() [![coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)]() [![python](https://img.shields.io/badge/python-3.11%2B-blue)]() [![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

[中文](#中文文档) · [English](#english) · [Architecture](#architecture) · [Roadmap](#roadmap)

---

### 🔍 Try it without installing anything

[**yyc.lat/tools/relayprobe → live demo**](https://yyc.lat/tools/relayprobe) — paste any OpenAI/Anthropic-compatible `base_url` + `api_key` + model, get a 5-dimension trust report in 30 seconds. No login, no signup, IP rate-limited.

[**yyc.lat → AI API gateway powered by RelayProbe**](https://yyc.lat/pricing) — every upstream channel is scanned by this tool, scores published on the pricing page so you can compare providers' integrity before you buy.

---

## English

### What it does

You buy `claude-opus-4-7` from a relay or aggregated gateway. RelayProbe answers, with evidence:

- **Is the model actually Claude?** — Or has it been swapped to a cheaper model, or wrapped by Kiro / Cursor / Continue / Cline?
- **Is the gateway injecting a hidden system prompt?** — Detects 100s–1000s of cached tokens charged silently to your bill.
- **Are advanced capabilities intact?** — Function calling, multi-turn tool chains. Many wrappers silently swallow `tool_calls`.
- **Is the token billing inflated?** — Compares observed token counts against tokenizer-family expectations.

For each `(base_url, api_key, model)` triplet, RelayProbe returns a 0–100 trust score, a verdict, per-dimension evidence (raw prompts and responses), and a bilingual summary.

### Why open source

Audit tools live or die by public trust in their methodology. Closed-source detectors are easy to dismiss as biased. RelayProbe puts every probe prompt, scoring rule, and dimension weight in plain Python so you can fork it, audit it, or PR new wrapper signatures as they emerge.

### Quick start

```bash
git clone https://github.com/danhiu/relayprobe.git
cd relayprobe
docker compose up -d
curl http://127.0.0.1:8800/healthz
```

Audit a gateway:

```bash
curl -X POST http://127.0.0.1:8800/detect \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://your-gateway.example.com",
    "api_key": "sk-...",
    "model": "claude-sonnet-4-6",
    "rounds": 6,
    "budget_usd": 0.15
  }'
```

Or via CLI:

```bash
python -m app.cli --base https://your-gateway.example.com \
  --key sk-... --model claude-sonnet-4-6 --rounds 6 --budget 0.15
```

### Detection dimensions (v0.1)

| Dimension | Detects | Score |
|---|---|---|
| `online` | Reachability of `/v1/models` and chat endpoint | 0 / 80 / 100 |
| `identity_consistency` | Self-reported identity matches the requested model; flags wrappers (Kiro, Cursor, Continue, Cline, Aider, Zed) | 0 / 60 / 70 / 80 / 95 |
| `wrapper_detection` | Hidden system prompt injection, measured by `cache_read_input_tokens` and effective input excess | 0 / 30 / 70 / 100 |
| `token_billing` | Effective input deviation from tokenizer-family expectations (cache excluded) | 0 / 30 / 60 / 85 / 100 |
| `tool_use` | Function calling actually returns `tool_calls` with valid arguments | 0 / 40 / 60 / 100 |

The final score is a weighted average over enabled dimensions; `online` failure short-circuits the verdict to `offline`.

### Supported models (v0.1)

| Provider | Models |
|---|---|
| Anthropic | `claude-opus-4-7`, `claude-sonnet-4-6` |
| OpenAI | `gpt-5-5`, `gpt-5-4` |
| Google | `gemini-3-1-pro` |

Adding a model is a one-file PR — see [CONTRIBUTING.md](CONTRIBUTING.md).

### HTTP API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/detect` | Run audit. `mode="sync"` (default) blocks ≤60s; `mode="async"` returns `task_id` immediately |
| `GET`  | `/detect/{task_id}` | Poll an async detection — status: `running` / `completed` / `failed` |
| `GET`  | `/healthz` | Liveness probe |

#### Async example

```bash
# Submit
TASK_ID=$(curl -s -X POST http://127.0.0.1:8800/detect \
  -H "Content-Type: application/json" \
  -d '{"base_url":"https://x","api_key":"sk-...","model":"claude-opus-4-7","mode":"async"}' \
  | jq -r .task_id)

# Poll every 5s until done
while :; do
  RES=$(curl -s http://127.0.0.1:8800/detect/$TASK_ID)
  echo "$RES" | jq -r '"status=\(.status) score=\(.score)"'
  [ "$(echo "$RES" | jq -r .status)" != "running" ] && { echo "$RES" | jq .; break; }
  sleep 5
done
```

Use `mode="async"` for slow audits (Claude Opus, GPT-5 multi-round
probes) where the 60s sync ceiling is too tight. Job state lives in the
detector process for 1h after completion, then is reaped.

Full request and response schema: [`app/detector/types.py`](app/detector/types.py).

### Security

- API keys are masked in all logs (`sk-XXX***XX`)
- Per-detection USD budget cap halts probes mid-flight if exceeded
- Service binds to `127.0.0.1:8800` only — front it with nginx for any external access
- Container runs `read-only` with `no-new-privileges`
- Probes are randomized with per-request nonces to defeat upstream caching

### Development

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # Linux / macOS
pip install -e ".[dev]"
pytest -v
ruff check .
```

68 tests, 94% coverage on the core library.

---

## 中文文档

### 这是什么

你从某个中转站或聚合网关买了 `claude-opus-4-7`。RelayProbe 用证据回答：

- **模型真的是 Claude 吗？** — 还是被换成了便宜模型，或被 Kiro / Cursor / Continue / Cline 套了壳？
- **网关有没有注入隐藏的 system prompt？** — 检测每次请求被静默计费的几百到几千个缓存 tokens。
- **高级能力完好吗？** — Function calling、多轮工具链。许多包壳会悄悄吞掉 `tool_calls`。
- **token 计费是否注水？** — 把实际 token 数与 tokenizer 家族的预期值对比。

对每个 `(base_url, api_key, model)` 三元组，RelayProbe 返回 0–100 可信度评分、verdict 标签、每个维度的原始证据（prompt 与 response 节选），以及双语 summary。

### 在线试用（无需安装）

[**yyc.lat/tools/relayprobe → 在线工具**](https://yyc.lat/tools/relayprobe) — 把任何 OpenAI/Anthropic 兼容中转的 `base_url` + `api_key` + 模型粘进去，30 秒内拿到 5 维度可信度报告。免登录、IP 限速。

[**yyc.lat → 一个用 RelayProbe 自审的 AI 中转**](https://yyc.lat/pricing) — 我们在自己的中转上跑这个工具，把每条上游渠道的扫描分数公开在价格页，方便用户在掏钱前先对比诚信度。

### 为什么开源

审计工具的命脉在于方法论的公开可信。闭源检测器容易被质疑有偏见。RelayProbe 把每个探测 prompt、评分规则、维度权重都用普通 Python 写明白，你可以 fork、审计，或在新 wrapper 签名出现时提 PR。

### 快速开始

```bash
git clone https://github.com/danhiu/relayprobe.git
cd relayprobe
docker compose up -d
curl http://127.0.0.1:8800/healthz
```

审计一个网关：

```bash
curl -X POST http://127.0.0.1:8800/detect \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://your-gateway.example.com",
    "api_key": "sk-...",
    "model": "claude-sonnet-4-6",
    "rounds": 6,
    "budget_usd": 0.15
  }'
```

### 检测维度（v0.1）

| 维度 | 检测什么 | 分数 |
|---|---|---|
| `online` | `/v1/models` 与 chat endpoint 是否可达 | 0 / 80 / 100 |
| `identity_consistency` | 自报身份是否与请求的模型一致；标记 Kiro/Cursor/Continue/Cline/Aider/Zed 等 wrapper | 0 / 60 / 70 / 80 / 95 |
| `wrapper_detection` | 隐藏 system prompt 注入（用 `cache_read_input_tokens` 与超额 input 测算） | 0 / 30 / 70 / 100 |
| `token_billing` | 有效 input 与 tokenizer 家族预期值的偏差（已扣除 cache） | 0 / 30 / 60 / 85 / 100 |
| `tool_use` | function calling 是否真返回了 `tool_calls` 与合法参数 | 0 / 40 / 60 / 100 |

最终分是已启用维度的加权平均；`online` 失败会直接短路为 `offline`。

### 安全

- 所有日志中 API key 都被掩码 (`sk-XXX***XX`)
- 单次检测有 USD 预算上限，超出立即中止
- 服务只 bind `127.0.0.1:8800`，外部访问必须经 nginx
- 容器以 `read-only` + `no-new-privileges` 运行
- 探测 prompt 每次随机抽取并加 nonce，规避上游缓存对抗

---

## Architecture

```
┌──────────────────┐
│ Caller (any HTTP)│
└────────┬─────────┘
         │ POST /detect
         ▼
┌─────────────────────────────────────────┐
│ FastAPI app (127.0.0.1:8800)            │
│ ├── /detect, /healthz                   │
│ └── 60s sync timeout                    │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ app/detector/  (pure library, no HTTP)  │
│ ├── core.py        orchestration        │
│ ├── adapters/      anthropic/openai/    │
│ │                  google native probes │
│ └── dimensions/    online, identity,    │
│                    wrapper_detection,   │
│                    token_billing,       │
│                    tool_use             │
└─────────────────────────────────────────┘
```

The core library is pure Python with no FastAPI dependency. CLI and HTTP layer share it.

## Roadmap

- **v0.2** — ~~async task mode~~ ✅ (rc.1, see [CHANGELOG](CHANGELOG.md));
  protocol consistency, knowledge signature, web search, sub-agent
  dimensions; SQLite caching
- **v0.3** — `/compare` endpoint for side-by-side audits; baseline catalog expanded to 50+ models (Grok, DeepSeek, Qwen, Moonshot, ZhipuAI)
- **v0.4** — Streaming protocol fingerprint detection (SSE format compliance, first-token latency)

## License

[MIT](LICENSE) © 2026 RelayProbe contributors

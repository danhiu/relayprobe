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

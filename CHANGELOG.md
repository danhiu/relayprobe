# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0-rc.1] — 2026-05-24

First v0.2 milestone — the async task mode promised in the v0.1 roadmap.
Long-running detections (Claude Opus, GPT-5) no longer hit the 60s sync
timeout.

### Added

- `mode="async"` on `POST /detect` — submits the audit and returns
  immediately with `task_id` and `status="running"`
- `GET /detect/{task_id}` — poll endpoint; status transitions
  `running` → `completed` / `failed`
- In-process job store (`app/jobs.py`) with 1h TTL and a 60s reaper
- Health endpoint reports the package version (was hard-coded)

### Unchanged

- `POST /detect` with `mode="sync"` (the default) keeps the v0.1
  behavior exactly: blocks up to 60s, returns 408 on timeout. Existing
  CLI / curl callers don't need to change anything.

[0.2.0-rc.1]: https://github.com/danhiu/relayprobe/releases/tag/v0.2.0-rc.1

## [0.1.0] — 2026-05-23

Initial public release.

### Added

- HTTP service (`POST /detect`, `GET /healthz`) and CLI (`python -m app.cli`)
- Three native protocol adapters: Anthropic `/v1/messages`, OpenAI `/v1/chat/completions`, Google `:generateContent`
- Five detection dimensions:
  - `online` — endpoint reachability
  - `identity_consistency` — multi-round self-identity probe with vendor and wrapper keyword matching
  - `wrapper_detection` — hidden system prompt injection via `cache_read_input_tokens` analysis
  - `token_billing` — cache-aware effective input deviation from tokenizer expectations
  - `tool_use` — function calling capability with `tool_calls` validation
- Five model baselines: `claude-opus-4-7`, `claude-sonnet-4-6`, `gpt-5-5`, `gpt-5-4`, `gemini-3-1-pro`
- Wrapper signatures for Kiro, Cursor, Continue, Cline, Aider, Zed
- USD budget tracker with per-detection cap
- API key redaction filter applied globally to logs
- Probe pool with random nonce injection to defeat upstream caching
- Dry-run mode using fixture data for CI / debugging
- Docker Compose deployment with `read-only` filesystem and `no-new-privileges`
- 68 unit and integration tests, 94% line coverage on `app/detector/`

[0.1.0]: https://github.com/danhiu/relayprobe/releases/tag/v0.1.0

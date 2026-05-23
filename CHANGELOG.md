# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

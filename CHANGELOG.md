# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0-rc.4] — 2026-05-25

Fixes a long-standing false-positive in `identity_consistency`: probes
that name vendors as part of the question itself (e.g. "Are you Claude,
GPT, or Gemini?") forced the model to repeat those names in any honest
denial, which then tripped the `forbidden_identity_keywords` rule and
collapsed the dimension to 0 — turning real GPT and real Claude
relays into "missing" (suspicious / likely_fake) verdicts at random.

### Fixed

- `identity_consistency`: forbidden vendor keywords that already appear
  in the prompt no longer count toward the round's `forbidden_hits`.
  Only words the model introduces unprompted are evidence of
  misidentification. Per-round evidence now records both
  `matched_expected` and `matched_forbidden` so admins can see why a
  verdict landed.
- `wrapper_detection`: the catch-all exception handler used to record
  `evidence={"error": str(e)}`. Some httpx errors arrive with empty
  `str(e)` (e.g. `ConnectError` on half-closed sockets), leaving the
  evidence as a useless `{"error": ""}`. Now also captures
  `exception_type` so transient blips are debuggable.

### Tests

- New `test_forbidden_keyword_in_prompt_does_not_count` covering the
  three-way trap probe path.

## [0.2.0-rc.3] — 2026-05-24

Refines `token_billing` so a fixed-size system-prompt overhead — common
across reverse-proxy relays — no longer collapses the dimension to 0
and gets double-counted with `wrapper_detection`.

### Changed

- `token_billing` now branches on **stability across rounds** before
  applying the ladder:
  - **Stable** counts (every round identical, ≤ 2 token spread): the
    overhead is a constant injection, already covered by
    `wrapper_detection`. Score by absolute inflation:
    `<50` → 90, `50–200` → 75, `200–800` → 60, `800+` → 50. Floors at
    50 — never zeroes out a relay just because it prepends a wrapper.
  - **Unstable** counts (genuine per-prompt re-tokenisation against the
    wrong tokenizer): the original aggressive ladder applies, with 0
    reserved for `>300%` deviation. This is the actual "different
    model entirely" signal.
- New evidence fields: `inflation_tokens` (absolute overhead vs the
  baseline tokenizer expectation) and `stable_across_rounds` (boolean).
- Tests updated; `test_high_deviation_flagged` replaced with two
  tests that cover both branches explicitly.

[0.2.0-rc.3]: https://github.com/danhiu/relayprobe/releases/tag/v0.2.0-rc.3

## [0.2.0-rc.2] — 2026-05-24

Resolves the long-standing "relay publishes the model under a different
identifier than the canonical baseline" mismatch. The detector now
treats `data/baselines.yaml` as the single source of truth for both
*which baselines exist* and *which identifiers map to them*; client
code (notably new-api) no longer needs to maintain a parallel mapping.

### Added

- `aliases:` per-baseline list in `baselines.yaml` — populated for
  `gpt-5-5` (`gpt-5.5`), `gpt-5-4` (`gpt-5.4`), `gemini-3-1-pro`
  (`gemini-3.1-pro`).
- Top-level `runtime_suffixes` and `dated_suffix_pattern` in
  `baselines.yaml` — drive the resolver's suffix-strip behavior so
  `claude-opus-4-7-thinking`, `gemini-3.1-pro-low`, and
  `claude-opus-4-7-20251101` all resolve to their underlying baseline.
- `BaselinesIndex.resolve(model)` — the canonical resolver. Implements:
  exact match → alias → punctuation normalization → runtime-suffix
  strip (loops, supports stacking) → dated-suffix strip (only when the
  prefix itself resolves).
- `GET /baselines` — full catalog plus the suffix list and dated
  pattern, so external clients can mirror resolution without
  re-implementing it.
- `GET /baselines/resolve?model=<id>` — single-shot resolver. Returns
  `{supported, baseline, target_model, aliases}`.
- `DimensionContext.target_model` — the identifier sent on the wire.
  Decoupled from `baseline.name` so a request for `gpt-5.5` is routed
  through the `gpt-5-5` baseline for *scoring* but reaches upstream as
  `gpt-5.5`. All five dimensions updated to use it.

### Fixed

- `POST /detect` previously sent the canonical baseline name to the
  upstream relay. Sites that publish the model under an alias (e.g.
  yyc.lat exposes `gpt-5.5`, not `gpt-5-5`) returned 503
  "model_not_found", which the detector reported as `verdict=offline`
  even though the relay was serving the model fine. The detector now
  sends the caller's original identifier upstream while still scoring
  against the resolved baseline.
- `BaselinesIndex.from_dict` now raises `ValueError` on alias
  collisions (two baselines claiming the same alias), preventing
  silent shadowing at resolve time.

### Migration notes

- The Python public symbol `Baseline` is unchanged. Code that did
  `load_baselines()[name]` keeps working because `BaselinesIndex`
  still supports `__getitem__` / `__contains__` / `keys` / `values` /
  `items`. Resolution-aware code should call `idx.resolve(name)`.
- `DimensionContext` gained a required `target_model` field. Any
  external dimension implementations need to update their context
  construction.

[0.2.0-rc.2]: https://github.com/danhiu/relayprobe/releases/tag/v0.2.0-rc.2

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

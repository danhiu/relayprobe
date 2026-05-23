# Contributing to RelayProbe

Thanks for considering a contribution. RelayProbe gets stronger every time someone adds a new wrapper signature, model baseline, or detection dimension.

## What's most useful

In rough priority order:

1. **New wrapper signatures.** When you find a relay self-identifying as `Foo` or injecting a fixed-size system prompt, add `foo` to the `forbidden_identity_keywords` list in [`data/baselines.yaml`](data/baselines.yaml) for every Anthropic / OpenAI / Google model and submit a PR. Include the test prompt and response in the PR description so reviewers can validate.

2. **Model baselines.** Adding `gpt-5-3`, `claude-haiku-4-5`, `gemini-3-flash`, Grok, DeepSeek, Qwen, and friends. Each takes ~10 lines in `baselines.yaml`. The detector picks the right tokenizer family and provider adapter from the baseline.

3. **Detection dimensions.** Each dimension is a single self-contained Python module under `app/detector/dimensions/` — see [`tool_use.py`](app/detector/dimensions/tool_use.py) for a minimal example. Subclass `Dimension`, set `name` and `weight`, implement `async def evaluate(ctx)`. Register it in `app/detector/dimensions/__init__.py`. Include unit tests covering `ok`, `degraded`, and `missing` paths.

4. **Probe pool variants.** Add prompts to [`data/probes.yaml`](data/probes.yaml). Larger pools defeat upstream caching better.

## Setup

```bash
git clone https://github.com/danhiu/relayprobe.git
cd relayprobe
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
ruff check .
```

The full test suite runs in under 2 seconds. A passing `pytest -v` and a clean `ruff check .` are required for review.

## Testing your change

Always include unit tests with mocked HTTP (use `respx` for adapter tests, `unittest.mock.AsyncMock` for dimension tests). Don't make real upstream calls in tests.

For end-to-end verification against a real gateway:

```bash
docker compose up -d
python -m app.cli --base https://your-gateway --key sk-... --model claude-sonnet-4-6 --rounds 6 --budget 0.15
```

## Commit style

- Conventional commits: `feat(adapters):`, `fix(dimensions):`, `docs:`, `test:`, `chore:`
- One logical change per commit
- Include the *why* in the commit body when it's non-obvious

## Reporting wrappers responsibly

When reporting a wrapper or relay misbehavior:

- **Do** include the gateway base URL, the model you requested, the system prompt size you observed, and timestamps
- **Do not** include API keys (yours or anyone else's). RelayProbe redacts them in logs but PR descriptions are public
- Open an issue tagged `wrapper-signature` or directly submit a PR adding the keyword to baselines

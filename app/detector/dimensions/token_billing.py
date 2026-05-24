"""Token-billing deviation. Sends the same fixed prompt 3 times, computes deviation
from a tokenizer-family-specific expected count.

Anthropic's `usage` reports `input_tokens` (new tokens this turn), `cache_read_input_tokens`
(replayed from cache), and `cache_creation_input_tokens` (newly cached). For deviation
detection we want the *user-visible* token count — i.e. tokens the relay can attribute
to your prompt — which is `input_tokens + cache_creation`. cache_read tokens come from
a system prompt the relay injected and shouldn't be attributed to your prompt directly,
but they ARE billable, so we surface both: `effective_input` and `total_billable`.
A relay that injects a fat system prompt shows up as cache_read >> input_tokens —
that's the wrapper signal."""
from __future__ import annotations

import statistics

from app.detector.budget import BudgetExceeded
from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.types import ChatMessage, DimensionResult, RoundLog

# Fixed prompt designed so tokenizer count is stable & low-cost.
FIXED_PROMPT = "Repeat after me: hello world"

# Approximate prompt_token expectation per tokenizer family.
EXPECTED_PROMPT_TOKENS = {
    "anthropic": 9,
    "openai":    8,
    "google":    9,
}


def _extract_input_tokens(raw: dict) -> tuple[int, int, int]:
    """Return (effective_input, cache_read, cache_creation) for any vendor.

    Anthropic raw: {"usage": {"input_tokens": N, "cache_read_input_tokens": M,
                              "cache_creation_input_tokens": K, "output_tokens": ...}}
    OpenAI raw:    {"usage": {"prompt_tokens": N, ...}}  (no cache breakdown)
    Google raw:    {"usageMetadata": {"promptTokenCount": N, ...}}
    """
    usage = raw.get("usage") or raw.get("usageMetadata") or {}
    cache_read = (
        usage.get("cache_read_input_tokens", 0)
        or usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        or 0
    )
    cache_creation = usage.get("cache_creation_input_tokens", 0) or 0
    if "input_tokens" in usage:
        # Anthropic: input_tokens already excludes cache_read
        effective = usage["input_tokens"]
    elif "prompt_tokens" in usage:
        # OpenAI: prompt_tokens INCLUDES cached, so subtract
        effective = usage["prompt_tokens"] - cache_read
    elif "promptTokenCount" in usage:
        effective = usage["promptTokenCount"] - cache_read
    else:
        effective = 0
    return effective, cache_read, cache_creation


class TokenBilling(Dimension):
    name = "token_billing"
    weight = 0.20
    rounds_used = 3

    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        baseline = ctx.baseline
        expected = EXPECTED_PROMPT_TOKENS.get(baseline.tokenizer, 9)

        observed_effective: list[int] = []
        observed_cache_read: list[int] = []
        observed_cache_creation: list[int] = []
        per_round: list[dict] = []
        last_error: str | None = None

        for i in range(self.rounds_used):
            try:
                result = await ctx.adapter.chat(
                    model=ctx.target_model,
                    messages=[ChatMessage(role="user", content=FIXED_PROMPT)],
                    max_tokens=20,
                )
                ctx.budget.charge(
                    model=baseline.name,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                )
                eff, cr, cc = _extract_input_tokens(result.raw)
                # Fallback to result.prompt_tokens if raw didn't have a usage block.
                if eff == 0 and not (cr or cc):
                    eff = result.prompt_tokens
                observed_effective.append(eff)
                observed_cache_read.append(cr)
                observed_cache_creation.append(cc)
                per_round.append(
                    {
                        "round": i,
                        "effective_input_tokens": eff,
                        "cache_read_input_tokens": cr,
                        "cache_creation_input_tokens": cc,
                        "completion_tokens": result.completion_tokens,
                    }
                )
                ctx.rounds_log.append(
                    RoundLog(
                        round=len(ctx.rounds_log) + 1,
                        dimension=self.name,
                        prompt=FIXED_PROMPT,
                        response_excerpt=result.text[:200],
                        verdict=f"effective_input={eff} cache_read={cr}",
                        duration_ms=result.total_latency_ms,
                    )
                )
            except BudgetExceeded:
                raise
            except Exception as e:
                last_error = str(e)
                per_round.append({"round": i, "error": last_error})

        if not observed_effective or all(v == 0 for v in observed_effective):
            return DimensionResult(
                name=self.name, score=0, status="error",
                evidence={"per_round": per_round, "expected": expected},
                error=last_error or "no observed token counts",
            )

        median_actual = statistics.median(observed_effective)
        deviation_pct = abs(median_actual - expected) / expected * 100
        median_cache_read = statistics.median(observed_cache_read) if observed_cache_read else 0
        median_cache_creation = (
            statistics.median(observed_cache_creation) if observed_cache_creation else 0
        )

        # Stability across rounds: a relay that injects a *fixed-size*
        # system prompt produces a flat curve (every round identical),
        # while a relay that genuinely re-tokenises your prompt against a
        # different model produces a noisy curve. The difference matters
        # for scoring — a fixed wrapper is already penalised by the
        # wrapper_detection dimension, so we don't double-count it here.
        spread = max(observed_effective) - min(observed_effective) if observed_effective else 0
        is_stable = spread <= 2  # tokenizer round-trip tolerance
        inflation_tokens = max(0, int(median_actual) - expected)

        # Two scoring tracks:
        #
        # 1. Stable count (every round identical) — overhead is a constant
        #    system prompt the relay prepends. The model itself is plausibly
        #    correct; we don't punish it like a swap. Floor at 60 so the
        #    "inflated by 138 tokens, every time" case isn't conflated with
        #    "different model entirely".
        #
        # 2. Unstable count — actual per-prompt tokenisation is happening
        #    but mismatched against the baseline tokenizer family. That's
        #    the strong "served by a different model" signal. We keep the
        #    aggressive ladder there.
        #
        # The two tracks share a no-deviation top: <15% drift on either
        # track still scores 100.

        if deviation_pct < 15:
            score, status = 100, "ok"
        elif is_stable:
            # Inflation is a constant offset. Score by absolute size, not %.
            # < 50 tokens   -> 90  ("be helpful" preamble; no real impact)
            # 50-200        -> 75  (small wrapper; slight cost overhead)
            # 200-800       -> 60  (medium wrapper; visible cost overhead)
            # 800+          -> 50  (heavy wrapper; user is buying overhead,
            #                       but the model itself can still be real;
            #                       wrapper_detection covers the rest)
            if inflation_tokens < 50:
                score, status = 90, "ok"
            elif inflation_tokens < 200:
                score, status = 75, "ok"
            elif inflation_tokens < 800:
                score, status = 60, "degraded"
            else:
                score, status = 50, "degraded"
        else:
            # Unstable across rounds — looks like real per-prompt counting,
            # but against the wrong tokenizer.
            if deviation_pct < 50:
                score, status = 85, "ok"
            elif deviation_pct < 100:
                score, status = 55, "degraded"
            elif deviation_pct < 300:
                score, status = 25, "degraded"
            else:
                score, status = 0, "missing"

        return DimensionResult(
            name=self.name, score=score, status=status,
            evidence={
                "expected": expected,
                "observed_median_effective": median_actual,
                "observed_median_cache_read": median_cache_read,
                "observed_median_cache_creation": median_cache_creation,
                "deviation_pct": round(deviation_pct, 2),
                "inflation_tokens": inflation_tokens,
                "stable_across_rounds": is_stable,
                "per_round": per_round,
            },
        )

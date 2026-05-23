"""Detect whether the upstream wraps the model with an injected system prompt.

Wrapper relays (Kiro reverse-engineered, Cursor reverse-engineered, custom IDEs) prepend
their own system prompt to every request. This shows up as either:

1. `cache_read_input_tokens` >= ~500 (vendor cached their fixed system prompt), or
2. `effective_input_tokens` >> expected (no caching but visible inflation)

The model itself may still be Claude — but you're paying to ship the wrapper's
hidden instructions through your context window every call. yyc.lat surfaces this
to users as a "wrapper detected" warning so they understand the price/quality
tradeoff before buying."""
from __future__ import annotations

from app.detector.budget import BudgetExceeded
from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.dimensions.token_billing import _extract_input_tokens
from app.detector.types import ChatMessage, DimensionResult, RoundLog

PROBE = "Hi"


class WrapperDetection(Dimension):
    name = "wrapper_detection"
    weight = 0.20

    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        try:
            result = await ctx.adapter.chat(
                model=ctx.baseline.name,
                messages=[ChatMessage(role="user", content=PROBE)],
                max_tokens=10,
            )
            ctx.budget.charge(
                model=ctx.baseline.name,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )
        except BudgetExceeded:
            raise
        except Exception as e:
            return DimensionResult(
                name=self.name, score=0, status="error",
                evidence={"error": str(e)}, error=str(e),
            )

        eff, cache_read, cache_creation = _extract_input_tokens(result.raw)
        if eff == 0 and not (cache_read or cache_creation):
            eff = result.prompt_tokens

        # Baseline expectation for a one-word prompt "Hi": ~5-10 tokens.
        # System prompt sizes seen in the wild:
        #   - Kiro reverse-engineered:        ~2500 tokens (cache_read)
        #   - Continue/Cline IDE wrappers:    ~500-1500 tokens
        #   - "personality" tweaks (vague):    ~50-200 tokens
        # We measure cache_read separately because it's the strongest signal —
        # if the relay caches a fixed prompt, that prompt IS the wrapper.

        evidence = {
            "probe": PROBE,
            "effective_input_tokens": eff,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_creation,
            "response_excerpt": result.text[:120],
        }
        ctx.rounds_log.append(
            RoundLog(
                round=len(ctx.rounds_log) + 1,
                dimension=self.name,
                prompt=PROBE,
                response_excerpt=result.text[:200],
                verdict=f"eff={eff} cache_read={cache_read}",
                duration_ms=result.total_latency_ms,
            )
        )

        # Score by maximum injection size seen (cache_read OR effective excess)
        injection_size = max(cache_read, max(0, eff - 10))

        if injection_size >= 1500:
            # Heavy wrapper (Kiro-class) — pay for ~2500 tokens of hidden instructions every call
            return DimensionResult(
                name=self.name, score=0, status="missing",
                evidence={**evidence, "injection_size": injection_size,
                          "interpretation": "heavy wrapper (e.g. Kiro reverse-engineered)"},
            )
        if injection_size >= 500:
            # Medium wrapper — IDE personality wrappers, RAG injections
            return DimensionResult(
                name=self.name, score=30, status="degraded",
                evidence={**evidence, "injection_size": injection_size,
                          "interpretation": "medium wrapper (IDE / RAG injection)"},
            )
        if injection_size >= 100:
            # Light wrapper — small "be helpful" preambles
            return DimensionResult(
                name=self.name, score=70, status="degraded",
                evidence={**evidence, "injection_size": injection_size,
                          "interpretation": "light wrapper (small preamble)"},
            )
        # Clean — no injection detected
        return DimensionResult(
            name=self.name, score=100, status="ok",
            evidence={**evidence, "injection_size": injection_size,
                      "interpretation": "clean — no system prompt injection"},
        )

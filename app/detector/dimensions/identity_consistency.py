"""Multi-round identity probe. Cross-checks self-reported identity against baseline."""
from __future__ import annotations

from app.detector.budget import BudgetExceeded
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
                    model=ctx.target_model,
                    messages=[ChatMessage(role="user", content=prompt)],
                    max_tokens=80,
                )
                ctx.budget.charge(
                    model=baseline.name,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                )
            except BudgetExceeded:
                raise
            except Exception as e:
                per_round.append({"round": i, "error": str(e)})
                continue

            text = result.text.lower()
            prompt_lower = prompt.lower()
            responses.append(result.text)
            round_expected = [
                kw for kw in baseline.expected_identity_keywords if kw.lower() in text
            ]
            # Forbidden vendor names that already appear in the prompt itself
            # don't count: probes like "Are you Claude, GPT, or Gemini?" force
            # the model to repeat those names just to deny them. Only words
            # the model introduced unprompted are evidence of misidentification.
            round_forbidden = [
                kw
                for kw in baseline.forbidden_identity_keywords
                if kw.lower() in text and kw.lower() not in prompt_lower
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
                    "matched_expected": round_expected,
                    "matched_forbidden": round_forbidden,
                }
            )

        evidence = {
            "rounds_completed": len(responses),
            "expected_hits": list(set(expected_hits)),
            "forbidden_hits": list(set(forbidden_hits)),
            "per_round": per_round,
        }

        # If any forbidden vendor or wrapper name leaked, this is fake.
        if forbidden_hits:
            return DimensionResult(
                name=self.name, score=0, status="missing", evidence=evidence
            )

        if len(responses) == 0:
            return DimensionResult(
                name=self.name, score=0, status="error", evidence=evidence,
                error="no successful identity probe rounds"
            )

        # Vague case: model refused to identify itself but didn't claim wrong vendor.
        # Common with safety-trained or wrapper-stripped models — partial credit, not punitive.
        if not expected_hits:
            return DimensionResult(
                name=self.name, score=60, status="degraded", evidence=evidence
            )

        match_rate = len(set(expected_hits)) / max(1, len(baseline.expected_identity_keywords))
        # 80%+ keyword coverage => 95
        # 50-80%                => 80
        # <50%                  => 70
        if match_rate >= 0.8:
            score, status = 95, "ok"
        elif match_rate >= 0.5:
            score, status = 80, "ok"
        else:
            score, status = 70, "degraded"

        return DimensionResult(
            name=self.name, score=score, status=status, evidence=evidence
        )

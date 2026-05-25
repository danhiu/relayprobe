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

            # Per-round verdict semantics:
            #   match     — model identified itself as the expected vendor and
            #               did not claim any rival vendor as its own.
            #   mixed     — model said "I'm Claude" AND mentioned a rival
            #               vendor (e.g. "I'm Claude, not GPT made by OpenAI").
            #               This is normal explanatory speech, not lying.
            #   mismatch  — model claimed only a rival vendor, with no
            #               expected keywords present. This is the only
            #               outcome that's actual evidence of a swapped model.
            #   vague     — neither expected nor forbidden keywords found
            #               (refusal / safety preamble / off-topic).
            if round_expected and not round_forbidden:
                verdict = "match"
            elif round_expected and round_forbidden:
                verdict = "mixed"
            elif round_forbidden:
                verdict = "mismatch"
            else:
                verdict = "vague"
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

        verdicts = [r.get("verdict") for r in per_round if "verdict" in r]
        n_match = sum(1 for v in verdicts if v == "match")
        n_mixed = sum(1 for v in verdicts if v == "mixed")
        n_mismatch = sum(1 for v in verdicts if v == "mismatch")
        n_vague = sum(1 for v in verdicts if v == "vague")
        total = max(1, len(verdicts))

        evidence = {
            "rounds_completed": len(responses),
            "expected_hits": list(set(expected_hits)),
            "forbidden_hits": list(set(forbidden_hits)),
            "verdict_counts": {
                "match": n_match,
                "mixed": n_mixed,
                "mismatch": n_mismatch,
                "vague": n_vague,
            },
            "per_round": per_round,
        }

        if len(responses) == 0:
            return DimensionResult(
                name=self.name, score=0, status="error", evidence=evidence,
                error="no successful identity probe rounds"
            )

        # Hard fail: every successful round was an outright misidentification
        # (claimed only a rival vendor). At that point we're confident the
        # upstream is serving the wrong model — not a probe artefact.
        if n_mismatch == total and n_match == 0 and n_mixed == 0:
            return DimensionResult(
                name=self.name, score=0, status="missing", evidence=evidence
            )

        # Soft signals: count "true positives" as match + mixed (mixed means
        # the model still self-identified correctly, it just also referenced
        # other vendors in passing — usually because the prompt invited
        # comparison). Mismatch rounds get penalised proportionally.
        good = n_match + n_mixed
        good_ratio = good / total
        mismatch_ratio = n_mismatch / total

        if mismatch_ratio >= 0.5:
            # Majority of rounds the model claimed a rival vendor — treat as
            # likely fake even if the occasional round happened to mention
            # the right brand.
            score, status = 20, "missing"
        elif mismatch_ratio >= 0.25:
            # Partial impersonation — minority of rounds outright wrong.
            score, status = 50, "degraded"
        elif good_ratio >= 0.8:
            score, status = 95, "ok"
        elif good_ratio >= 0.5:
            score, status = 80, "ok"
        elif good > 0:
            # A correct claim exists but most rounds were vague / refused.
            score, status = 70, "degraded"
        else:
            # No expected hits anywhere — vague but not lying. Common with
            # safety-trained or wrapper-stripped models.
            score, status = 60, "degraded"

        return DimensionResult(
            name=self.name, score=score, status=status, evidence=evidence
        )

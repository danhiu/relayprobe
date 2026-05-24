"""Online check: hit /v1/models + a single minimal chat. Short-circuit gate for the rest."""
from __future__ import annotations

from app.detector.budget import BudgetExceeded
from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.types import ChatMessage, DimensionResult


class Online(Dimension):
    name = "online"
    weight = 0.20

    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        evidence: dict = {
            "models_endpoint_ok": False,
            "chat_endpoint_ok": False,
            "error": None,
        }

        try:
            models = await ctx.adapter.list_models()
            evidence["models_endpoint_ok"] = True
            evidence["model_count"] = len(models)
        except BudgetExceeded:
            raise
        except Exception as e:  # network, 4xx, 5xx, parse — fall through to chat probe
            evidence["models_endpoint_ok"] = False
            evidence["models_error"] = str(e)

        try:
            chat = await ctx.adapter.chat(
                model=ctx.target_model,
                messages=[ChatMessage(role="user", content="hi")],
                max_tokens=10,
            )
            evidence["chat_endpoint_ok"] = True
            evidence["sample_response_excerpt"] = chat.text[:80]
            ctx.budget.charge(
                model=ctx.baseline.name,
                prompt_tokens=chat.prompt_tokens,
                completion_tokens=chat.completion_tokens,
            )
        except BudgetExceeded:
            raise
        except Exception as e:
            evidence["chat_endpoint_ok"] = False
            evidence["error"] = str(e)
            return DimensionResult(
                name=self.name, score=0, status="missing", evidence=evidence,
                error=str(e),
            )

        # chat ok; partial credit if /v1/models broken
        score = 100 if evidence["models_endpoint_ok"] else 80
        return DimensionResult(
            name=self.name, score=score, status="ok", evidence=evidence
        )

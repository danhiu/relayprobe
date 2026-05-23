"""tool_use capability probe. Detects whether function calling is genuinely supported."""
from __future__ import annotations

from app.detector.budget import BudgetExceeded
from app.detector.dimensions.base import Dimension, DimensionContext
from app.detector.probes import draw
from app.detector.types import ChatMessage, DimensionResult, RoundLog, ToolDefinition

WEATHER_TOOL = ToolDefinition(
    name="get_weather",
    description="Get current weather for a given location.",
    parameters={
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"],
    },
)


class ToolUse(Dimension):
    name = "tool_use"
    weight = 0.25

    async def evaluate(self, ctx: DimensionContext) -> DimensionResult:
        if not ctx.baseline.supports.get("tool_use", False):
            return DimensionResult(
                name=self.name, score=0, status="skipped",
                evidence={"reason": "baseline marks model as not supporting tool_use"},
            )

        prompt, _nonce = draw("tool_use", rng=ctx.rng)

        try:
            result = await ctx.adapter.chat_with_tools(
                model=ctx.baseline.name,
                messages=[ChatMessage(role="user", content=prompt)],
                tools=[WEATHER_TOOL],
                max_tokens=200,
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
                name=self.name, score=0, status="missing",
                evidence={"prompt": prompt, "error": str(e)},
                error=str(e),
            )

        evidence = {
            "prompt": prompt,
            "tool_calls": result.tool_calls,
            "response_excerpt": result.text[:200],
        }

        if not result.tool_calls:
            ctx.rounds_log.append(
                RoundLog(
                    round=len(ctx.rounds_log) + 1, dimension=self.name,
                    prompt=prompt, response_excerpt=result.text[:200],
                    verdict="text_only", duration_ms=result.total_latency_ms,
                )
            )
            return DimensionResult(
                name=self.name, score=40, status="degraded", evidence=evidence
            )

        # Did the call target the right tool with required args?
        call = result.tool_calls[0]
        right_tool = call.get("name") == WEATHER_TOOL.name
        args = call.get("arguments") or {}
        has_required = "location" in args and bool(args.get("location"))

        if right_tool and has_required:
            score, status, verdict = 100, "ok", "tool_call_ok"
        elif right_tool:
            score, status, verdict = 60, "degraded", "tool_call_missing_args"
        else:
            score, status, verdict = 40, "degraded", "wrong_tool"

        ctx.rounds_log.append(
            RoundLog(
                round=len(ctx.rounds_log) + 1, dimension=self.name,
                prompt=prompt, response_excerpt=str(call)[:200],
                verdict=verdict, duration_ms=result.total_latency_ms,
            )
        )
        return DimensionResult(
            name=self.name, score=score, status=status, evidence=evidence
        )

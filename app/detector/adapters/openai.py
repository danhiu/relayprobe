"""OpenAI /v1/chat/completions adapter."""
from __future__ import annotations

import json
import time
from collections.abc import Iterable

import httpx

from app.detector.adapters.base import Adapter
from app.detector.types import ChatMessage, ChatResult, ToolDefinition


class OpenAIAdapter(Adapter):
    provider = "openai"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }

    def _to_messages(self, messages: Iterable[ChatMessage]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.get(
                f"{self.base_url}/v1/models", headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]

    async def _post_chat(self, payload: dict) -> tuple[dict, int]:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()
        latency_ms = int((time.monotonic() - start) * 1000)
        return body, latency_ms

    async def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        body, latency_ms = await self._post_chat(
            {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": self._to_messages(messages),
            }
        )
        choice = body.get("choices", [{}])[0]
        msg = choice.get("message", {})
        return ChatResult(
            text=msg.get("content") or "",
            prompt_tokens=body.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=body.get("usage", {}).get("completion_tokens", 0),
            total_latency_ms=latency_ms,
            tool_calls=[],
            raw=body,
        )

    async def chat_with_tools(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        tools: list[ToolDefinition],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        body, latency_ms = await self._post_chat(
            {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": self._to_messages(messages),
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        },
                    }
                    for t in tools
                ],
                "tool_choice": "auto",
            }
        )
        choice = body.get("choices", [{}])[0]
        msg = choice.get("message", {})
        tool_calls: list[dict] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw_args = fn.get("arguments", "")
            try:
                parsed = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                parsed = {}
            tool_calls.append(
                {
                    "id": tc.get("id"),
                    "name": fn.get("name"),
                    "arguments": parsed,
                    "arguments_raw": raw_args,
                }
            )
        return ChatResult(
            text=msg.get("content") or "",
            prompt_tokens=body.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=body.get("usage", {}).get("completion_tokens", 0),
            total_latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw=body,
        )

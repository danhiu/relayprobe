"""Anthropic /v1/messages adapter. Native protocol — required for true authenticity check."""
from __future__ import annotations

import time
from collections.abc import Iterable

import httpx

from app.detector.adapters.base import Adapter
from app.detector.types import ChatMessage, ChatResult, ToolDefinition

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter(Adapter):
    provider = "anthropic"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _to_messages(self, messages: Iterable[ChatMessage]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if m.role == "system":
                # Anthropic uses top-level `system`; we attach via separate field in payload.
                continue
            out.append({"role": m.role, "content": m.content})
        return out

    def _system(self, messages: Iterable[ChatMessage]) -> str | None:
        for m in messages:
            if m.role == "system":
                return m.content
        return None

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.get(
                f"{self.base_url}/v1/models", headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]

    async def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        msgs = list(messages)
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._to_messages(msgs),
        }
        sys = self._system(msgs)
        if sys:
            payload["system"] = sys

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()
        latency_ms = int((time.monotonic() - start) * 1000)

        text_parts = [
            blk["text"] for blk in body.get("content", []) if blk.get("type") == "text"
        ]
        return ChatResult(
            text="".join(text_parts),
            prompt_tokens=body.get("usage", {}).get("input_tokens", 0),
            completion_tokens=body.get("usage", {}).get("output_tokens", 0),
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
        msgs = list(messages)
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._to_messages(msgs),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ],
        }
        sys = self._system(msgs)
        if sys:
            payload["system"] = sys

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            body = resp.json()
        latency_ms = int((time.monotonic() - start) * 1000)

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for blk in body.get("content", []):
            if blk.get("type") == "text":
                text_parts.append(blk["text"])
            elif blk.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": blk.get("id"),
                        "name": blk["name"],
                        "arguments": blk.get("input", {}),
                    }
                )
        return ChatResult(
            text="".join(text_parts),
            prompt_tokens=body.get("usage", {}).get("input_tokens", 0),
            completion_tokens=body.get("usage", {}).get("output_tokens", 0),
            total_latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw=body,
        )

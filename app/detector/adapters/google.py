"""Google Gemini generateContent adapter."""
from __future__ import annotations

import time
from collections.abc import Iterable

import httpx

from app.detector.adapters.base import Adapter
from app.detector.types import ChatMessage, ChatResult, ToolDefinition


class GoogleAdapter(Adapter):
    provider = "google"

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self.api_key,
            "content-type": "application/json",
        }

    def _to_contents(self, messages: Iterable[ChatMessage]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if m.role == "system":
                continue  # passed via systemInstruction below
            role = "user" if m.role == "user" else "model"
            out.append({"role": role, "parts": [{"text": m.content}]})
        return out

    def _system(self, messages: Iterable[ChatMessage]) -> dict | None:
        for m in messages:
            if m.role == "system":
                return {"parts": [{"text": m.content}]}
        return None

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.get(
                f"{self.base_url}/v1beta/models", headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
            # name format: "models/gemini-3-1-pro"
            return [
                m["name"].split("/", 1)[1] if "/" in m["name"] else m["name"]
                for m in data.get("models", [])
            ]

    async def _post(self, model: str, payload: dict) -> tuple[dict, int]:
        url = f"{self.base_url}/v1beta/models/{model}:generateContent"
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            body = resp.json()
        latency_ms = int((time.monotonic() - start) * 1000)
        return body, latency_ms

    def _parse(self, body: dict, latency_ms: int) -> ChatResult:
        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for cand in body.get("candidates", []):
            for p in cand.get("content", {}).get("parts", []):
                if "text" in p:
                    text_parts.append(p["text"])
                elif "functionCall" in p:
                    fc = p["functionCall"]
                    tool_calls.append(
                        {
                            "id": None,
                            "name": fc.get("name"),
                            "arguments": fc.get("args", {}),
                        }
                    )
        usage = body.get("usageMetadata", {})
        return ChatResult(
            text="".join(text_parts),
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
            total_latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw=body,
        )

    async def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        msgs = list(messages)
        payload: dict = {
            "contents": self._to_contents(msgs),
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        sys = self._system(msgs)
        if sys:
            payload["systemInstruction"] = sys

        body, latency_ms = await self._post(model, payload)
        return self._parse(body, latency_ms)

    async def chat_with_tools(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        tools: list[ToolDefinition],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        msgs = list(messages)
        payload: dict = {
            "contents": self._to_contents(msgs),
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        }
                        for t in tools
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        sys = self._system(msgs)
        if sys:
            payload["systemInstruction"] = sys

        body, latency_ms = await self._post(model, payload)
        return self._parse(body, latency_ms)

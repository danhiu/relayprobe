"""Adapter ABC. Three concrete subclasses (anthropic/openai/google) speak each vendor's
native protocol but expose the same normalized interface to the rest of the detector."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.detector.types import ChatMessage, ChatResult, Provider, ToolDefinition


class Adapter(ABC):
    provider: Provider

    def __init__(self, base_url: str, api_key: str, timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Return model IDs available at the upstream's `/v1/models` (or equivalent)."""

    @abstractmethod
    async def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        """Single-turn or multi-turn chat with no tools."""

    @abstractmethod
    async def chat_with_tools(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        tools: list[ToolDefinition],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> ChatResult:
        """Chat with function-calling tools enabled."""

    async def aclose(self) -> None:  # noqa: B027 — intentional default no-op
        """Override if subclass holds an httpx.AsyncClient."""

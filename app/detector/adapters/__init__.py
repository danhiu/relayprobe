"""Adapter factory."""
from __future__ import annotations

from app.detector.adapters.base import Adapter
from app.detector.types import Provider


def get_adapter(provider: Provider, *, base_url: str, api_key: str) -> Adapter:
    if provider == "anthropic":
        from app.detector.adapters.anthropic import AnthropicAdapter
        return AnthropicAdapter(base_url=base_url, api_key=api_key)
    if provider == "openai":
        from app.detector.adapters.openai import OpenAIAdapter
        return OpenAIAdapter(base_url=base_url, api_key=api_key)
    if provider == "google":
        from app.detector.adapters.google import GoogleAdapter
        return GoogleAdapter(base_url=base_url, api_key=api_key)
    raise ValueError(f"unknown provider: {provider!r}")

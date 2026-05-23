import pytest

from app.detector.adapters import get_adapter
from app.detector.adapters.base import Adapter


def test_get_adapter_anthropic():
    a = get_adapter("anthropic", base_url="https://x", api_key="sk-test")
    assert isinstance(a, Adapter)
    assert a.provider == "anthropic"


def test_get_adapter_openai():
    a = get_adapter("openai", base_url="https://x", api_key="sk-test")
    assert a.provider == "openai"


def test_get_adapter_google():
    a = get_adapter("google", base_url="https://x", api_key="sk-test")
    assert a.provider == "google"


def test_get_adapter_unknown_provider_raises():
    with pytest.raises(ValueError):
        get_adapter("xai", base_url="https://x", api_key="sk-test")

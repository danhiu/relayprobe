import httpx
import respx

from app.detector.adapters.google import GoogleAdapter
from app.detector.types import ChatMessage, ToolDefinition


@respx.mock
async def test_chat_basic():
    respx.post(
        "https://up.example.com/v1beta/models/gemini-3-1-pro:generateContent"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "Hi"}],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 4,
                    "candidatesTokenCount": 1,
                    "totalTokenCount": 5,
                },
            },
        )
    )
    a = GoogleAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat(
        model="gemini-3-1-pro",
        messages=[ChatMessage(role="user", content="hi")],
    )
    assert result.text == "Hi"
    assert result.prompt_tokens == 4
    assert result.completion_tokens == 1


@respx.mock
async def test_chat_with_tools_returns_function_call():
    respx.post(
        "https://up.example.com/v1beta/models/gemini-3-1-pro:generateContent"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "get_weather",
                                        "args": {"location": "Tokyo"},
                                    }
                                }
                            ],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 50,
                    "candidatesTokenCount": 10,
                    "totalTokenCount": 60,
                },
            },
        )
    )
    a = GoogleAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat_with_tools(
        model="gemini-3-1-pro",
        messages=[ChatMessage(role="user", content="weather?")],
        tools=[
            ToolDefinition(
                name="get_weather",
                description="Get weather",
                parameters={
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            )
        ],
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "get_weather"
    assert result.tool_calls[0]["arguments"] == {"location": "Tokyo"}


@respx.mock
async def test_list_models():
    respx.get("https://up.example.com/v1beta/models").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {"name": "models/gemini-3-1-pro"},
                    {"name": "models/gemini-3-flash"},
                ]
            },
        )
    )
    a = GoogleAdapter(base_url="https://up.example.com", api_key="sk-test")
    models = await a.list_models()
    assert "gemini-3-1-pro" in models

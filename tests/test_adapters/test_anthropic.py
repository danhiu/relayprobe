import httpx
import respx

from app.detector.adapters.anthropic import AnthropicAdapter
from app.detector.types import ChatMessage, ToolDefinition


@respx.mock
async def test_chat_basic():
    respx.post("https://up.example.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there"}],
                "model": "claude-opus-4-7",
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )
    )
    a = AnthropicAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat(
        model="claude-opus-4-7",
        messages=[ChatMessage(role="user", content="hello")],
    )
    assert result.text == "Hi there"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 3
    assert result.tool_calls == []


@respx.mock
async def test_chat_with_tools_returns_tool_calls():
    respx.post("https://up.example.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_2",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "get_weather",
                        "input": {"location": "Tokyo"},
                    }
                ],
                "model": "claude-opus-4-7",
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 50, "output_tokens": 20},
            },
        )
    )
    a = AnthropicAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat_with_tools(
        model="claude-opus-4-7",
        messages=[ChatMessage(role="user", content="weather in Tokyo?")],
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
    respx.get("https://up.example.com/v1/models").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": "claude-opus-4-7", "type": "model"},
                    {"id": "claude-sonnet-4-6", "type": "model"},
                ]
            },
        )
    )
    a = AnthropicAdapter(base_url="https://up.example.com", api_key="sk-test")
    models = await a.list_models()
    assert "claude-opus-4-7" in models

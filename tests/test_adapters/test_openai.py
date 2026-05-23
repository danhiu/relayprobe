import httpx
import respx

from app.detector.adapters.openai import OpenAIAdapter
from app.detector.types import ChatMessage, ToolDefinition


@respx.mock
async def test_chat_basic():
    respx.post("https://up.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cmpl_1",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hi"},
                        "finish_reason": "stop",
                        "index": 0,
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
            },
        )
    )
    a = OpenAIAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat(
        model="gpt-5-5", messages=[ChatMessage(role="user", content="hi")]
    )
    assert result.text == "Hi"
    assert result.prompt_tokens == 5


@respx.mock
async def test_chat_with_tools_returns_tool_calls():
    respx.post("https://up.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cmpl_2",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"location": "Tokyo"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                        "index": 0,
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            },
        )
    )
    a = OpenAIAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat_with_tools(
        model="gpt-5-5",
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
async def test_chat_text_when_tool_calls_arguments_invalid_json():
    respx.post("https://up.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cmpl_3",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_x",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": "{not-json}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5},
            },
        )
    )
    a = OpenAIAdapter(base_url="https://up.example.com", api_key="sk-test")
    result = await a.chat_with_tools(
        model="gpt-5-5",
        messages=[ChatMessage(role="user", content="x")],
        tools=[
            ToolDefinition(
                name="get_weather", description="", parameters={"type": "object"}
            )
        ],
    )
    # invalid json arguments still surface, but as raw string under "arguments_raw"
    assert result.tool_calls[0]["name"] == "get_weather"
    assert result.tool_calls[0]["arguments"] == {}
    assert result.tool_calls[0]["arguments_raw"] == "{not-json}"

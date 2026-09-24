"""Tests the Anthropic adapter's translation logic with a fake client - no network calls."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import (
    AssistantMessage,
    LLMError,
    ToolCall,
    ToolResult,
    ToolResultsMessage,
    ToolSpec,
    UserMessage,
)

TOOLS = [ToolSpec(name="read_file", description="Read a file", input_schema={"type": "object", "properties": {}})]


class FakeMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def make_provider(fake: FakeMessages) -> AnthropicProvider:
    provider = AnthropicProvider(api_key="test-key", model="claude-opus-5")
    provider._client = SimpleNamespace(beta=SimpleNamespace(messages=fake))  # type: ignore[assignment]
    return provider


def response(content: list[Any], stop_reason: str) -> SimpleNamespace:
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def test_tool_use_response_is_normalized() -> None:
    blocks = [
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="tool_use", id="toolu_1", name="read_file", input={"path": "a.js"}),
    ]
    fake = FakeMessages(response(blocks, "tool_use"))
    turn = make_provider(fake).tool_call("system", [UserMessage(text="hi")], TOOLS)

    assert turn.stop_reason == "tool_use"
    assert turn.message.tool_calls == [ToolCall(id="toolu_1", name="read_file", arguments={"path": "a.js"})]
    assert turn.message.provider_state is blocks  # kept for exact replay, incl. thinking
    assert (turn.input_tokens, turn.output_tokens) == (10, 5)

    request = fake.calls[0]
    assert request["model"] == "claude-opus-5"
    assert request["thinking"] == {"type": "adaptive"}
    assert request["tools"][0]["name"] == "read_file"
    assert request["messages"] == [{"role": "user", "content": "hi"}]


def test_conversation_translation() -> None:
    raw_blocks = [SimpleNamespace(type="tool_use", id="t1", name="read_file", input={})]
    history = [
        UserMessage(text="bug"),
        AssistantMessage(tool_calls=[ToolCall(id="t1", name="read_file", arguments={})], provider_state=raw_blocks),
        ToolResultsMessage(results=[ToolResult(tool_call_id="t1", content="nope", is_error=True)]),
    ]
    fake = FakeMessages(response([SimpleNamespace(type="text", text="done")], "end_turn"))
    turn = make_provider(fake).tool_call("system", history, TOOLS)

    sent = fake.calls[0]["messages"]
    assert sent[1] == {"role": "assistant", "content": raw_blocks}
    assert sent[2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "nope", "is_error": True}],
    }
    assert turn.stop_reason == "end_turn"
    assert turn.message.text == "done"


def test_assistant_message_without_provider_state_is_rebuilt() -> None:
    message = AssistantMessage(text="checking", tool_calls=[ToolCall(id="t1", name="read_file", arguments={"path": "x"})])
    assert AnthropicProvider._to_api_message(message) == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "checking"},
            {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "x"}},
        ],
    }


@pytest.mark.parametrize(("api_reason", "expected"), [("refusal", "refusal"), ("max_tokens", "max_tokens"), ("end_turn", "end_turn")])
def test_stop_reason_mapping(api_reason: str, expected: str) -> None:
    assert AnthropicProvider._stop_reason(api_reason, []) == expected


def test_connection_error_becomes_llm_error() -> None:
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    with pytest.raises(LLMError, match="Could not connect"):
        make_provider(FakeMessages(error=error)).tool_call("s", [UserMessage(text="x")], TOOLS)


def test_real_sdk_request_shape_with_mock_transport() -> None:
    """Runs the real SDK end to end against a fake HTTP transport to check the wire format."""
    import json

    import httpx2

    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5",
            "content": [{"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "a.js"}}],
            "stop_reason": "tool_use", "stop_sequence": None,
            "usage": {"input_tokens": 12, "output_tokens": 7},
        })

    provider = AnthropicProvider(api_key="test-key", model="claude-opus-5")
    provider._client = anthropic.Anthropic(
        api_key="test-key", http_client=httpx2.Client(transport=httpx2.MockTransport(handler))
    )
    turn = provider.tool_call("system", [UserMessage(text="hi")], TOOLS)

    assert captured["headers"]["anthropic-beta"] == "server-side-fallback-2026-07-01"
    assert captured["body"]["fallbacks"] == "default"
    assert captured["body"]["thinking"] == {"type": "adaptive"}
    assert turn.message.tool_calls[0].arguments == {"path": "a.js"}

    provider.tool_call("system", [UserMessage(text="hi"), turn.message], TOOLS)
    assert captured["body"]["messages"][1]["content"][0]["id"] == "toolu_1"


def test_generate_returns_text() -> None:
    fake = FakeMessages(response([SimpleNamespace(type="text", text=" Fix cart total \n")], "end_turn"))
    assert make_provider(fake).generate("system", "prompt") == "Fix cart total"

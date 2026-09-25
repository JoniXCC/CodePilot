"""OllamaProvider tests against a mock HTTP transport - no Ollama installation needed."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.llm.base import AssistantMessage, LLMError, ToolCall, ToolResult, ToolResultsMessage, ToolSpec, UserMessage
from app.llm.factory import create_provider
from app.llm.ollama_provider import OllamaProvider

TOOLS = [
    ToolSpec(name="read_file", description="Read a file", input_schema={"type": "object", "properties": {"path": {"type": "string"}}}),
    ToolSpec(name="finish", description="Finish", input_schema={"type": "object", "properties": {}}),
]


def make_provider(handler: Callable[[httpx.Request], httpx.Response], captured: list[dict[str, Any]] | None = None) -> OllamaProvider:
    def recording_handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(json.loads(request.content))
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(recording_handler))
    return OllamaProvider(model="qwen2.5-coder:7b", http_client=client)


def reply(message: dict[str, Any], done_reason: str = "stop") -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(
        200, json={"message": {"role": "assistant", **message}, "done_reason": done_reason, "prompt_eval_count": 120, "eval_count": 15}
    )


def test_tool_call_response_and_request_shape() -> None:
    captured: list[dict[str, Any]] = []
    provider = make_provider(reply({"content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "a.js"}}}]}), captured)
    turn = provider.tool_call("system prompt", [UserMessage(text="bug")], TOOLS)

    assert turn.stop_reason == "tool_use"
    [call] = turn.message.tool_calls
    assert (call.name, call.arguments) == ("read_file", {"path": "a.js"})
    assert call.id.startswith("call_")  # generated, since Ollama may not send ids
    assert (turn.input_tokens, turn.output_tokens) == (120, 15)

    body = captured[0]
    assert body["model"] == "qwen2.5-coder:7b" and body["stream"] is False
    assert body["options"]["num_ctx"] == 16_384
    assert body["messages"][0] == {"role": "system", "content": "system prompt"}
    assert body["tools"][0] == {"type": "function", "function": {"name": "read_file", "description": "Read a file", "parameters": TOOLS[0].input_schema}}


def test_conversation_translation_pairs_results_with_tool_names() -> None:
    captured: list[dict[str, Any]] = []
    provider = make_provider(reply({"content": "All done."}), captured)
    history = [
        UserMessage(text="bug"),
        AssistantMessage(tool_calls=[ToolCall(id="c1", name="read_file", arguments={"path": "x"})]),
        ToolResultsMessage(results=[ToolResult(tool_call_id="c1", content="File not found", is_error=True)]),
    ]
    turn = provider.tool_call("s", history, TOOLS)

    sent = captured[0]["messages"]
    assert sent[2] == {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "x"}}}]}
    assert sent[3] == {"role": "tool", "content": "Error: File not found", "tool_name": "read_file"}
    assert turn.stop_reason == "end_turn" and turn.message.text == "All done."


def test_arguments_as_json_string_are_parsed() -> None:
    provider = make_provider(reply({"content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": '{"path": "b.py"}'}}]}))
    assert provider.tool_call("s", [UserMessage(text="x")], TOOLS).message.tool_calls[0].arguments == {"path": "b.py"}


@pytest.mark.parametrize(
    "text",
    [
        '{"name": "read_file", "arguments": {"path": "src/cart.js"}}',
        '```json\n{"name": "read_file", "arguments": {"path": "src/cart.js"}}\n```',
        # Real reply captured from qwen2.5-coder:7b: prose, then the call in a fenced block.
        "Let's start by reading the `src/cart.js` file.\n\nPlease run the following command:\n\n"
        '```json\n{"name": "read_file", "arguments": {"path": "src/cart.js"}}\n```',
    ],
)
def test_tool_call_written_as_text_is_recovered(text: str) -> None:
    turn = make_provider(reply({"content": text})).tool_call("s", [UserMessage(text="x")], TOOLS)
    assert turn.stop_reason == "tool_use"
    assert turn.message.tool_calls[0].name == "read_file"
    assert turn.message.tool_calls[0].arguments == {"path": "src/cart.js"}


def test_json_text_naming_an_unknown_tool_is_left_as_text() -> None:
    turn = make_provider(reply({"content": '{"name": "rm_rf", "arguments": {}}'})).tool_call("s", [UserMessage(text="x")], TOOLS)
    assert turn.stop_reason == "end_turn" and not turn.message.tool_calls


def test_length_limit_maps_to_max_tokens() -> None:
    turn = make_provider(reply({"content": "partial"}, done_reason="length")).tool_call("s", [UserMessage(text="x")], TOOLS)
    assert turn.stop_reason == "max_tokens"


def test_missing_model_gives_pull_hint() -> None:
    provider = make_provider(lambda _r: httpx.Response(404, json={"error": "model 'qwen2.5-coder:7b' not found"}))
    with pytest.raises(LLMError, match="ollama pull qwen2.5-coder:7b"):
        provider.tool_call("s", [UserMessage(text="x")], TOOLS)


def test_ollama_not_running() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(LLMError, match="is Ollama running"):
        make_provider(refuse).tool_call("s", [UserMessage(text="x")], TOOLS)


def test_server_error_detail_is_reported() -> None:
    provider = make_provider(lambda _r: httpx.Response(500, json={"error": "out of memory"}))
    with pytest.raises(LLMError, match="out of memory"):
        provider.generate("s", "p")


def test_generate_returns_text() -> None:
    assert make_provider(reply({"content": " Fix cart total \n"})).generate("s", "p") == "Fix cart total"


def test_factory_selects_ollama() -> None:
    settings = Settings(_env_file=None, llm_provider="ollama", ollama_model="llama3.1:8b")
    provider = create_provider(settings)
    assert isinstance(provider, OllamaProvider) and provider.model == "llama3.1:8b"
    assert settings.model_name == "llama3.1:8b"


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="expected 'anthropic' or 'ollama'"):
        create_provider(Settings(_env_file=None, llm_provider="nope"))

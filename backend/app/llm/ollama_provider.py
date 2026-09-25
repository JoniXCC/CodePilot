"""Local-model implementation of LLMProvider, using Ollama's /api/chat endpoint.

Runs entirely on your machine - free, private, and a good test of the provider
abstraction: nothing outside app/llm/ had to change to add it.
"""

import json
import uuid
from typing import Any

import httpx

from app.llm.base import (
    AssistantMessage,
    LLMError,
    LLMProvider,
    LLMTurn,
    Message,
    StopReason,
    ToolCall,
    ToolResultsMessage,
    ToolSpec,
    UserMessage,
)

REQUEST_TIMEOUT_SECONDS = 600  # local models on a laptop can take a while per step


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        num_ctx: int = 16_384,
        temperature: float = 0.2,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        # Ollama's default context window is small; tool schemas + file contents need more.
        self.options = {"num_ctx": num_ctx, "temperature": temperature}
        self._http = http_client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)

    def _chat(self, messages: list[dict[str, Any]], tools: list[ToolSpec] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False, "options": self.options}
        if tools:
            body["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}}
                for t in tools
            ]
        try:
            response = self._http.post(f"{self.base_url}/api/chat", json=body)
        except httpx.ConnectError as exc:
            raise LLMError(f"Could not connect to Ollama at {self.base_url} - is Ollama running?") from exc
        except httpx.TimeoutException as exc:
            raise LLMError("Ollama took too long to respond") from exc

        if response.status_code == 404:
            raise LLMError(f"Ollama model '{self.model}' is not installed - run: ollama pull {self.model}")
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", response.text)
            except ValueError:
                detail = response.text
            raise LLMError(f"Ollama error {response.status_code}: {detail}")
        return response.json()

    def generate(self, system: str, prompt: str) -> str:
        data = self._chat([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        return data.get("message", {}).get("content", "").strip()

    def tool_call(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> LLMTurn:
        data = self._chat([{"role": "system", "content": system}, *self._to_api_messages(messages)], tools)
        message = data.get("message", {})
        text = message.get("content") or ""
        tool_names = {t.name for t in tools}

        tool_calls = [self._parse_tool_call(call) for call in message.get("tool_calls") or []]
        if not tool_calls:
            # Some local models write the call as JSON text instead of using the tool_calls field.
            fallback = self._tool_call_from_text(text, tool_names)
            if fallback:
                tool_calls = [fallback]

        return LLMTurn(
            message=AssistantMessage(text=text, tool_calls=tool_calls),
            stop_reason=self._stop_reason(data.get("done_reason"), tool_calls),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

    @staticmethod
    def _parse_tool_call(call: dict[str, Any]) -> ToolCall:
        function = call.get("function", {})
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):  # some models return arguments as a JSON string
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        # Ollama doesn't always return call ids, so make our own to pair calls with results.
        return ToolCall(id=call.get("id") or f"call_{uuid.uuid4().hex[:12]}", name=function.get("name", ""), arguments=arguments)

    @staticmethod
    def _tool_call_from_text(text: str, tool_names: set[str]) -> ToolCall | None:
        """Find a {"name": ..., "arguments": {...}} object anywhere in the reply, e.g. in a ```json block
        after some prose. Only names of real tools are accepted."""
        decoder = json.JSONDecoder()
        for start in (i for i, char in enumerate(text) if char == "{"):
            try:
                data, _end = decoder.raw_decode(text, start)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or data.get("name") not in tool_names:
                continue
            arguments = data.get("arguments", data.get("parameters", {}))
            if isinstance(arguments, dict):
                return ToolCall(id=f"call_{uuid.uuid4().hex[:12]}", name=data["name"], arguments=arguments)
        return None

    @staticmethod
    def _stop_reason(done_reason: str | None, tool_calls: list[ToolCall]) -> StopReason:
        if tool_calls:
            return "tool_use"
        if done_reason == "length":
            return "max_tokens"
        return "end_turn"

    @staticmethod
    def _to_api_messages(messages: list[Message]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        names_by_call_id: dict[str, str] = {}
        for message in messages:
            if isinstance(message, UserMessage):
                converted.append({"role": "user", "content": message.text})
            elif isinstance(message, AssistantMessage):
                names_by_call_id.update({c.id: c.name for c in message.tool_calls})
                entry: dict[str, Any] = {"role": "assistant", "content": message.text}
                if message.tool_calls:
                    entry["tool_calls"] = [{"function": {"name": c.name, "arguments": c.arguments}} for c in message.tool_calls]
                converted.append(entry)
            elif isinstance(message, ToolResultsMessage):
                # Ollama matches results to calls by order, one "tool" message per result.
                for result in message.results:
                    content = f"Error: {result.content}" if result.is_error else result.content
                    converted.append({"role": "tool", "content": content, "tool_name": names_by_call_id.get(result.tool_call_id, "")})
        return converted

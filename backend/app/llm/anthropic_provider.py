"""Claude implementation of LLMProvider, using the official Anthropic SDK."""

from typing import Any

import anthropic

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

MAX_TOKENS = 16_000
# If a safety classifier declines a request, the API re-runs it on a suitable
# fallback model server-side instead of returning a refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None, model: str, effort: str = "high") -> None:
        # With api_key=None the SDK falls back to ANTHROPIC_API_KEY / `ant auth login`.
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.effort = effort

    def _create(self, **kwargs: Any) -> Any:
        try:
            return self._client.beta.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                # Adaptive thinking: the model decides how much to reason. The reasoning
                # itself is never returned to users (display defaults to "omitted").
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
                **kwargs,
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic API key is invalid") from exc
        except TypeError as exc:
            # The SDK raises TypeError (before any HTTP call) when no credentials exist at all.
            if "authentication method" in str(exc):
                raise LLMError("No Anthropic API key configured - set ANTHROPIC_API_KEY in .env") from exc
            raise
        except anthropic.RateLimitError as exc:
            raise LLMError("Anthropic rate limit reached; try again shortly") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not connect to the Anthropic API") from exc

    def generate(self, system: str, prompt: str) -> str:
        response = self._create(system=system, messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def tool_call(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> LLMTurn:
        response = self._create(
            system=system,
            messages=[self._to_api_message(m) for m in messages],
            tools=[
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, arguments=dict(b.input))
            for b in response.content
            if b.type == "tool_use"
        ]
        return LLMTurn(
            # Keep the full content (incl. thinking blocks) so the next request replays it unchanged.
            message=AssistantMessage(text=text, tool_calls=tool_calls, provider_state=response.content),
            stop_reason=self._stop_reason(response.stop_reason, tool_calls),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    @staticmethod
    def _stop_reason(api_reason: str | None, tool_calls: list[ToolCall]) -> StopReason:
        if api_reason == "tool_use" or tool_calls:
            return "tool_use"
        if api_reason in ("max_tokens", "refusal"):
            return api_reason
        return "end_turn"

    @staticmethod
    def _to_api_message(message: Message) -> dict[str, Any]:
        if isinstance(message, UserMessage):
            return {"role": "user", "content": message.text}
        if isinstance(message, ToolResultsMessage):
            # All results for one assistant turn go back in a single user message.
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.tool_call_id,
                        "content": r.content,
                        "is_error": r.is_error,
                    }
                    for r in message.results
                ],
            }
        if isinstance(message, AssistantMessage) and message.provider_state is not None:
            return {"role": "assistant", "content": message.provider_state}
        content: list[dict[str, Any]] = []
        if message.text:
            content.append({"type": "text", "text": message.text})
        content += [
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
            for c in message.tool_calls
        ]
        return {"role": "assistant", "content": content}

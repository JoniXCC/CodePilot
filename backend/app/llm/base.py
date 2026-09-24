"""Provider-neutral LLM interface.

The agent loop only ever talks to `LLMProvider` using the small message types below.
Each concrete provider (Anthropic, a scripted fake, maybe OpenAI later) translates
these to and from its own API format. Swapping providers therefore never touches
the agent, the tools, or the web layer.
"""

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    """What the model is told about a tool: name, purpose and a JSON schema for its arguments."""

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    is_error: bool = False


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    text: str


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    # Provider-specific payload needed to replay this turn exactly (e.g. thinking blocks).
    # Opaque to everyone except the provider that produced it.
    provider_state: Any = Field(default=None, exclude=True)


class ToolResultsMessage(BaseModel):
    role: Literal["tool_results"] = "tool_results"
    results: list[ToolResult]


Message = UserMessage | AssistantMessage | ToolResultsMessage

StopReason = Literal["tool_use", "end_turn", "max_tokens", "refusal", "error"]


class LLMTurn(BaseModel):
    """One model response in the agent loop."""

    message: AssistantMessage
    stop_reason: StopReason
    input_tokens: int = 0
    output_tokens: int = 0


class LLMError(Exception):
    """The provider could not produce a response (network, auth, rate limit...)."""


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, system: str, prompt: str) -> str:
        """Single-shot text generation (used for e.g. commit messages)."""

    @abstractmethod
    def tool_call(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> LLMTurn:
        """One step of the agent loop: the model either calls tools or finishes."""

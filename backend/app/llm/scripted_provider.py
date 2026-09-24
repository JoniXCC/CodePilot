"""A fake LLM that replays a predefined list of tool calls.

Used by the test suite and for offline demos: the agent loop, tools, events and
database all run for real, only the "thinking" is scripted. This makes tests
deterministic, free and runnable without an API key.
"""

from typing import Any

from pydantic import BaseModel

from app.llm.base import AssistantMessage, LLMProvider, LLMTurn, Message, ToolCall, ToolSpec


class ScriptedStep(BaseModel):
    tool: str
    arguments: dict[str, Any] = {}


class ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, steps: list[ScriptedStep], final_text: str = "Done.") -> None:
        self.steps = steps
        self.final_text = final_text
        self.calls_made = 0
        self.seen_messages: list[list[Message]] = []

    def generate(self, system: str, prompt: str) -> str:
        return self.final_text

    def tool_call(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> LLMTurn:
        self.seen_messages.append(list(messages))
        if self.calls_made >= len(self.steps):
            return LLMTurn(message=AssistantMessage(text=self.final_text), stop_reason="end_turn")
        step = self.steps[self.calls_made]
        self.calls_made += 1
        call = ToolCall(id=f"call_{self.calls_made}", name=step.tool, arguments=step.arguments)
        return LLMTurn(message=AssistantMessage(tool_calls=[call]), stop_reason="tool_use")

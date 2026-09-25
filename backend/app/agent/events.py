"""Timeline events emitted by the agent loop.

These are what the UI shows. They contain short, factual action summaries
("Reading src/cart.js") - never the model's private reasoning.
"""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

EventType = Literal["status", "tool_started", "tool_finished", "hypothesis", "error", "done"]


class AgentEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    type: EventType
    message: str
    tool: str | None = None
    call_id: str | None = None  # links a tool_finished event to its tool_started event
    success: bool | None = None
    warning: bool = False  # succeeded, but with a negative result such as failing tests
    detail: str | None = None  # trimmed tool output for the expandable timeline row
    duration_ms: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


EventSink = Callable[[AgentEvent], None]


def ignore_events(event: AgentEvent) -> None:
    pass

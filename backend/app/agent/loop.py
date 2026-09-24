"""The agent loop.

    ask the LLM -> it requests tool calls -> run them (safely) -> send results back -> repeat

until the model calls `finish`, stops on its own, or we hit the step limit.
The loop never writes files: edits accumulate in the ChangeSet for the user to review.
"""

import logging
import threading
import time
from typing import Literal

from pydantic import BaseModel

from app.agent.events import AgentEvent, EventSink, ignore_events
from app.agent.prompts import SYSTEM_PROMPT, initial_prompt
from app.agent.registry import ToolContext, ToolRegistry
from app.agent.toolset import FinishArgs
from app.llm.base import LLMError, LLMProvider, Message, ToolResult, ToolResultsMessage, UserMessage

logger = logging.getLogger("codepilot.agent")

RunStatus = Literal["proposed", "no_changes", "failed", "cancelled"]


class AgentRunResult(BaseModel):
    status: RunStatus
    summary: str = ""
    root_cause: str = ""
    fix_explanation: str = ""
    hypothesis: str | None = None
    files_inspected: list[str] = []
    files_modified: list[str] = []
    diff: str = ""
    tool_calls: int = 0
    steps: int = 0
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        max_steps: int = 25,
        on_event: EventSink = ignore_events,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.max_steps = max_steps
        self.emit = on_event
        self.cancel_event = cancel_event or threading.Event()

    def run(self, bug_report: str, context: ToolContext) -> AgentRunResult:
        started = time.perf_counter()
        messages: list[Message] = [UserMessage(text=initial_prompt(context.workspace.name, bug_report))]
        tool_specs = self.registry.specs()
        tool_calls = steps = input_tokens = output_tokens = 0
        error: str | None = None
        cancelled = False

        self.emit(AgentEvent(type="status", message="Analyzing bug report"))

        while steps < self.max_steps:
            if self.cancel_event.is_set():
                cancelled = True
                break
            steps += 1
            try:
                turn = self.provider.tool_call(SYSTEM_PROMPT, messages, tool_specs)
            except LLMError as exc:
                error = str(exc)
                break
            input_tokens += turn.input_tokens
            output_tokens += turn.output_tokens
            messages.append(turn.message)

            if turn.stop_reason == "tool_use":
                results = [self._run_tool(call.id, call.name, call.arguments, context) for call in turn.message.tool_calls]
                tool_calls += len(results)
                # Every tool_use must get a matching result, sent back together in one message.
                messages.append(ToolResultsMessage(results=results))
                if context.final_report is not None:
                    break
                continue

            if turn.stop_reason == "refusal":
                error = "The model declined to continue with this request"
            elif turn.stop_reason == "max_tokens":
                error = "The model response was cut off (max tokens reached)"
            # "end_turn": the model stopped without calling finish - use what we have.
            break
        else:
            error = f"Stopped after reaching the step limit ({self.max_steps})"

        result = self._build_result(context, error, cancelled)
        result.tool_calls, result.steps = tool_calls, steps
        result.input_tokens, result.output_tokens = input_tokens, output_tokens
        result.duration_ms = int((time.perf_counter() - started) * 1000)

        if result.status == "failed":
            self.emit(AgentEvent(type="error", message=result.error or "Agent failed", success=False))
        self.emit(AgentEvent(type="done", message=self._done_message(result), success=result.status != "failed"))
        logger.info(
            "agent_run_finished",
            extra={"fields": {"status": result.status, "tool_calls": tool_calls, "steps": steps,
                              "duration_ms": result.duration_ms, "error": result.error}},
        )
        return result

    def _run_tool(self, call_id: str, name: str, arguments: dict, context: ToolContext) -> ToolResult:
        summary = self.registry.summarize(name, arguments)
        self.emit(AgentEvent(type="tool_started", message=summary, tool=name, call_id=call_id))
        outcome = self.registry.execute(name, arguments, context)
        self.emit(
            AgentEvent(
                type="tool_finished",
                message=outcome.note or summary,
                tool=name,
                call_id=call_id,
                success=not outcome.is_error,
                detail=outcome.content[:2_000],
                duration_ms=outcome.duration_ms,
            )
        )
        if name == "record_hypothesis" and not outcome.is_error and context.hypothesis:
            self.emit(AgentEvent(type="hypothesis", message=context.hypothesis))
        return ToolResult(tool_call_id=call_id, content=outcome.content, is_error=outcome.is_error)

    @staticmethod
    def _build_result(context: ToolContext, error: str | None, cancelled: bool) -> AgentRunResult:
        report = context.final_report if isinstance(context.final_report, FinishArgs) else None
        has_changes = not context.changeset.is_empty()
        if cancelled:
            status: RunStatus = "cancelled"
        elif has_changes:
            status = "proposed"  # even after an error, a staged patch is worth showing
        elif error:
            status = "failed"
        else:
            status = "no_changes"
        return AgentRunResult(
            status=status,
            summary=report.summary if report else "",
            root_cause=report.root_cause if report else "",
            fix_explanation=report.fix_explanation if report else "",
            hypothesis=context.hypothesis,
            files_inspected=list(context.files_inspected),
            files_modified=[c.path for c in context.changeset.changes],
            diff=context.changeset.diff(),
            error=error,
        )

    @staticmethod
    def _done_message(result: AgentRunResult) -> str:
        if result.status == "proposed":
            count = len(result.files_modified)
            return f"Patch ready for review ({count} file{'s' if count != 1 else ''})"
        if result.status == "no_changes":
            return "Finished without proposing changes"
        if result.status == "cancelled":
            return "Cancelled"
        return "Analysis failed"

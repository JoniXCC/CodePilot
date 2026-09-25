"""Tool registry: maps a tool name to its argument schema and implementation.

Each tool's arguments are a Pydantic model. That one model gives us both the
JSON schema we send to the LLM *and* validation of whatever the LLM sends back,
so a malformed tool call becomes a clear error message instead of a crash.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.base import ToolSpec
from app.tools.changeset import ChangeSet
from app.tools.errors import ToolError
from app.tools.workspace import Workspace

logger = logging.getLogger("codepilot.tools")

MAX_RESULT_CHARS = 12_000


@dataclass
class ToolContext:
    """Per-session state the tools operate on."""

    workspace: Workspace
    changeset: ChangeSet
    command_timeout: int = 120
    files_inspected: list[str] = field(default_factory=list)
    hypothesis: str | None = None
    final_report: BaseModel | None = None

    def mark_inspected(self, path: str) -> None:
        if path not in self.files_inspected:
            self.files_inspected.append(path)


@dataclass
class ToolOutput:
    content: str  # what the LLM sees
    note: str = ""  # short human-readable result for the timeline, e.g. "3 matches in cart.js"
    warning: bool = False  # the tool worked, but the result is bad news (e.g. tests failing)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[ToolContext, Any], ToolOutput]
    summarize: Callable[[Any], str]  # "Reading src/cart.js" - shown before the tool runs

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description, input_schema=self.args_model.model_json_schema()
        )


class ToolOutcome(BaseModel):
    content: str
    is_error: bool
    summary: str
    note: str = ""
    warning: bool = False
    duration_ms: int


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    def summarize(self, name: str, raw_args: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Unknown tool {name}"
        try:
            return tool.summarize(tool.args_model.model_validate(raw_args))
        except ValidationError:
            return f"Calling {name}"

    def execute(self, name: str, raw_args: dict[str, Any], context: ToolContext) -> ToolOutcome:
        started = time.perf_counter()
        summary = self.summarize(name, raw_args)
        error: str | None = None
        output = ToolOutput(content="")

        tool = self._tools.get(name)
        if tool is None:
            error = f"Unknown tool '{name}'. Available tools: {', '.join(self._tools)}"
        else:
            try:
                output = tool.handler(context, tool.args_model.model_validate(raw_args))
            except ValidationError as exc:
                error = f"Invalid arguments for {name}: {exc.errors(include_url=False)}"
            except ToolError as exc:
                error = str(exc)
            except Exception:  # never let one tool crash the whole session
                logger.exception("Unexpected tool failure", extra={"fields": {"tool": name}})
                error = f"{name} failed with an internal error"

        duration_ms = int((time.perf_counter() - started) * 1000)
        # Log metadata only - never file contents or command output, which may be sensitive.
        logger.info(
            "tool_call",
            extra={
                "fields": {
                    "tool": name,
                    "duration_ms": duration_ms,
                    "success": error is None,
                    "error": error,
                    "arg_keys": sorted(raw_args),
                    "path": raw_args.get("path") if isinstance(raw_args.get("path"), str) else None,
                }
            },
        )
        content = error if error is not None else output.content
        if len(content) > MAX_RESULT_CHARS:
            content = content[:MAX_RESULT_CHARS] + "\n... [output truncated]"
        return ToolOutcome(
            content=content,
            is_error=error is not None,
            summary=summary,
            note=error or output.note,
            warning=error is None and output.warning,
            duration_ms=duration_ms,
        )

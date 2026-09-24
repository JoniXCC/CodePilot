import threading
from pathlib import Path

from app.agent.events import AgentEvent
from app.agent.loop import Agent
from app.agent.registry import ToolContext
from app.agent.toolset import build_registry
from app.llm.base import LLMError, LLMProvider, LLMTurn, Message, ToolResultsMessage, ToolSpec
from app.llm.scripted_provider import ScriptedProvider, ScriptedStep
from app.tools.changeset import ChangeSet
from app.tools.workspace import Workspace

BUGGY = "  return items.reduce((a, b) => a + b.price);"
FIXED = "  return items.reduce((a, b) => a + b.price, 0);"


def make_context(workspace: Workspace) -> ToolContext:
    return ToolContext(workspace=workspace, changeset=ChangeSet(workspace))


def run(steps: list[ScriptedStep], workspace: Workspace, **agent_kwargs) -> tuple:
    events: list[AgentEvent] = []
    provider = ScriptedProvider(steps)
    context = make_context(workspace)
    agent = Agent(provider, build_registry(), on_event=events.append, **agent_kwargs)
    result = agent.run("Cart total is NaN when the cart is empty", context)
    return result, events, provider


def last_tool_results(provider: ScriptedProvider) -> ToolResultsMessage:
    message = provider.seen_messages[-1][-1]
    assert isinstance(message, ToolResultsMessage)
    return message


HAPPY_PATH = [
    ScriptedStep(tool="list_files"),
    ScriptedStep(tool="search_code", arguments={"query": "reduce"}),
    ScriptedStep(tool="read_file", arguments={"path": "src/cart.js"}),
    ScriptedStep(tool="record_hypothesis", arguments={"hypothesis": "reduce() has no initial value in total()"}),
    ScriptedStep(tool="replace_code", arguments={"path": "src/cart.js", "old_code": BUGGY, "new_code": FIXED}),
    ScriptedStep(
        tool="finish",
        arguments={
            "summary": "Fix NaN total for empty cart",
            "root_cause": "total() calls reduce without an initial value",
            "fix_explanation": "Pass 0 as the initial accumulator",
        },
    ),
]


def test_happy_path_produces_proposal_without_touching_disk(workspace: Workspace, repo: Path) -> None:
    before = (repo / "src" / "cart.js").read_bytes()
    result, events, _ = run(HAPPY_PATH, workspace)

    assert result.status == "proposed"
    assert result.summary == "Fix NaN total for empty cart"
    assert result.hypothesis == "reduce() has no initial value in total()"
    assert result.files_inspected == ["src/cart.js"]
    assert result.files_modified == ["src/cart.js"]
    assert f"+{FIXED}" in result.diff
    assert result.tool_calls == 6
    assert result.error is None
    assert (repo / "src" / "cart.js").read_bytes() == before


def test_happy_path_event_timeline(workspace: Workspace) -> None:
    _, events, _ = run(HAPPY_PATH, workspace)
    types = [e.type for e in events]
    assert types[0] == "status"
    assert types[-1] == "done"
    assert types.count("tool_started") == types.count("tool_finished") == 6
    assert "hypothesis" in types
    search_done = next(e for e in events if e.type == "tool_finished" and e.tool == "search_code")
    assert search_done.message == "Found 1 match in src/cart.js"
    started = [e for e in events if e.type == "tool_started"]
    assert [e.message for e in started][:3] == [
        "Listing repository files",
        "Searching code for “reduce”",
        "Reading src/cart.js",
    ]


def test_blocked_command_is_reported_to_model_and_run_continues(workspace: Workspace) -> None:
    result, events, provider = run([ScriptedStep(tool="run_command", arguments={"command": "rm -rf src"})], workspace)
    [tool_result] = last_tool_results(provider).results
    assert tool_result.is_error
    assert "not in whitelist" in tool_result.content
    assert result.status == "no_changes"
    assert any(e.type == "tool_finished" and e.success is False for e in events)


def test_path_traversal_via_agent_is_rejected(workspace: Workspace) -> None:
    _, _, provider = run([ScriptedStep(tool="read_file", arguments={"path": "../../etc/passwd"})], workspace)
    [tool_result] = last_tool_results(provider).results
    assert tool_result.is_error and "escapes the repository" in tool_result.content


def test_secret_file_contents_never_reach_events_or_model(workspace: Workspace) -> None:
    _, events, provider = run([ScriptedStep(tool="read_file", arguments={"path": ".env"})], workspace)
    [tool_result] = last_tool_results(provider).results
    assert tool_result.is_error
    everything = tool_result.content + "".join(f"{e.message}{e.detail}" for e in events)
    assert "supersecret" not in everything


def test_invalid_arguments_become_error_result(workspace: Workspace) -> None:
    _, _, provider = run([ScriptedStep(tool="read_file", arguments={"start_line": 1})], workspace)
    [tool_result] = last_tool_results(provider).results
    assert tool_result.is_error and "Invalid arguments for read_file" in tool_result.content


def test_unknown_tool(workspace: Workspace) -> None:
    _, _, provider = run([ScriptedStep(tool="delete_everything")], workspace)
    [tool_result] = last_tool_results(provider).results
    assert tool_result.is_error and "Unknown tool" in tool_result.content


def test_step_limit(workspace: Workspace) -> None:
    steps = [ScriptedStep(tool="git_status")] * 10
    result, _, _ = run(steps, workspace, max_steps=3)
    assert result.status == "failed"
    assert "step limit" in (result.error or "")
    assert result.tool_calls == 3


def test_step_limit_still_returns_staged_patch(workspace: Workspace) -> None:
    steps = [HAPPY_PATH[4], ScriptedStep(tool="git_status"), ScriptedStep(tool="git_status")]
    result, _, _ = run(steps, workspace, max_steps=2)
    assert result.status == "proposed"
    assert result.error and "step limit" in result.error


def test_cancellation(workspace: Workspace) -> None:
    cancel = threading.Event()
    cancel.set()
    result, events, _ = run(HAPPY_PATH, workspace, cancel_event=cancel)
    assert result.status == "cancelled"
    assert result.tool_calls == 0


def test_model_stopping_without_finish(workspace: Workspace) -> None:
    result, _, _ = run([ScriptedStep(tool="list_files")], workspace)
    assert result.status == "no_changes"
    assert result.error is None


class FailingProvider(LLMProvider):
    def generate(self, system: str, prompt: str) -> str:
        raise LLMError("offline")

    def tool_call(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> LLMTurn:
        raise LLMError("Could not connect to the Anthropic API")


def test_provider_error_fails_cleanly(workspace: Workspace) -> None:
    events: list[AgentEvent] = []
    result = Agent(FailingProvider(), build_registry(), on_event=events.append).run("bug", make_context(workspace))
    assert result.status == "failed"
    assert result.error == "Could not connect to the Anthropic API"
    assert [e.type for e in events][-2:] == ["error", "done"]


def test_tool_schemas_are_json_objects() -> None:
    for spec in build_registry().specs():
        assert spec.input_schema["type"] == "object", spec.name
        assert spec.description

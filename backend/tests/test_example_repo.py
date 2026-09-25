"""End-to-end check against the real demo project: real tools, real npm test, scripted "LLM"."""

import shutil
from pathlib import Path

import pytest

from app.agent.events import AgentEvent
from app.agent.loop import Agent
from app.agent.registry import ToolContext
from app.agent.toolset import build_registry
from app.config import REPO_ROOT
from app.llm.scripted_provider import ScriptedProvider, ScriptedStep
from app.services.repo_copies import create_git_copy
from app.tools import git, shell
from app.tools.changeset import ChangeSet
from app.tools.workspace import Workspace

pytestmark = pytest.mark.skipif(shutil.which("npm") is None, reason="Node.js/npm not installed")

BUG_LINE = "  return tier?.rate;"
FIX_LINE = "  return tier?.rate ?? 0;"


@pytest.fixture
def cart_repo(tmp_path: Path) -> Workspace:
    return Workspace(create_git_copy(REPO_ROOT / "examples" / "shopping-cart", tmp_path / "shopping-cart"))


def test_example_bug_reproduces(cart_repo: Workspace) -> None:
    result = shell.run_tests(cart_repo)
    assert result.command == "npm test"
    assert not result.succeeded
    assert "empty cart total is zero" in result.stdout
    assert "NaN" in result.stdout


def test_scripted_agent_fixes_example(cart_repo: Workspace) -> None:
    steps = [
        ScriptedStep(tool="search_code", arguments={"query": "calculateTotal"}),
        ScriptedStep(tool="read_file", arguments={"path": "src/cart.js"}),
        ScriptedStep(tool="run_tests"),
        ScriptedStep(tool="record_hypothesis", arguments={"hypothesis": "getBulkDiscountRate returns undefined for 0 items"}),
        ScriptedStep(tool="replace_code", arguments={"path": "src/cart.js", "old_code": BUG_LINE, "new_code": FIX_LINE}),
        ScriptedStep(tool="finish", arguments={"summary": "Default bulk discount rate to 0",
                                               "root_cause": "No tier matches 0 items", "fix_explanation": "?? 0"}),
    ]
    context = ToolContext(workspace=cart_repo, changeset=ChangeSet(cart_repo))
    events: list[AgentEvent] = []
    result = Agent(ScriptedProvider(steps), build_registry(), on_event=events.append).run("Empty cart total is NaN", context)

    assert result.status == "proposed"
    # Failing tests before the fix: the tool worked (success) but the result is flagged as a warning.
    test_run = next(e for e in events if e.type == "tool_finished" and e.tool == "run_tests")
    assert test_run.success is True and test_run.warning is True
    assert test_run.message == "Tests failed (exit 1)"
    assert result.files_modified == ["src/cart.js"]
    assert git.get_git_diff(cart_repo) == ""  # nothing written before approval

    context.changeset.apply()  # the user clicked "Approve"
    after = shell.run_tests(cart_repo)
    assert after.succeeded, after.stdout
    diff = git.get_git_diff(cart_repo)
    assert f"-{BUG_LINE}" in diff and f"+{FIX_LINE}" in diff

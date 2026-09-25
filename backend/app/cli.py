"""Run the agent from the terminal - handy for debugging without the web UI.

    python -m app.cli <repo-path> "<bug report>" [--apply]
"""

import argparse
import sys

from app.agent.events import AgentEvent
from app.agent.loop import Agent
from app.agent.registry import ToolContext
from app.agent.toolset import build_registry
from app.config import get_settings
from app.llm.factory import create_provider
from app.logging_config import configure_logging
from app.tools import git, shell
from app.tools.changeset import ChangeSet
from app.tools.workspace import Workspace

ICONS = {"tool_started": "→", "hypothesis": "★", "status": "…", "error": "✗"}


def print_event(event: AgentEvent) -> None:
    if event.type == "tool_finished":
        icon = "✓" if event.success else "✗"
        print(f"  {icon} {event.message}  ({event.duration_ms} ms)")
    elif event.type == "done":
        print(f"\n{event.message}")
    else:
        print(f"{ICONS.get(event.type, '-')} {event.message}")
    sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CodePilot agent on a repository")
    parser.add_argument("repo")
    parser.add_argument("bug_report")
    parser.add_argument("--apply", action="store_true", help="apply the patch and run the tests")
    args = parser.parse_args()
    # Windows consoles default to a legacy code page that can't print the timeline symbols.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = get_settings()
    configure_logging("WARNING")  # keep the terminal readable; JSON logs are for the server
    workspace = Workspace(args.repo)

    status = git.git_status(workspace)
    if status.is_repo and not status.is_clean:
        print(f"Warning: {len(status.files)} uncommitted change(s) in the repository")

    context = ToolContext(workspace=workspace, changeset=ChangeSet(workspace), command_timeout=settings.command_timeout_seconds)
    agent = Agent(create_provider(settings), build_registry(), settings.agent_max_steps, on_event=print_event)
    result = agent.run(args.bug_report, context)

    print(f"\nStatus: {result.status}   tool calls: {result.tool_calls}   time: {result.duration_ms / 1000:.1f}s   "
          f"tokens: {result.input_tokens} in / {result.output_tokens} out")
    if result.error:
        print(f"Error: {result.error}")
    for label, value in (("Summary", result.summary), ("Root cause", result.root_cause), ("Fix", result.fix_explanation)):
        if value:
            print(f"{label}: {value}")
    print(f"Files inspected: {', '.join(result.files_inspected) or '-'}")
    if result.diff:
        print("\nProposed diff:\n" + result.diff)

    if args.apply and result.status == "proposed":
        context.changeset.apply()
        tests = shell.run_tests(workspace, settings.command_timeout_seconds)
        print(f"Applied. Tests {'PASSED' if tests.succeeded else 'FAILED'} ({tests.command})")
        print((tests.stdout + tests.stderr)[-1500:])


if __name__ == "__main__":
    main()

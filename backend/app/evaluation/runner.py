"""Runs the agent against each evaluation case and scores the outcome.

For every case:
  1. copy the case repository into a fresh git repo
  2. run the tests once to confirm the bug reproduces
  3. run the agent (it only stages changes, as in the real app)
  4. score which file/lines it changed
  5. apply the patch, restore protected files (tests), run the tests again
"""

import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from app.agent.loop import Agent
from app.agent.registry import ToolContext
from app.agent.toolset import build_registry
from app.evaluation.cases import EvalCase
from app.evaluation.metrics import CaseResult, changed_line_ranges, touches_expected_lines
from app.llm.base import LLMProvider
from app.llm.scripted_provider import ScriptedProvider, ScriptedStep
from app.services.repo_copies import create_git_copy
from app.tools import shell
from app.tools.changeset import ChangeSet
from app.tools.errors import ToolError
from app.tools.workspace import Workspace

ProviderFactory = Callable[[EvalCase], LLMProvider]


def reference_provider(case: EvalCase) -> LLMProvider:
    """An 'oracle' that applies the known fix. Validates the harness and that every case is solvable."""
    steps = [
        ScriptedStep(tool="read_file", arguments={"path": case.expected_file}),
        ScriptedStep(tool="run_tests"),
        ScriptedStep(tool="record_hypothesis", arguments={"hypothesis": f"Bug is in {case.expected_file}"}),
        *[
            ScriptedStep(tool="replace_code", arguments={"path": e.path, "old_code": e.old, "new_code": e.new})
            for e in case.reference_fix
        ],
        ScriptedStep(tool="finish", arguments={"summary": "Apply reference fix", "root_cause": case.expected_file,
                                               "fix_explanation": "Known-good reference fix"}),
    ]
    return ScriptedProvider(steps)


def _tests_pass(case: EvalCase, workspace: Workspace, timeout: int) -> bool:
    result = shell.run_command(case.test_command, workspace, timeout)
    # Exit code 0 alone isn't enough: the expected test must actually have run.
    return result.succeeded and case.expected_test in (result.stdout + result.stderr)


def _restore_protected(case: EvalCase, repo: Path) -> None:
    if case.protected_paths:
        subprocess.run(["git", "checkout", "HEAD", "--", *case.protected_paths], cwd=repo, check=True, capture_output=True)


def run_case(case: EvalCase, provider_factory: ProviderFactory, workdir: Path, max_steps: int = 25, timeout: int = 120) -> CaseResult:
    started = time.perf_counter()
    base = {"case_id": case.id, "bug_description": case.bug_description, "expected_file": case.expected_file}
    try:
        repo = create_git_copy(case.source_dir, workdir / case.id)
        workspace = Workspace(repo)
        tests_failed_before = not _tests_pass(case, workspace, timeout)

        context = ToolContext(workspace=workspace, changeset=ChangeSet(workspace), command_timeout=timeout)
        run = Agent(provider_factory(case), build_registry(), max_steps=max_steps).run(case.bug_description, context)

        changes = {c.path: c for c in context.changeset.changes}
        expected_change = changes.get(case.expected_file)
        mentioned = case.expected_file in f"{run.root_cause} {run.hypothesis or ''}"
        found_file = expected_change is not None or (not changes and mentioned)
        found_location = expected_change is not None and touches_expected_lines(
            changed_line_ranges(expected_change.original, expected_change.proposed), case.expected_lines
        )
        touched_protected = any(case.is_protected(path) for path in changes)

        patch_applied = False
        tests_passed = False
        if changes:
            try:
                context.changeset.apply()
                patch_applied = True
            except ToolError:
                pass
        if patch_applied:
            _restore_protected(case, repo)  # a "fix" that edits the tests doesn't count
            tests_passed = _tests_pass(case, workspace, timeout)

        return CaseResult(
            **base,
            status=run.status,
            tests_failed_before=tests_failed_before,
            found_correct_file=found_file,
            found_bug_location=found_location,
            patch_applied=patch_applied,
            tests_passed=tests_passed,
            touched_protected_files=touched_protected,
            successful_fix=tests_failed_before and tests_passed and not touched_protected,
            tool_calls=run.tool_calls,
            duration_ms=run.duration_ms,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            files_modified=run.files_modified,
            error=run.error,
        )
    except Exception as exc:  # one broken case must not abort the whole evaluation
        return CaseResult(
            **base,
            status="error",
            tests_failed_before=False,
            found_correct_file=False,
            found_bug_location=False,
            patch_applied=False,
            tests_passed=False,
            touched_protected_files=False,
            successful_fix=False,
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=f"{type(exc).__name__}: {exc}",
        )

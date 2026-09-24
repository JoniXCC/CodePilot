"""The concrete tools the agent can call, wired to the sandboxed implementations in app.tools."""

from pydantic import BaseModel, Field

from app.agent.registry import Tool, ToolContext, ToolOutput, ToolRegistry
from app.tools import files, git, search, shell
from app.tools.changeset import unified_diff
from app.tools.errors import ToolError


# --- argument models (these become the JSON schemas the LLM sees) -------------------


class ListFilesArgs(BaseModel):
    path: str = Field(".", description="Directory relative to the repository root")


class ReadFileArgs(BaseModel):
    path: str = Field(description="File path relative to the repository root")
    start_line: int = Field(1, ge=1, description="First line to return (1-based)")
    end_line: int | None = Field(None, ge=1, description="Last line to return (inclusive)")


class SearchCodeArgs(BaseModel):
    query: str = Field(description="Text (or regex when is_regex=true) to search for")
    file_glob: str | None = Field(None, description="Optional filter such as '*.js' or 'src/*'")
    is_regex: bool = False


class WriteFileArgs(BaseModel):
    path: str
    content: str = Field(description="Complete new file content")


class ReplaceCodeArgs(BaseModel):
    path: str
    old_code: str = Field(description="Exact existing code to replace; must occur exactly once")
    new_code: str = Field(description="Replacement code")


class RunCommandArgs(BaseModel):
    command: str = Field(description="A whitelisted command, e.g. 'npm test' or 'python -m pytest -q'")


class NoArgs(BaseModel):
    pass


class HypothesisArgs(BaseModel):
    hypothesis: str = Field(description="One or two sentences: the suspected root cause and where it is")


class FinishArgs(BaseModel):
    summary: str = Field(description="One-sentence summary of the fix, suitable as a commit title")
    root_cause: str = Field(description="What caused the bug, referencing file and function")
    fix_explanation: str = Field(description="What the proposed change does and why it fixes the bug")


# --- handlers ------------------------------------------------------------------------


def _format_command(result: shell.CommandResult) -> str:
    status = "TIMED OUT" if result.timed_out else f"exit code {result.exit_code}"
    parts = [f"$ {result.command}  ({status}, {result.duration_ms} ms)"]
    if result.stdout.strip():
        parts.append(f"stdout:\n{result.stdout.strip()}")
    if result.stderr.strip():
        parts.append(f"stderr:\n{result.stderr.strip()}")
    return "\n".join(parts)


def _list_files(ctx: ToolContext, args: ListFilesArgs) -> ToolOutput:
    listed = files.list_files(ctx.workspace, args.path)
    return ToolOutput("\n".join(listed) or "(no files)", f"{len(listed)} files")


def _read_file(ctx: ToolContext, args: ReadFileArgs) -> ToolOutput:
    content = ctx.changeset.current_content(args.path)  # includes staged edits
    if content is None:
        raise ToolError(f"File not found: {args.path}")
    ctx.mark_inspected(ctx.workspace.relative(ctx.workspace.resolve(args.path)))
    numbered = files.number_lines(content, args.start_line, args.end_line)
    return ToolOutput(numbered or "(empty file)", f"{len(content.splitlines())} lines")


def _search_code(ctx: ToolContext, args: SearchCodeArgs) -> ToolOutput:
    matches = search.search_code(ctx.workspace, args.query, args.file_glob, args.is_regex)
    if not matches:
        return ToolOutput("No matches.", "No matches")
    found_in = sorted({m.path for m in matches})
    note = f"Found {len(matches)} match{'es' if len(matches) != 1 else ''} in {', '.join(found_in[:3])}"
    if len(found_in) > 3:
        note += f" (+{len(found_in) - 3} more)"
    return ToolOutput("\n".join(f"{m.path}:{m.line}: {m.text}" for m in matches), note)


def _staged_output(path: str, original: str | None, proposed: str) -> ToolOutput:
    diff = unified_diff(path, original, proposed)
    return ToolOutput(
        f"Staged change to {path} (NOT applied yet - the user must approve it):\n{diff}",
        f"Patch staged for {path}",
    )


def _write_file(ctx: ToolContext, args: WriteFileArgs) -> ToolOutput:
    before = ctx.changeset.current_content(args.path)
    change = ctx.changeset.write_file(args.path, args.content)
    return _staged_output(change.path, before, change.proposed)


def _replace_code(ctx: ToolContext, args: ReplaceCodeArgs) -> ToolOutput:
    before = ctx.changeset.current_content(args.path)
    change = ctx.changeset.replace_code(args.path, args.old_code, args.new_code)
    return _staged_output(change.path, before, change.proposed)


def _command_note(result: shell.CommandResult) -> str:
    return "Passed" if result.succeeded else ("Timed out" if result.timed_out else f"Failed (exit {result.exit_code})")


def _run_command(ctx: ToolContext, args: RunCommandArgs) -> ToolOutput:
    result = shell.run_command(args.command, ctx.workspace, ctx.command_timeout)
    return ToolOutput(_format_command(result), _command_note(result))


def _run_tests(ctx: ToolContext, args: NoArgs) -> ToolOutput:
    result = shell.run_tests(ctx.workspace, ctx.command_timeout)
    note = "Tests passed" if result.succeeded else _command_note(result).replace("Failed", "Tests failed")
    reminder = "\n(Note: tests ran against files on disk; staged changes are not applied yet.)"
    return ToolOutput(_format_command(result) + (reminder if not ctx.changeset.is_empty() else ""), note)


def _get_git_diff(ctx: ToolContext, args: NoArgs) -> ToolOutput:
    sections: list[str] = []
    try:
        working_tree = git.get_git_diff(ctx.workspace)
        sections.append(f"# Uncommitted changes on disk\n{working_tree or '(none)'}")
    except ToolError as exc:
        sections.append(f"# Git diff unavailable: {exc}")
    sections.append(f"# Proposed changes (staged by you, not yet applied)\n{ctx.changeset.diff() or '(none)'}")
    return ToolOutput("\n\n".join(sections), f"{len(ctx.changeset.changes)} file(s) with proposed changes")


def _git_status(ctx: ToolContext, args: NoArgs) -> ToolOutput:
    status = git.git_status(ctx.workspace)
    if not status.is_repo:
        return ToolOutput("Not a git repository.", "Not a git repository")
    lines = [f"branch: {status.branch}"] + [f"{f.code} {f.path}" for f in status.files]
    note = "Working tree clean" if status.is_clean else f"{len(status.files)} uncommitted change(s)"
    return ToolOutput("\n".join(lines), note)


def _record_hypothesis(ctx: ToolContext, args: HypothesisArgs) -> ToolOutput:
    ctx.hypothesis = args.hypothesis
    return ToolOutput("Hypothesis recorded.", args.hypothesis)


def _finish(ctx: ToolContext, args: FinishArgs) -> ToolOutput:
    # Finishing with no staged changes is allowed (e.g. the bug could not be located).
    ctx.final_report = args
    return ToolOutput("Report submitted.", args.summary)


def build_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool("list_files", "List files in the repository (recursively). Skips dependencies and secret files.",
                 ListFilesArgs, _list_files, lambda a: f"Listing files in {a.path}" if a.path != "." else "Listing repository files"),
            Tool("read_file", "Read a file with line numbers. Shows your staged edits if you made any.",
                 ReadFileArgs, _read_file, lambda a: f"Reading {a.path}"),
            Tool("search_code", "Search all text files in the repository for a string or regex.",
                 SearchCodeArgs, _search_code, lambda a: f"Searching code for “{a.query}”"),
            Tool("write_file", "Propose the full new content of a file (creates it if missing). Staged for user review, not written.",
                 WriteFileArgs, _write_file, lambda a: f"Preparing new version of {a.path}"),
            Tool("replace_code", "Propose replacing one exact snippet in a file. Preferred for small fixes. Staged for user review, not written.",
                 ReplaceCodeArgs, _replace_code, lambda a: f"Creating patch for {a.path}"),
            Tool("run_command", "Run a whitelisted command in the repository: " + ", ".join(" ".join(r.prefix) for r in shell.ALLOWED_COMMANDS) + ".",
                 RunCommandArgs, _run_command, lambda a: f"Running `{a.command}`"),
            Tool("run_tests", "Detect and run the project's test suite against the files currently on disk.",
                 NoArgs, _run_tests, lambda a: "Running tests"),
            Tool("get_git_diff", "Show uncommitted changes on disk plus your proposed (staged) changes.",
                 NoArgs, _get_git_diff, lambda a: "Reviewing the diff"),
            Tool("git_status", "Show the current branch and uncommitted files.",
                 NoArgs, _git_status, lambda a: "Checking git status"),
            Tool("record_hypothesis", "Record your current best hypothesis about the root cause. The user sees this.",
                 HypothesisArgs, _record_hypothesis, lambda a: "Possible bug identified"),
            Tool("finish", "Call exactly once when done, after staging the fix (or if you could not find one).",
                 FinishArgs, _finish, lambda a: "Summarising the fix"),
        ]
    )

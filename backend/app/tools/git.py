"""Git integration: status, diff and (user-triggered) commit.

These functions build fixed argument lists themselves - they are not driven by
free-form strings from the LLM, so they don't go through the shell whitelist.
"""

import subprocess

from pydantic import BaseModel

from app.tools.changeset import unified_diff
from app.tools.errors import ToolError
from app.tools.files import read_text
from app.tools.shell import sanitized_env
from app.tools.workspace import Workspace


class GitFileStatus(BaseModel):
    path: str
    code: str  # two-letter porcelain code, e.g. " M", "??"


class GitStatus(BaseModel):
    is_repo: bool
    branch: str | None = None
    files: list[GitFileStatus] = []

    @property
    def is_clean(self) -> bool:
        return not self.files


def _git(workspace: Workspace, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-c", "core.quotepath=off", "--no-pager", *args],
        cwd=workspace.root,
        env=sanitized_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        stdin=subprocess.DEVNULL,
    )
    if check and completed.returncode != 0:
        raise ToolError(f"git {args[0]} failed: {completed.stderr.strip()}")
    return completed


def is_git_repo(workspace: Workspace) -> bool:
    result = _git(workspace, "rev-parse", "--is-inside-work-tree", check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_status(workspace: Workspace) -> GitStatus:
    if not is_git_repo(workspace):
        return GitStatus(is_repo=False)
    output = _git(workspace, "status", "--porcelain=v1", "--branch", "--untracked-files=all").stdout
    branch: str | None = None
    files: list[GitFileStatus] = []
    for line in output.splitlines():
        if line.startswith("## "):
            branch = line[3:].split("...")[0]
        elif line:
            files.append(GitFileStatus(code=line[:2], path=line[3:]))
    return GitStatus(is_repo=True, branch=branch, files=files)


def get_git_diff(workspace: Workspace) -> str:
    """Unified diff of the working tree vs HEAD, including brand-new (untracked) files."""
    if not is_git_repo(workspace):
        raise ToolError("Not a git repository")
    has_head = _git(workspace, "rev-parse", "--verify", "HEAD", check=False).returncode == 0
    diff = _git(workspace, "diff", "HEAD" if has_head else "--cached").stdout

    # `git diff` ignores untracked files, so render those ourselves.
    for entry in git_status(workspace).files:
        if entry.code == "??":
            try:
                content = read_text(workspace.resolve(entry.path))
            except ToolError:
                continue  # secret or binary file - never included in a diff
            diff += unified_diff(entry.path, None, content)
    return diff


def commit_changes(workspace: Workspace, paths: list[str], message: str) -> str:
    """Stage exactly `paths` and commit. Only called when the user clicks "Create commit"."""
    if not paths:
        raise ToolError("Nothing to commit")
    safe_paths = [workspace.relative(workspace.resolve(p)) for p in paths]
    _git(workspace, "add", "--", *safe_paths)
    _git(workspace, "commit", "-m", message, "--", *safe_paths)
    return _git(workspace, "rev-parse", "--short", "HEAD").stdout.strip()

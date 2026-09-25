"""Create throwaway git repositories from template folders (demo projects, eval cases)."""

import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

IGNORE = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".pytest_cache")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _clear_readonly_and_retry(func: Any, path: str, _exc: BaseException) -> None:
    # Git marks object files read-only; on Windows that makes rmtree fail unless we clear the flag.
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, onexc=_clear_readonly_and_retry)


def create_git_copy(source: Path, destination: Path, message: str = "Initial commit") -> Path:
    """Copy `source` to `destination` (replacing it) and commit it as a fresh git repository."""
    if destination.exists():
        remove_tree(destination)
    shutil.copytree(source, destination, ignore=IGNORE)
    _git(destination, "init", "-q", "-b", "main")
    # Local identity so this works on machines without a global git config.
    _git(destination, "config", "user.name", "CodePilot Demo")
    _git(destination, "config", "user.email", "demo@codepilot.local")
    _git(destination, "config", "core.autocrlf", "false")
    _git(destination, "add", "-A")
    _git(destination, "commit", "-q", "-m", message)
    return destination

"""Discovering and opening the repositories CodePilot is allowed to work on."""

from pathlib import Path

from app.schemas.projects import ProjectInfo
from app.services.errors import NotFoundError
from app.tools import git
from app.tools.errors import PathSecurityError
from app.tools.shell import detect_test_command
from app.tools.workspace import Workspace


def open_project(projects_dir: Path, name: str) -> Workspace:
    """Only direct children of PROJECTS_DIR can be opened - never an arbitrary path from the browser."""
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise NotFoundError(f"Invalid project name: {name!r}")
    root = projects_dir.resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root or not candidate.is_dir():
        raise NotFoundError(f"Project not found: {name}")
    try:
        return Workspace(candidate)
    except PathSecurityError as exc:
        raise NotFoundError(str(exc)) from exc


def describe_project(workspace: Workspace) -> ProjectInfo:
    status = git.git_status(workspace)
    return ProjectInfo(
        name=workspace.name,
        is_git_repo=status.is_repo,
        branch=status.branch,
        uncommitted_files=[f.path for f in status.files],
        test_command=detect_test_command(workspace),
    )


def list_projects(projects_dir: Path) -> list[ProjectInfo]:
    if not projects_dir.is_dir():
        return []
    return [
        describe_project(Workspace(path))
        for path in sorted(projects_dir.iterdir())
        if path.is_dir() and not path.name.startswith(".")
    ]

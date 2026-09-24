"""Read-only file tools: list_files and read_file."""

import os
from pathlib import Path

from app.tools.errors import PathSecurityError, ToolError
from app.tools.workspace import IGNORED_DIRS, Workspace

MAX_FILE_BYTES = 200_000
MAX_LIST_ENTRIES = 500


def iter_files(workspace: Workspace, start: Path) -> list[Path]:
    """All files under `start`, skipping ignored directories and symlinks that leave the repo."""
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(start):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            try:
                workspace.resolve(workspace.relative_unresolved(path))
            except PathSecurityError:
                continue
            results.append(path)
    return results


def list_files(workspace: Workspace, path: str = ".") -> list[str]:
    directory = workspace.resolve(path)
    if not directory.is_dir():
        raise ToolError(f"Not a directory: {path}")
    files = iter_files(workspace, directory)
    listed = [workspace.relative(p) for p in files[:MAX_LIST_ENTRIES]]
    if len(files) > MAX_LIST_ENTRIES:
        listed.append(f"... ({len(files) - MAX_LIST_ENTRIES} more files not shown)")
    return listed


def read_text(path: Path) -> str:
    """Read a text file exactly as stored (newline='' keeps CRLF line endings intact)."""
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ToolError(f"File is too large to read ({path.stat().st_size} bytes)")
    raw = path.read_bytes()
    if b"\x00" in raw[:8000]:
        raise ToolError("File appears to be binary")
    return raw.decode("utf-8", errors="replace")


def number_lines(content: str, start_line: int = 1, end_line: int | None = None) -> str:
    lines = content.splitlines()
    end = len(lines) if end_line is None else min(end_line, len(lines))
    start = max(start_line, 1)
    return "\n".join(f"{n:>4} | {lines[n - 1]}" for n in range(start, end + 1))


def read_file(
    workspace: Workspace, path: str, start_line: int = 1, end_line: int | None = None
) -> str:
    """File contents with line numbers, so the LLM can refer to exact locations."""
    file_path = workspace.resolve(path)
    if not file_path.is_file():
        raise ToolError(f"File not found: {path}")
    return number_lines(read_text(file_path), start_line, end_line)

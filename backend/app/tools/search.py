"""search_code: a small, dependency-free grep over the workspace."""

import re
from fnmatch import fnmatch

from pydantic import BaseModel

from app.tools.errors import ToolError
from app.tools.files import MAX_FILE_BYTES, iter_files
from app.tools.workspace import Workspace

MAX_RESULTS = 50
MAX_LINE_CHARS = 200


class SearchMatch(BaseModel):
    path: str
    line: int
    text: str


def search_code(
    workspace: Workspace,
    query: str,
    file_glob: str | None = None,
    is_regex: bool = False,
    case_sensitive: bool = False,
) -> list[SearchMatch]:
    if not query:
        raise ToolError("Search query must not be empty")
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(query if is_regex else re.escape(query), flags)
    except re.error as exc:
        raise ToolError(f"Invalid regular expression: {exc}") from exc

    matches: list[SearchMatch] = []
    for path in iter_files(workspace, workspace.root):
        relative = workspace.relative(path)
        if file_glob and not (fnmatch(relative, file_glob) or fnmatch(path.name, file_glob)):
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        raw = path.read_bytes()
        if b"\x00" in raw[:8000]:
            continue  # binary file
        for number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            if pattern.search(line):
                matches.append(
                    SearchMatch(path=relative, line=number, text=line.strip()[:MAX_LINE_CHARS])
                )
                if len(matches) >= MAX_RESULTS:
                    return matches
    return matches

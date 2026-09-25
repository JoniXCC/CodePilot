"""Staged file edits.

The agent's write_file / replace_code tools never touch the disk. They record the
proposed new content here. The user reviews `diff()`, and only `apply()` - called
after explicit approval - writes anything.
"""

import difflib

from pydantic import BaseModel

from app.tools.errors import ToolError
from app.tools.files import read_text
from app.tools.workspace import Workspace


class FileChange(BaseModel):
    path: str
    original: str | None  # None means the file is new
    proposed: str

    @property
    def is_new(self) -> bool:
        return self.original is None


def unified_diff(path: str, original: str | None, proposed: str) -> str:
    before = (original or "").splitlines(keepends=True)
    after = proposed.splitlines(keepends=True)
    diff = difflib.unified_diff(
        before,
        after,
        fromfile="/dev/null" if original is None else f"a/{path}",
        tofile=f"b/{path}",
    )
    # Ensure every line ends with a newline so the diff text is well-formed.
    return "".join(line if line.endswith("\n") else line + "\n" for line in diff)


def match_line_endings(reference: str | None, text: str) -> str:
    """The LLM always writes '\\n'; keep a CRLF file CRLF so the diff isn't every line."""
    if reference and "\r\n" in reference and "\r\n" not in text:
        return text.replace("\n", "\r\n")
    return text


class ChangeSet:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self._changes: dict[str, FileChange] = {}

    @property
    def changes(self) -> list[FileChange]:
        return list(self._changes.values())

    def is_empty(self) -> bool:
        return not self._changes

    def _key(self, path: str) -> str:
        return self.workspace.relative(self.workspace.resolve(path))

    def current_content(self, path: str) -> str | None:
        """Content as the agent should see it: staged version if any, else what's on disk."""
        key = self._key(path)
        if key in self._changes:
            return self._changes[key].proposed
        file_path = self.workspace.resolve(path)
        return read_text(file_path) if file_path.is_file() else None

    def write_file(self, path: str, content: str) -> FileChange:
        key = self._key(path)
        if self.workspace.resolve(path).is_dir():
            raise ToolError(f"{path} is a directory")
        if key in self._changes:
            original = self._changes[key].original
        else:
            file_path = self.workspace.resolve(path)
            original = read_text(file_path) if file_path.is_file() else None
        proposed = match_line_endings(original, content)
        change = FileChange(path=key, original=original, proposed=proposed)
        self._changes[key] = change
        return change

    def replace_code(self, path: str, old: str, new: str) -> FileChange:
        """Replace exactly one occurrence of `old`. Ambiguous or missing matches are errors."""
        current = self.current_content(path)
        if current is None:
            raise ToolError(f"File not found: {path}")
        if not old:
            raise ToolError("old_code must not be empty")
        old, new = match_line_endings(current, old), match_line_endings(current, new)
        count = current.count(old)
        if count == 0:
            raise ToolError("old_code was not found in the file; read the file and copy it exactly")
        if count > 1:
            raise ToolError(f"old_code matches {count} places; include more surrounding lines")
        return self.write_file(path, current.replace(old, new, 1))

    @classmethod
    def restore(cls, workspace: Workspace, changes: list[FileChange]) -> "ChangeSet":
        """Rebuild a change set saved earlier (e.g. loaded from the database for approval)."""
        changeset = cls(workspace)
        for change in changes:
            changeset._changes[changeset._key(change.path)] = change
        return changeset

    def diff(self) -> str:
        return "".join(unified_diff(c.path, c.original, c.proposed) for c in self.changes)

    def apply(self) -> list[str]:
        """Write all staged changes to disk. Refuses if a file changed since it was staged."""
        for change in self.changes:
            file_path = self.workspace.resolve(change.path)
            on_disk = read_text(file_path) if file_path.is_file() else None
            if on_disk != change.original:
                raise ToolError(f"{change.path} was modified outside CodePilot; re-run analysis")
        written: list[str] = []
        for change in self.changes:
            file_path = self.workspace.resolve(change.path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(change.proposed.encode("utf-8"))
            written.append(change.path)
        return written

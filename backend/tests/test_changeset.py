from pathlib import Path

import pytest

from app.tools.changeset import ChangeSet
from app.tools.errors import PathSecurityError, ToolError
from app.tools.workspace import Workspace

ORIGINAL_LINE = "  return items.reduce((a, b) => a + b.price);"
FIXED_LINE = "  return items.reduce((a, b) => a + b.price, 0);"


def test_replace_code_is_staged_not_written(workspace: Workspace, repo: Path) -> None:
    before = (repo / "src" / "cart.js").read_text()
    changes = ChangeSet(workspace)
    changes.replace_code("src/cart.js", ORIGINAL_LINE, FIXED_LINE)
    assert (repo / "src" / "cart.js").read_text() == before  # disk untouched
    assert FIXED_LINE in (changes.current_content("src/cart.js") or "")


def test_diff_shows_change(workspace: Workspace) -> None:
    changes = ChangeSet(workspace)
    changes.replace_code("src/cart.js", ORIGINAL_LINE, FIXED_LINE)
    diff = changes.diff()
    assert "--- a/src/cart.js" in diff and "+++ b/src/cart.js" in diff
    assert f"-{ORIGINAL_LINE}" in diff
    assert f"+{FIXED_LINE}" in diff


def test_replace_code_not_found(workspace: Workspace) -> None:
    with pytest.raises(ToolError, match="not found"):
        ChangeSet(workspace).replace_code("src/cart.js", "doesNotExist()", "x")


def test_replace_code_ambiguous(workspace: Workspace, repo: Path) -> None:
    (repo / "dup.js").write_text("a();\na();\n")
    with pytest.raises(ToolError, match="matches 2 places"):
        ChangeSet(workspace).replace_code("dup.js", "a();", "b();")


def test_multiple_edits_to_same_file_keep_original(workspace: Workspace, repo: Path) -> None:
    changes = ChangeSet(workspace)
    changes.replace_code("src/cart.js", ORIGINAL_LINE, FIXED_LINE)
    changes.replace_code("src/cart.js", "function total", "function calculateTotal")
    [change] = changes.changes
    assert change.original == (repo / "src" / "cart.js").read_bytes().decode()
    assert "calculateTotal" in change.proposed and FIXED_LINE in change.proposed


def test_write_new_file(workspace: Workspace) -> None:
    changes = ChangeSet(workspace)
    change = changes.write_file("src/new.js", "export {};\n")
    assert change.is_new
    assert "--- /dev/null" in changes.diff()


def test_write_outside_repo_rejected(workspace: Workspace) -> None:
    with pytest.raises(PathSecurityError):
        ChangeSet(workspace).write_file("../evil.js", "boom")


def test_write_env_file_rejected(workspace: Workspace) -> None:
    with pytest.raises(PathSecurityError):
        ChangeSet(workspace).write_file(".env", "API_KEY=stolen")


def test_apply_writes_to_disk(workspace: Workspace, repo: Path) -> None:
    changes = ChangeSet(workspace)
    changes.replace_code("src/cart.js", ORIGINAL_LINE, FIXED_LINE)
    changes.write_file("src/new.js", "export {};\n")
    assert sorted(changes.apply()) == ["src/cart.js", "src/new.js"]
    assert FIXED_LINE in (repo / "src" / "cart.js").read_text()
    assert (repo / "src" / "new.js").read_text() == "export {};\n"


def test_apply_refuses_if_file_changed_since_staging(workspace: Workspace, repo: Path) -> None:
    changes = ChangeSet(workspace)
    changes.replace_code("src/cart.js", ORIGINAL_LINE, FIXED_LINE)
    (repo / "src" / "cart.js").write_text("// someone else edited this\n")
    with pytest.raises(ToolError, match="modified outside"):
        changes.apply()


def test_crlf_line_endings_preserved(workspace: Workspace, repo: Path) -> None:
    (repo / "win.js").write_bytes(b"const a = 1;\r\nconst b = 2;\r\n")
    changes = ChangeSet(workspace)
    changes.replace_code("win.js", "const a = 1;\nconst b = 2;", "const a = 1;\nconst b = 3;")
    changes.apply()
    assert (repo / "win.js").read_bytes() == b"const a = 1;\r\nconst b = 3;\r\n"


def test_replace_code_accepts_snippet_copied_with_line_numbers(workspace: Workspace) -> None:
    changes = ChangeSet(workspace)
    changes.replace_code("src/cart.js", f"   2 | {ORIGINAL_LINE}", f"   2 | {FIXED_LINE}")
    assert FIXED_LINE in (changes.current_content("src/cart.js") or "")


def test_not_found_error_points_at_closest_line(workspace: Workspace) -> None:
    with pytest.raises(ToolError, match=r"closest line in the file is: 'return items.reduce"):
        ChangeSet(workspace).replace_code("src/cart.js", "return items.reduce((a, b) => a + b.cost);", "x")

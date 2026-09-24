from pathlib import Path

import pytest

from app.tools.errors import PathSecurityError, ToolError
from app.tools.files import list_files, read_file
from app.tools.search import search_code
from app.tools.workspace import Workspace
from tests.conftest import link_directory


def test_list_files_skips_ignored_and_secret_files(workspace: Workspace) -> None:
    files = list_files(workspace)
    assert "src/cart.js" in files
    assert ".env.example" in files
    assert ".env" not in files
    assert not any(f.startswith(("node_modules", ".git/")) for f in files)


def test_list_and_search_do_not_follow_links_out_of_repo(
    workspace: Workspace, repo: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.txt").write_text("outside-only-marker")
    link_directory(repo / "linked", outside)
    assert not any(f.startswith("linked") for f in list_files(workspace))
    assert search_code(workspace, "outside-only-marker") == []


def test_list_files_subdirectory(workspace: Workspace) -> None:
    assert list_files(workspace, "src") == ["src/cart.js", "src/util.js"]


def test_list_files_outside_repo_rejected(workspace: Workspace) -> None:
    with pytest.raises(PathSecurityError):
        list_files(workspace, "..")


def test_read_file_numbers_lines(workspace: Workspace) -> None:
    content = read_file(workspace, "src/cart.js")
    assert content.splitlines()[0] == "   1 | function total(items) {"
    assert "   4 | module.exports = { total };" in content


def test_read_file_line_range(workspace: Workspace) -> None:
    assert read_file(workspace, "src/cart.js", 2, 2) == "   2 |   return items.reduce((a, b) => a + b.price);"


def test_read_missing_file(workspace: Workspace) -> None:
    with pytest.raises(ToolError, match="not found"):
        read_file(workspace, "src/nope.js")


def test_read_binary_file_rejected(workspace: Workspace, repo: Path) -> None:
    (repo / "logo.png").write_bytes(b"\x89PNG\x00\x00\x00binary")
    with pytest.raises(ToolError, match="binary"):
        read_file(workspace, "logo.png")


def test_read_env_file_blocked(workspace: Workspace) -> None:
    with pytest.raises(PathSecurityError):
        read_file(workspace, ".env")


def test_search_literal_case_insensitive(workspace: Workspace) -> None:
    matches = search_code(workspace, "REDUCE")
    assert [(m.path, m.line) for m in matches] == [("src/cart.js", 2)]


def test_search_regex(workspace: Workspace) -> None:
    matches = search_code(workspace, r"TAX_\w+\s*=", is_regex=True)
    assert matches[0].path == "src/util.js"


def test_search_glob_filter(workspace: Workspace) -> None:
    assert search_code(workspace, "shopping", file_glob="*.js") == []
    assert search_code(workspace, "shopping", file_glob="*.md")[0].path == "README.md"


def test_search_skips_node_modules_and_secrets(workspace: Workspace) -> None:
    # "total" appears in node_modules; the key only appears in .env
    assert all(not m.path.startswith("node_modules") for m in search_code(workspace, "total"))
    assert search_code(workspace, "supersecret") == []


def test_search_invalid_regex(workspace: Workspace) -> None:
    with pytest.raises(ToolError, match="Invalid regular expression"):
        search_code(workspace, "(unclosed", is_regex=True)

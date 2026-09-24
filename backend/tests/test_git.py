from pathlib import Path

from app.tools.changeset import ChangeSet
from app.tools.git import commit_changes, get_git_diff, git_status
from app.tools.workspace import Workspace
from tests.conftest import git


def test_clean_status(workspace: Workspace) -> None:
    status = git_status(workspace)
    assert status.is_repo
    assert status.branch == "main"
    assert status.is_clean


def test_status_reports_uncommitted_changes(workspace: Workspace, repo: Path) -> None:
    (repo / "README.md").write_text("changed\n")
    (repo / "notes.txt").write_text("new\n")
    files = {f.path: f.code for f in git_status(workspace).files}
    assert files == {"README.md": " M", "notes.txt": "??"}


def test_non_repo(tmp_path: Path) -> None:
    status = git_status(Workspace(tmp_path))
    assert not status.is_repo and status.is_clean


def test_diff_empty_when_clean(workspace: Workspace) -> None:
    assert get_git_diff(workspace) == ""


def test_diff_after_applied_change(workspace: Workspace) -> None:
    changes = ChangeSet(workspace)
    changes.replace_code("src/cart.js", "b.price);", "b.price, 0);")
    changes.apply()
    diff = get_git_diff(workspace)
    assert "diff --git a/src/cart.js b/src/cart.js" in diff
    assert "+  return items.reduce((a, b) => a + b.price, 0);" in diff


def test_diff_includes_untracked_files_but_not_ignored_secrets(workspace: Workspace, repo: Path) -> None:
    (repo / "src" / "helper.js").write_text("export const x = 1;\n")
    (repo / ".env").write_text("API_KEY=sk-changedsecret\n")  # gitignored and secret
    diff = get_git_diff(workspace)
    assert "+++ b/src/helper.js" in diff
    assert "changedsecret" not in diff


def test_commit_only_given_files(workspace: Workspace, repo: Path) -> None:
    (repo / "src" / "cart.js").write_text("fixed\n")
    (repo / "README.md").write_text("unrelated edit\n")
    sha = commit_changes(workspace, ["src/cart.js"], "Fix cart total")
    assert sha
    assert git(repo, "log", "-1", "--pretty=%s").strip() == "Fix cart total"
    remaining = {f.path for f in git_status(workspace).files}
    assert remaining == {"README.md"}  # unrelated change left uncommitted

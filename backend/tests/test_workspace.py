from pathlib import Path

import pytest

from app.tools.errors import PathSecurityError
from app.tools.workspace import Workspace, is_secret_file
from tests.conftest import link_directory


def test_resolves_normal_path(workspace: Workspace, repo: Path) -> None:
    assert workspace.resolve("src/cart.js") == (repo / "src" / "cart.js").resolve()


def test_resolves_dot_to_root(workspace: Workspace) -> None:
    assert workspace.resolve(".") == workspace.root


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        "../../etc/passwd",
        "src/../../outside.txt",
        "src/../../../../../../Windows/System32/drivers/etc/hosts",
        "..\\outside.txt",
    ],
)
def test_rejects_parent_traversal(workspace: Workspace, path: str) -> None:
    with pytest.raises(PathSecurityError):
        workspace.resolve(path)


@pytest.mark.parametrize("path", ["/etc/passwd", "\\Windows\\win.ini", "C:\\Windows\\win.ini", "C:foo", "file.txt:stream"])
def test_rejects_absolute_and_drive_paths(workspace: Workspace, path: str) -> None:
    with pytest.raises(PathSecurityError):
        workspace.resolve(path)


def test_rejects_symlink_escaping_repo(workspace: Workspace, repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret")
    link_directory(repo / "sneaky", outside)
    with pytest.raises(PathSecurityError):
        workspace.resolve("sneaky/secret.txt")


def test_allows_symlink_inside_repo(workspace: Workspace, repo: Path) -> None:
    link_directory(repo / "src_link", repo / "src")
    assert workspace.resolve("src_link/cart.js") == (repo / "src" / "cart.js").resolve()


def test_blocks_git_directory(workspace: Workspace) -> None:
    with pytest.raises(PathSecurityError):
        workspace.resolve(".git/config")


def test_blocks_env_file_by_default(workspace: Workspace) -> None:
    with pytest.raises(PathSecurityError, match="secrets"):
        workspace.resolve(".env")


def test_env_file_allowed_with_explicit_permission(repo: Path) -> None:
    assert Workspace(repo, allow_secret_files=True).resolve(".env").name == ".env"


@pytest.mark.parametrize(
    ("name", "secret"),
    [
        (".env", True),
        (".env.production", True),
        ("config/server.pem", True),
        ("id_rsa", True),
        (".npmrc", True),
        (".env.example", False),
        ("src/cart.js", False),
        ("environment.ts", False),
    ],
)
def test_secret_file_detection(name: str, secret: bool) -> None:
    assert is_secret_file(name) is secret


def test_missing_root_rejected(tmp_path: Path) -> None:
    with pytest.raises(PathSecurityError):
        Workspace(tmp_path / "does-not-exist")

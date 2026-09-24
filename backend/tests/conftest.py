import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.tools.workspace import Workspace


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def link_directory(link: Path, target: Path) -> None:
    """Create a directory symlink, falling back to an NTFS junction on Windows.

    Junctions behave like symlinks for path resolution but don't need admin rights,
    so the symlink-escape tests still run on a normal Windows account.
    """
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("Creating symlinks is not permitted on this machine")
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


@pytest.fixture(scope="session")
def template_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Built once per test run - git init/commit is slow on Windows."""
    root = tmp_path_factory.mktemp("template") / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "cart.js").write_text(
        "function total(items) {\n  return items.reduce((a, b) => a + b.price);\n}\n"
        "module.exports = { total };\n"
    )
    (root / "src" / "util.js").write_text("export const TAX_RATE = 0.2;\n")
    (root / "README.md").write_text("# Demo\nShopping cart demo\n")
    (root / ".env").write_text("API_KEY=sk-supersecretvalue123\n")
    (root / ".env.example").write_text("API_KEY=\n")
    (root / "node_modules" / "lib").mkdir(parents=True)
    (root / "node_modules" / "lib" / "index.js").write_text("// total should be ignored\n")
    (root / ".gitignore").write_text("node_modules/\n.env\n")

    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "config", "core.autocrlf", "false")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "initial")
    return root


@pytest.fixture
def repo(template_repo: Path, tmp_path: Path) -> Path:
    """A fresh copy of the committed demo repository for each test."""
    return Path(shutil.copytree(template_repo, tmp_path / "repo"))


@pytest.fixture
def workspace(repo: Path) -> Workspace:
    return Workspace(repo)

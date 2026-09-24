"""Whitelisted command execution: run_command and run_tests.

Security model (fail closed - anything not explicitly allowed is refused):
  1. Shell metacharacters are rejected outright, and commands run with shell=False,
     so `;`, `&&`, `|`, redirects and `$(...)` can never chain a second command.
  2. The command must start with an allowed prefix, e.g. ("npm", "test").
  3. Each extra argument must be a known-safe flag for that command, or a path
     that stays inside the workspace.
  4. The child process gets an environment with API keys/tokens removed, a timeout,
     and the repository as its working directory.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

from pydantic import BaseModel

from app.tools.errors import CommandNotAllowedError, ToolError
from app.tools.workspace import Workspace

MAX_OUTPUT_CHARS = 8_000
SHELL_METACHARACTERS = set(";&|`$<>\n\r")
SENSITIVE_ENV_PATTERN = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL", re.IGNORECASE)

PYTEST_FLAGS = frozenset(
    {"-q", "-v", "-vv", "-x", "-s", "-rA", "--no-header", "--tb=short", "--tb=line", "--tb=no"}
)


@dataclass(frozen=True)
class CommandRule:
    prefix: tuple[str, ...]
    allowed_flags: frozenset[str] = frozenset()
    flags_with_value: frozenset[str] = frozenset()  # flags whose next token is a free-text value
    allow_paths: bool = False


ALLOWED_COMMANDS: tuple[CommandRule, ...] = (
    CommandRule(("npm", "test")),
    CommandRule(("npm", "run", "test")),
    CommandRule(("npm", "run", "lint")),
    CommandRule(("pytest",), PYTEST_FLAGS, frozenset({"-k"}), allow_paths=True),
    CommandRule(("python", "-m", "pytest"), PYTEST_FLAGS, frozenset({"-k"}), allow_paths=True),
    CommandRule(
        ("git", "diff"),
        frozenset({"--stat", "--cached", "--staged", "--name-only", "--name-status", "--no-color", "--"}),
        allow_paths=True,
    ),
    CommandRule(("git", "status"), frozenset({"--short", "-s", "--porcelain", "--branch", "-b"})),
)


class CommandResult(BaseModel):
    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def _truncate(text: str) -> str:
    """Keep the *end* of long output - that's where test failures and summaries are."""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return f"... [{len(text) - MAX_OUTPUT_CHARS} characters truncated]\n" + text[-MAX_OUTPUT_CHARS:]


def _find_rule(argv: list[str]) -> CommandRule | None:
    matching = [r for r in ALLOWED_COMMANDS if tuple(argv[: len(r.prefix)]) == r.prefix]
    return max(matching, key=lambda r: len(r.prefix), default=None)


def validate_command(command: str, workspace: Workspace) -> list[str]:
    """Return the parsed argv if the command is allowed, otherwise raise CommandNotAllowedError."""
    if any(char in SHELL_METACHARACTERS for char in command):
        raise CommandNotAllowedError("Shell operators (; & | $ > < `) are not allowed")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise CommandNotAllowedError(f"Could not parse command: {exc}") from exc
    if not argv:
        raise CommandNotAllowedError("Empty command")

    rule = _find_rule(argv)
    if rule is None:
        allowed = ", ".join(" ".join(r.prefix) for r in ALLOWED_COMMANDS)
        raise CommandNotAllowedError(f"Command not in whitelist. Allowed: {allowed}")

    extra = argv[len(rule.prefix) :]
    index = 0
    while index < len(extra):
        arg = extra[index]
        if arg in rule.flags_with_value:
            index += 2  # the value is free text (e.g. a pytest -k expression), not executed
            continue
        if arg.startswith("-"):
            if arg not in rule.allowed_flags:
                raise CommandNotAllowedError(f"Flag {arg!r} is not allowed for '{' '.join(rule.prefix)}'")
        elif rule.allow_paths:
            workspace.resolve(arg.split("::")[0])  # raises PathSecurityError if it escapes
        else:
            raise CommandNotAllowedError(f"Extra arguments are not allowed for '{' '.join(rule.prefix)}'")
        index += 1
    return argv


def sanitized_env() -> dict[str, str]:
    """Copy of the environment without anything that looks like a credential."""
    env = {k: v for k, v in os.environ.items() if not SENSITIVE_ENV_PATTERN.search(k)}
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["CI"] = "true"  # stops test runners from entering interactive watch mode
    return env


def _to_executable_argv(argv: list[str]) -> list[str]:
    # Run Python tooling with the interpreter CodePilot itself uses, so results are predictable.
    if argv[0] == "pytest":
        return [sys.executable, "-m", "pytest", *argv[1:]]
    if argv[0] == "python":
        return [sys.executable, *argv[1:]]
    # shutil.which finds e.g. npm.cmd on Windows, which shell=False would otherwise miss.
    executable = shutil.which(argv[0])
    if executable is None:
        raise ToolError(f"'{argv[0]}' is not installed or not on PATH")
    return [executable, *argv[1:]]


def run_command(command: str, workspace: Workspace, timeout_seconds: int = 120) -> CommandResult:
    argv = validate_command(command, workspace)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            _to_executable_argv(argv),
            cwd=workspace.root,
            env=sanitized_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            shell=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            exit_code=None,
            stdout=_truncate(str(exc.stdout or "")),
            stderr=f"Command timed out after {timeout_seconds}s",
            duration_ms=int((time.perf_counter() - started) * 1000),
            timed_out=True,
        )
    return CommandResult(
        command=command,
        exit_code=completed.returncode,
        stdout=_truncate(completed.stdout),
        stderr=_truncate(completed.stderr),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def detect_test_command(workspace: Workspace) -> str | None:
    package_json = workspace.root / "package.json"
    if package_json.is_file():
        try:
            scripts = json.loads(package_json.read_text(encoding="utf-8")).get("scripts", {})
        except (json.JSONDecodeError, AttributeError):
            scripts = {}
        if "test" in scripts:
            return "npm test"
    python_markers = ("pytest.ini", "pyproject.toml", "setup.cfg", "conftest.py")
    if any((workspace.root / m).is_file() for m in python_markers) or (workspace.root / "tests").is_dir():
        return "python -m pytest -q"
    return None


def run_tests(workspace: Workspace, timeout_seconds: int = 120) -> CommandResult:
    command = detect_test_command(workspace)
    if command is None:
        raise ToolError("Could not detect a test command (no package.json test script or pytest config)")
    return run_command(command, workspace, timeout_seconds)

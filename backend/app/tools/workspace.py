"""The security boundary for all file access.

Every path the agent supplies goes through `Workspace.resolve()`. It resolves `..` and
symlinks *first*, then checks the real location is still inside the repository root.
Checking the string before resolving would be bypassable (e.g. a symlink named `docs`
that points at `C:\\Windows`).
"""

from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from app.tools.errors import PathSecurityError

# Files that commonly hold credentials. Reading them requires explicit permission.
SECRET_FILE_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials*",
)
# Template files are meant to be committed and contain no real secrets.
SECRET_FILE_EXCEPTIONS: tuple[str, ...] = (".env.example", ".env.sample", ".env.template")

# Directories that are never useful to the agent and are expensive to walk.
IGNORED_DIRS: frozenset[str] = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "build"}
)


def is_secret_file(relative_path: str) -> bool:
    name = PurePosixPath(relative_path).name.lower()
    if name in SECRET_FILE_EXCEPTIONS:
        return False
    return any(fnmatch(name, pattern) for pattern in SECRET_FILE_PATTERNS)


class Workspace:
    """A repository root that the agent is confined to."""

    def __init__(self, root: Path | str, allow_secret_files: bool = False) -> None:
        root_path = Path(root)
        if not root_path.is_dir():
            raise PathSecurityError(f"Workspace root does not exist: {root}")
        self.root: Path = root_path.resolve(strict=True)
        self.allow_secret_files = allow_secret_files

    @property
    def name(self) -> str:
        return self.root.name

    def resolve(self, relative_path: str) -> Path:
        """Turn an agent-supplied relative path into a safe absolute path, or raise."""
        # Treat "\" as a separator on every OS, so "..\x" is caught on Linux too (there it's a valid filename char).
        cleaned = (relative_path or ".").strip().replace("\\", "/")
        # ':' blocks Windows drive-relative paths ("C:foo") and alternate data streams.
        if ":" in cleaned or cleaned.startswith(("/", "\\")):
            raise PathSecurityError(f"Absolute paths are not allowed: {relative_path!r}")

        # resolve() follows symlinks and collapses '..' so we check the *real* target.
        candidate = (self.root / cleaned).resolve()
        if not candidate.is_relative_to(self.root):
            raise PathSecurityError(f"Path escapes the repository: {relative_path!r}")

        relative = candidate.relative_to(self.root)
        if relative.parts and relative.parts[0] == ".git":
            raise PathSecurityError("Direct access to the .git directory is not allowed")
        if is_secret_file(relative.as_posix()) and not self.allow_secret_files:
            raise PathSecurityError(
                f"{relative.as_posix()!r} may contain secrets; access requires explicit permission"
            )
        return candidate

    def relative(self, absolute_path: Path) -> str:
        """Repository-relative POSIX path, used in everything shown to the user/LLM."""
        return absolute_path.resolve().relative_to(self.root).as_posix()

    def relative_unresolved(self, path_under_root: Path) -> str:
        """Relative path *without* following symlinks, so resolve() can then vet the link."""
        return path_under_root.relative_to(self.root).as_posix()

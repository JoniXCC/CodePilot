class ToolError(Exception):
    """A tool failed in an expected way. The message is safe to show to the LLM and the user."""


class PathSecurityError(ToolError):
    """A path is outside the workspace or points at a protected file."""


class CommandNotAllowedError(ToolError):
    """A shell command was rejected by the whitelist."""

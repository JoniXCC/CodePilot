class NotFoundError(Exception):
    """The requested session or project does not exist."""


class ConflictError(Exception):
    """The action is not valid in the current state (e.g. approving a rejected session)."""

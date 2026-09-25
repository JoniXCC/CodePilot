from pydantic import BaseModel


class ProjectInfo(BaseModel):
    name: str
    is_git_repo: bool
    branch: str | None
    uncommitted_files: list[str]
    test_command: str | None

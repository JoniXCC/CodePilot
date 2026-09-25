from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

ACTIVE_STATUSES = {"running"}


class CreateSessionRequest(BaseModel):
    project: str = Field(min_length=1, max_length=255)
    bug_description: str = Field(min_length=5, max_length=5_000)


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    event_id: str
    type: str
    message: str
    tool: str | None
    call_id: str | None
    success: bool | None
    warning: bool = False
    detail: str | None
    duration_ms: int | None
    timestamp: datetime


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_name: str
    bug_description: str
    status: str
    created_at: datetime
    tool_calls: int
    duration_ms: int
    test_passed: bool | None
    files_modified: list[str]


class SessionDetail(SessionSummary):
    model: str | None
    uncommitted_at_start: list[str]
    hypothesis: str | None
    summary: str | None
    root_cause: str | None
    fix_explanation: str | None
    files_inspected: list[str]
    proposed_diff: str | None
    final_diff: str | None
    test_command: str | None
    test_output: str | None
    commit_sha: str | None
    input_tokens: int
    output_tokens: int
    error: str | None
    actions: list[ActionOut] = []


class CommitRequest(BaseModel):
    message: str = Field(min_length=3, max_length=2_000)


class CommitMessageOut(BaseModel):
    message: str


class CommitOut(BaseModel):
    sha: str
    message: str

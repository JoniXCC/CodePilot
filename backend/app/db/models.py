from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentSessionRecord(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(255), index=True)
    bug_description: Mapped[str] = mapped_column(Text)
    # running | awaiting_approval | applied | rejected | no_changes | failed | cancelled
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    model: Mapped[str | None] = mapped_column(String(64))
    uncommitted_at_start: Mapped[list[str]] = mapped_column(JSON, default=list)

    hypothesis: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    fix_explanation: Mapped[str | None] = mapped_column(Text)
    files_inspected: Mapped[list[str]] = mapped_column(JSON, default=list)
    files_modified: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Staged edits [{path, original, proposed}] - kept here so approval survives a server restart.
    proposed_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    proposed_diff: Mapped[str | None] = mapped_column(Text)

    final_diff: Mapped[str | None] = mapped_column(Text)
    test_command: Mapped[str | None] = mapped_column(String(255))
    test_passed: Mapped[bool | None] = mapped_column(Boolean)
    test_output: Mapped[str | None] = mapped_column(Text)
    commit_sha: Mapped[str | None] = mapped_column(String(64))

    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)

    actions: Mapped[list["AgentActionRecord"]] = relationship(
        back_populates="session", order_by="AgentActionRecord.seq", cascade="all, delete-orphan"
    )


class AgentActionRecord(Base):
    """One timeline event (tool started/finished, hypothesis, status...)."""

    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("agent_sessions.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    event_id: Mapped[str] = mapped_column(String(32))
    type: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    tool: Mapped[str | None] = mapped_column(String(64))
    call_id: Mapped[str | None] = mapped_column(String(128))
    success: Mapped[bool | None] = mapped_column(Boolean)
    warning: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    session: Mapped[AgentSessionRecord] = relationship(back_populates="actions")

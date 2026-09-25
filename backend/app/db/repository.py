"""All database queries live here, so services never build SQL themselves."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.agent.events import AgentEvent
from app.db.models import AgentActionRecord, AgentSessionRecord


def create_session(db: Session, **fields: Any) -> AgentSessionRecord:
    record = AgentSessionRecord(**fields)
    db.add(record)
    db.flush()
    return record


def get_session(db: Session, session_id: str, with_actions: bool = False) -> AgentSessionRecord | None:
    query = select(AgentSessionRecord).where(AgentSessionRecord.id == session_id)
    if with_actions:
        query = query.options(selectinload(AgentSessionRecord.actions))
    return db.scalars(query).first()


def list_sessions(db: Session, limit: int = 100) -> list[AgentSessionRecord]:
    query = select(AgentSessionRecord).order_by(AgentSessionRecord.created_at.desc()).limit(limit)
    return list(db.scalars(query))


def update_session(db: Session, session_id: str, **fields: Any) -> None:
    record = db.get(AgentSessionRecord, session_id)
    if record is None:
        raise KeyError(session_id)
    for key, value in fields.items():
        setattr(record, key, value)


def add_action(db: Session, session_id: str, event: AgentEvent) -> AgentActionRecord:
    next_seq = (db.scalar(select(func.max(AgentActionRecord.seq)).where(AgentActionRecord.session_id == session_id)) or 0) + 1
    action = AgentActionRecord(
        session_id=session_id,
        seq=next_seq,
        event_id=event.id,
        type=event.type,
        message=event.message,
        tool=event.tool,
        call_id=event.call_id,
        success=event.success,
        warning=event.warning,
        detail=event.detail,
        duration_ms=event.duration_ms,
        timestamp=event.timestamp,
    )
    db.add(action)
    return action


def actions_after(db: Session, session_id: str, seq: int) -> list[AgentActionRecord]:
    query = (
        select(AgentActionRecord)
        .where(AgentActionRecord.session_id == session_id, AgentActionRecord.seq > seq)
        .order_by(AgentActionRecord.seq)
    )
    return list(db.scalars(query))


def get_status(db: Session, session_id: str) -> str | None:
    return db.scalar(select(AgentSessionRecord.status).where(AgentSessionRecord.id == session_id))

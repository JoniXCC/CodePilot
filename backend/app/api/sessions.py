import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.api.deps import get_service
from app.schemas.sessions import (
    CommitMessageOut,
    CommitOut,
    CommitRequest,
    CreateSessionRequest,
    SessionDetail,
    SessionSummary,
)
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])

POLL_INTERVAL_SECONDS = 0.4


@router.post("", response_model=SessionDetail, status_code=status.HTTP_201_CREATED)
def create_session(body: CreateSessionRequest, service: SessionService = Depends(get_service)) -> SessionDetail:
    return service.start_session(body.project, body.bug_description)


@router.get("", response_model=list[SessionSummary])
def list_sessions(service: SessionService = Depends(get_service)) -> list[SessionSummary]:
    return service.list_sessions()


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, service: SessionService = Depends(get_service)) -> SessionDetail:
    return service.get_session(session_id)


@router.get("/{session_id}/events")
async def stream_events(session_id: str, request: Request, service: SessionService = Depends(get_service)) -> StreamingResponse:
    """Server-Sent Events: pushes each new timeline action to the browser as it happens.

    Events are read from the database, so a reconnecting browser (which sends
    Last-Event-ID automatically) resumes exactly where it left off.
    """
    await run_in_threadpool(service.get_session, session_id)  # 404 if unknown
    last_seq = int(request.headers.get("last-event-id") or 0)

    async def event_stream() -> AsyncIterator[str]:
        nonlocal last_seq
        while not await request.is_disconnected():
            actions, current_status = await run_in_threadpool(service.events_after, session_id, last_seq)
            for action in actions:
                last_seq = action.seq
                yield f"id: {action.seq}\nevent: action\ndata: {action.model_dump_json()}\n\n"
            if current_status != "running" and not actions:
                yield f"event: end\ndata: {json.dumps({'status': current_status})}\n\n"
                return
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@router.post("/{session_id}/cancel", response_model=SessionDetail)
def cancel_session(session_id: str, service: SessionService = Depends(get_service)) -> SessionDetail:
    return service.cancel(session_id)


@router.post("/{session_id}/approve", response_model=SessionDetail)
def approve_session(session_id: str, service: SessionService = Depends(get_service)) -> SessionDetail:
    return service.approve(session_id)


@router.post("/{session_id}/reject", response_model=SessionDetail)
def reject_session(session_id: str, service: SessionService = Depends(get_service)) -> SessionDetail:
    return service.reject(session_id)


@router.post("/{session_id}/commit-message", response_model=CommitMessageOut)
def suggest_commit_message(session_id: str, service: SessionService = Depends(get_service)) -> CommitMessageOut:
    return CommitMessageOut(message=service.suggest_commit_message(session_id))


@router.post("/{session_id}/commit", response_model=CommitOut)
def commit_session(session_id: str, body: CommitRequest, service: SessionService = Depends(get_service)) -> CommitOut:
    sha, message = service.commit(session_id, body.message)
    return CommitOut(sha=sha, message=message)

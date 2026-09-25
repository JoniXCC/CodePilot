"""Session lifecycle: run the agent -> await approval -> apply + test -> (optional) commit.

    running --> awaiting_approval --approve--> applied --commit--> applied (+ commit_sha)
       |               '---------reject---> rejected
       '--> no_changes | failed | cancelled
"""

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.agent.events import AgentEvent
from app.agent.loop import Agent, AgentRunResult
from app.agent.registry import ToolContext
from app.agent.toolset import build_registry
from app.config import Settings
from app.db import repository
from app.db.database import Database
from app.llm.base import LLMError, LLMProvider
from app.schemas.sessions import ActionOut, SessionDetail, SessionSummary
from app.services.errors import ConflictError, NotFoundError
from app.services.projects import open_project
from app.tools import git, shell
from app.tools.changeset import ChangeSet, FileChange
from app.tools.errors import ToolError
from app.tools.workspace import Workspace

logger = logging.getLogger("codepilot.sessions")

RESULT_STATUS = {"proposed": "awaiting_approval", "no_changes": "no_changes", "failed": "failed", "cancelled": "cancelled"}

COMMIT_SYSTEM_PROMPT = (
    "You write git commit messages. Reply with only the message: an imperative subject line "
    "of at most 60 characters, a blank line, then 1-3 short lines explaining why."
)


class SessionService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        provider_factory: Callable[[], LLMProvider],
        max_concurrent_runs: int = 2,
    ) -> None:
        self.settings = settings
        self.db = database
        self.provider_factory = provider_factory
        self._max_runs = max_concurrent_runs
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_runs, thread_name_prefix="agent")
        self._cancel_events: dict[str, threading.Event] = {}
        self._state_lock = threading.Lock()  # serialises approve/reject/commit transitions

    # --- queries -----------------------------------------------------------------------

    def list_sessions(self) -> list[SessionSummary]:
        with self.db.session() as db:
            return [SessionSummary.model_validate(r) for r in repository.list_sessions(db)]

    def get_session(self, session_id: str) -> SessionDetail:
        with self.db.session() as db:
            record = repository.get_session(db, session_id, with_actions=True)
            if record is None:
                raise NotFoundError(f"Session not found: {session_id}")
            return SessionDetail.model_validate(record)

    def events_after(self, session_id: str, seq: int) -> tuple[list[ActionOut], str | None]:
        """New timeline events since `seq`, plus the session's current status (for SSE streaming)."""
        with self.db.session() as db:
            actions = [ActionOut.model_validate(a) for a in repository.actions_after(db, session_id, seq)]
            return actions, repository.get_status(db, session_id)

    # --- running the agent -------------------------------------------------------------

    def start_session(self, project: str, bug_description: str) -> SessionDetail:
        workspace = open_project(self.settings.projects_dir, project)
        status = git.git_status(workspace)
        session_id = uuid.uuid4().hex
        with self.db.session() as db:
            repository.create_session(
                db,
                id=session_id,
                project_name=workspace.name,
                bug_description=bug_description.strip(),
                status="running",
                model=self.settings.model_name,
                uncommitted_at_start=[f.path for f in status.files],
            )
        cancel_event = threading.Event()
        self._cancel_events[session_id] = cancel_event
        self._executor.submit(self._run_agent, session_id, project, bug_description, cancel_event)
        return self.get_session(session_id)

    def wait_for_idle(self) -> None:
        """Block until queued runs finish (used by tests and on shutdown)."""
        self._executor.shutdown(wait=True)
        self._executor = ThreadPoolExecutor(max_workers=self._max_runs, thread_name_prefix="agent")

    def cancel(self, session_id: str) -> SessionDetail:
        detail = self.get_session(session_id)
        if detail.status != "running":
            raise ConflictError("Only running sessions can be cancelled")
        if event := self._cancel_events.get(session_id):
            event.set()
        return detail

    def _record_event(self, session_id: str, event: AgentEvent) -> None:
        with self.db.session() as db:
            repository.add_action(db, session_id, event)

    def _run_agent(self, session_id: str, project: str, bug_description: str, cancel_event: threading.Event) -> None:
        try:
            workspace = open_project(self.settings.projects_dir, project)
            context = ToolContext(
                workspace=workspace,
                changeset=ChangeSet(workspace),
                command_timeout=self.settings.command_timeout_seconds,
            )
            agent = Agent(
                provider=self.provider_factory(),
                registry=build_registry(),
                max_steps=self.settings.agent_max_steps,
                on_event=lambda event: self._record_event(session_id, event),
                cancel_event=cancel_event,
            )
            result = agent.run(bug_description, context)
            self._save_result(session_id, result, context.changeset.changes)
        except Exception as exc:  # the worker thread must always leave the session in a final state
            logger.exception("Agent run crashed", extra={"fields": {"session_id": session_id}})
            self._record_event(session_id, AgentEvent(type="error", message="Internal error while running the agent", success=False))
            with self.db.session() as db:
                repository.update_session(db, session_id, status="failed", error=f"Internal error: {type(exc).__name__}")
        finally:
            self._cancel_events.pop(session_id, None)

    def _save_result(self, session_id: str, result: AgentRunResult, changes: list[FileChange]) -> None:
        with self.db.session() as db:
            repository.update_session(
                db,
                session_id,
                status=RESULT_STATUS[result.status],
                hypothesis=result.hypothesis,
                summary=result.summary or None,
                root_cause=result.root_cause or None,
                fix_explanation=result.fix_explanation or None,
                files_inspected=result.files_inspected,
                files_modified=result.files_modified,
                proposed_changes=[c.model_dump() for c in changes],
                proposed_diff=result.diff or None,
                tool_calls=result.tool_calls,
                duration_ms=result.duration_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                error=result.error,
            )

    # --- human decisions ---------------------------------------------------------------

    def approve(self, session_id: str) -> SessionDetail:
        """Apply the staged patch, run the tests and capture the final git diff."""
        with self._state_lock:
            with self.db.session() as db:
                record = repository.get_session(db, session_id)
                if record is None:
                    raise NotFoundError(f"Session not found: {session_id}")
                if record.status != "awaiting_approval":
                    raise ConflictError(f"Cannot approve a session with status '{record.status}'")
                project, saved_changes = record.project_name, record.proposed_changes

            workspace = open_project(self.settings.projects_dir, project)
            changeset = ChangeSet.restore(workspace, [FileChange.model_validate(c) for c in saved_changes])
            try:
                written = changeset.apply()
            except ToolError as exc:
                raise ConflictError(str(exc)) from exc
            self._record_event(session_id, AgentEvent(type="status", message=f"Applied changes to {', '.join(written)}", success=True))

            test_fields = self._run_tests_after_apply(session_id, workspace)
            final_diff = git.get_git_diff(workspace) if git.is_git_repo(workspace) else changeset.diff()
            with self.db.session() as db:
                repository.update_session(db, session_id, status="applied", final_diff=final_diff, **test_fields)
        return self.get_session(session_id)

    def _run_tests_after_apply(self, session_id: str, workspace: Workspace) -> dict[str, object]:
        command = shell.detect_test_command(workspace)
        if command is None:
            self._record_event(session_id, AgentEvent(type="status", message="No test command detected; skipped tests"))
            return {"test_command": None, "test_passed": None, "test_output": None}
        started = AgentEvent(type="tool_started", message="Running tests", tool="run_tests", call_id="post-apply-tests")
        self._record_event(session_id, started)
        result = shell.run_command(command, workspace, self.settings.command_timeout_seconds)
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        self._record_event(
            session_id,
            AgentEvent(
                type="tool_finished",
                message="Tests passed" if result.succeeded else "Tests failed",
                tool="run_tests",
                call_id="post-apply-tests",
                success=result.succeeded,
                detail=output[-2_000:],
                duration_ms=result.duration_ms,
            ),
        )
        return {"test_command": command, "test_passed": result.succeeded, "test_output": output}

    def reject(self, session_id: str) -> SessionDetail:
        with self._state_lock, self.db.session() as db:
            status = repository.get_status(db, session_id)
            if status is None:
                raise NotFoundError(f"Session not found: {session_id}")
            if status != "awaiting_approval":
                raise ConflictError(f"Cannot reject a session with status '{status}'")
            repository.update_session(db, session_id, status="rejected")
            repository.add_action(db, session_id, AgentEvent(type="status", message="Changes rejected; nothing was written"))
        return self.get_session(session_id)

    # --- committing --------------------------------------------------------------------

    def suggest_commit_message(self, session_id: str) -> str:
        detail = self._applied_session(session_id)
        fallback = detail.summary or f"Fix: {detail.bug_description[:50]}"
        prompt = (
            f"Bug report: {detail.bug_description}\nRoot cause: {detail.root_cause}\n"
            f"Fix: {detail.fix_explanation}\n\nDiff:\n{(detail.final_diff or '')[:6_000]}"
        )
        try:
            message = self.provider_factory().generate(COMMIT_SYSTEM_PROMPT, prompt)
        except LLMError:
            return fallback
        return message or fallback

    def commit(self, session_id: str, message: str) -> tuple[str, str]:
        with self._state_lock:
            detail = self._applied_session(session_id)
            if detail.commit_sha:
                raise ConflictError("These changes were already committed")
            workspace = open_project(self.settings.projects_dir, detail.project_name)
            try:
                sha = git.commit_changes(workspace, detail.files_modified, message.strip())
            except ToolError as exc:
                raise ConflictError(str(exc)) from exc
            with self.db.session() as db:
                repository.update_session(db, session_id, commit_sha=sha)
                repository.add_action(db, session_id, AgentEvent(type="status", message=f"Created commit {sha}", success=True))
        return sha, message.strip()

    def _applied_session(self, session_id: str) -> SessionDetail:
        detail = self.get_session(session_id)
        if detail.status != "applied":
            raise ConflictError("Only applied sessions can be committed")
        return detail

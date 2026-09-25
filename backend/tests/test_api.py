"""HTTP-level tests: the full create -> stream -> approve/reject -> commit flow."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.llm.base import LLMProvider
from app.llm.scripted_provider import ScriptedProvider, ScriptedStep
from app.main import create_app
from app.services.repo_copies import create_git_copy
from tests.conftest import git
from tests.test_agent_loop import FailingProvider

needs_npm = pytest.mark.skipif(shutil.which("npm") is None, reason="Node.js/npm not installed")

BUG_LINE = "  return tier?.rate;"
FIX_LINE = "  return tier?.rate ?? 0;"
FIX_STEPS = [
    ScriptedStep(tool="search_code", arguments={"query": "calculateTotal"}),
    ScriptedStep(tool="read_file", arguments={"path": "src/cart.js"}),
    ScriptedStep(tool="record_hypothesis", arguments={"hypothesis": "No discount tier matches an empty cart"}),
    ScriptedStep(tool="replace_code", arguments={"path": "src/cart.js", "old_code": BUG_LINE, "new_code": FIX_LINE}),
    ScriptedStep(tool="finish", arguments={"summary": "Default bulk discount rate to 0",
                                           "root_cause": "getBulkDiscountRate returns undefined for 0 items",
                                           "fix_explanation": "Fall back to a 0 rate"}),
]
COMMIT_MESSAGE = "Fix NaN total for empty carts\n\nDefault the bulk discount rate to 0."


def build_client(tmp_path: Path, provider_factory) -> TestClient:
    projects = tmp_path / "projects"
    create_git_copy(REPO_ROOT / "examples" / "shopping-cart", projects / "shopping-cart")
    settings = Settings(
        _env_file=None,
        projects_dir=projects,
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        log_level="WARNING",
    )
    return TestClient(create_app(settings, provider_factory))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    def factory() -> LLMProvider:
        return ScriptedProvider(list(FIX_STEPS), final_text=COMMIT_MESSAGE)

    with build_client(tmp_path, factory) as test_client:
        yield test_client


@pytest.fixture
def cart_file(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "shopping-cart" / "src" / "cart.js"


def run_session(client: TestClient) -> dict:
    response = client.post("/api/sessions", json={"project": "shopping-cart", "bug_description": "Empty cart total is NaN"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "running"
    client.app.state.session_service.wait_for_idle()
    return client.get(f"/api/sessions/{response.json()['id']}").json()


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"


def test_list_projects(client: TestClient) -> None:
    [project] = client.get("/api/projects").json()
    assert project == {
        "name": "shopping-cart", "is_git_repo": True, "branch": "main",
        "uncommitted_files": [], "test_command": "npm test",
    }


def test_unknown_project_and_session(client: TestClient) -> None:
    assert client.get("/api/projects/nope").status_code == 404
    assert client.post("/api/sessions", json={"project": "nope", "bug_description": "something broke"}).status_code == 404
    assert client.get("/api/sessions/does-not-exist").status_code == 404


def test_request_validation(client: TestClient) -> None:
    assert client.post("/api/sessions", json={"project": "shopping-cart", "bug_description": ""}).status_code == 422


def test_session_proposes_patch_without_writing(client: TestClient, cart_file: Path) -> None:
    before = cart_file.read_bytes()
    session = run_session(client)
    assert session["status"] == "awaiting_approval"
    assert session["hypothesis"] == "No discount tier matches an empty cart"
    assert session["files_inspected"] == ["src/cart.js"]
    assert session["files_modified"] == ["src/cart.js"]
    assert f"+{FIX_LINE}" in session["proposed_diff"]
    assert session["tool_calls"] == 5
    assert [a["type"] for a in session["actions"]][0] == "status"
    assert cart_file.read_bytes() == before


def test_event_stream(client: TestClient) -> None:
    session = run_session(client)
    body = client.get(f"/api/sessions/{session['id']}/events").text
    assert body.count("event: action") == len(session["actions"])
    assert 'event: end\ndata: {"status": "awaiting_approval"}' in body
    resumed = client.get(f"/api/sessions/{session['id']}/events", headers={"Last-Event-ID": "3"}).text
    assert resumed.count("event: action") == len(session["actions"]) - 3


@needs_npm
def test_approve_applies_patch_and_runs_tests(client: TestClient, cart_file: Path) -> None:
    session = run_session(client)
    approved = client.post(f"/api/sessions/{session['id']}/approve").json()
    assert approved["status"] == "applied"
    assert approved["test_command"] == "npm test"
    assert approved["test_passed"] is True
    assert f"+{FIX_LINE}" in approved["final_diff"]
    assert FIX_LINE in cart_file.read_text()
    assert approved["actions"][-1]["message"] == "Tests passed"
    # A second approval is a state conflict, not a second write.
    assert client.post(f"/api/sessions/{session['id']}/approve").status_code == 409


def test_reject_leaves_files_untouched(client: TestClient, cart_file: Path) -> None:
    before = cart_file.read_bytes()
    session = run_session(client)
    rejected = client.post(f"/api/sessions/{session['id']}/reject").json()
    assert rejected["status"] == "rejected"
    assert cart_file.read_bytes() == before
    assert client.post(f"/api/sessions/{session['id']}/approve").status_code == 409


def test_approve_refuses_if_file_changed_meanwhile(client: TestClient, cart_file: Path) -> None:
    session = run_session(client)
    cart_file.write_text("// edited by hand\n")
    response = client.post(f"/api/sessions/{session['id']}/approve")
    assert response.status_code == 409
    assert "modified outside" in response.json()["detail"]


@needs_npm
def test_commit_flow(client: TestClient, tmp_path: Path) -> None:
    session = run_session(client)
    assert client.post(f"/api/sessions/{session['id']}/commit", json={"message": "too early"}).status_code == 409
    client.post(f"/api/sessions/{session['id']}/approve")

    suggestion = client.post(f"/api/sessions/{session['id']}/commit-message").json()["message"]
    assert suggestion == COMMIT_MESSAGE
    commit = client.post(f"/api/sessions/{session['id']}/commit", json={"message": suggestion}).json()
    repo = tmp_path / "projects" / "shopping-cart"
    assert git(repo, "log", "-1", "--pretty=%s").strip() == "Fix NaN total for empty carts"
    assert git(repo, "rev-parse", "--short", "HEAD").strip() == commit["sha"]
    assert client.get(f"/api/sessions/{session['id']}").json()["commit_sha"] == commit["sha"]
    assert client.post(f"/api/sessions/{session['id']}/commit", json={"message": "again"}).status_code == 409


def test_history_lists_sessions_newest_first(client: TestClient) -> None:
    first = run_session(client)
    second = run_session(client)
    ids = [s["id"] for s in client.get("/api/sessions").json()]
    assert ids == [second["id"], first["id"]]


def test_uncommitted_changes_are_recorded(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "projects" / "shopping-cart" / "README.md").write_text("local edit\n")
    assert client.get("/api/projects/shopping-cart").json()["uncommitted_files"] == ["README.md"]
    assert run_session(client)["uncommitted_at_start"] == ["README.md"]


def test_provider_failure_marks_session_failed(tmp_path: Path) -> None:
    provider: LLMProvider = FailingProvider()
    with build_client(tmp_path, lambda: provider) as failing_client:
        session = run_session(failing_client)
    assert session["status"] == "failed"
    assert session["error"] == "Could not connect to the Anthropic API"

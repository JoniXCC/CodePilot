import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ProjectInfo } from "../api/types";

const EXAMPLE_BUG = "When the shopping cart is empty, the total price becomes NaN.";

export function Dashboard() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectInfo[] | null>(null);
  const [projectName, setProjectName] = useState("");
  const [bug, setBug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .listProjects()
      .then((list) => {
        setProjects(list);
        if (list.length > 0) setProjectName((current) => current || list[0].name);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const project = projects?.find((p) => p.name === projectName);

  async function analyze(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const session = await api.createSession(projectName, bug);
      navigate(`/sessions/${session.id}`);
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <div className="page narrow">
      <h1>Debug a bug</h1>
      <p className="lead">
        Pick a repository, describe the bug, and CodePilot will investigate and propose a fix. Nothing is written to your
        files until you approve the diff.
      </p>

      <form className="card form" onSubmit={analyze}>
        <label htmlFor="project">Repository</label>
        {projects === null && !error && <p className="muted">Loading projects…</p>}
        {projects?.length === 0 && (
          <p className="warning">
            No repositories found in the projects folder. Run <code>python -m app.demo</code> in <code>backend/</code> to
            create the demo project.
          </p>
        )}
        {projects && projects.length > 0 && (
          <select id="project" value={projectName} onChange={(e) => setProjectName(e.target.value)}>
            {projects.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
        )}

        {project && (
          <div className="project-meta">
            <span>{project.is_git_repo ? `Branch: ${project.branch}` : "Not a git repository"}</span>
            <span>Tests: {project.test_command ? <code>{project.test_command}</code> : "not detected"}</span>
          </div>
        )}
        {project && project.uncommitted_files.length > 0 && (
          <div className="warning">
            <strong>Uncommitted changes:</strong> {project.uncommitted_files.length} file(s) have local edits (
            {project.uncommitted_files.slice(0, 3).join(", ")}
            {project.uncommitted_files.length > 3 ? ", …" : ""}). Consider committing or stashing first so CodePilot's
            changes are easy to review.
          </div>
        )}

        <label htmlFor="bug">Bug report</label>
        <textarea
          id="bug"
          rows={5}
          value={bug}
          onChange={(e) => setBug(e.target.value)}
          placeholder="Describe what goes wrong, and when…"
        />
        <button type="button" className="link-button" onClick={() => setBug(EXAMPLE_BUG)}>
          Use example bug report
        </button>

        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button type="submit" className="primary" disabled={!projectName || bug.trim().length < 5 || submitting}>
            {submitting ? "Starting…" : "Analyze"}
          </button>
        </div>
      </form>
    </div>
  );
}

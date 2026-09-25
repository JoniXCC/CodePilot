import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { SessionDetail } from "../api/types";
import { DiffViewer } from "../components/DiffViewer";
import { StatusBadge } from "../components/StatusBadge";
import { TestResults } from "../components/TestResults";
import { Timeline } from "../components/Timeline";
import { useSessionEvents } from "../hooks/useSessionEvents";
import { CommitPanel } from "./CommitPanel";

export function SessionPage() {
  const { id = "" } = useParams();
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"approve" | "reject" | "cancel" | null>(null);

  const reload = useCallback(() => {
    api.getSession(id).then(setSession).catch((e: Error) => setError(e.message));
  }, [id]);

  useEffect(reload, [reload]);

  const live = session?.status === "running";
  const actions = useSessionEvents(id, session?.actions ?? EMPTY, live, reload);

  async function act(kind: "approve" | "reject" | "cancel") {
    setBusy(kind);
    setError(null);
    try {
      const call = { approve: api.approveSession, reject: api.rejectSession, cancel: api.cancelSession }[kind];
      setSession(await call(id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (!session) return <div className="page">{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</div>;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="breadcrumb">
            <Link to="/history">History</Link> / {session.project_name}
          </p>
          <h1>Agent session</h1>
        </div>
        <StatusBadge status={session.status} />
      </div>

      <blockquote className="bug-report">{session.bug_description}</blockquote>
      <p className="meta">
        {new Date(session.created_at).toLocaleString()} · {session.model ?? "unknown model"}
        {session.tool_calls > 0 && ` · ${session.tool_calls} tool calls · ${(session.duration_ms / 1000).toFixed(1)}s`}
      </p>

      {session.uncommitted_at_start.length > 0 && (
        <div className="warning">
          The repository had {session.uncommitted_at_start.length} uncommitted file(s) when this session started:{" "}
          {session.uncommitted_at_start.join(", ")}
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {session.error && session.status !== "running" && <p className="error">{session.error}</p>}

      <div className="columns">
        <section className="card">
          <div className="card-header">
            <h2>Agent activity</h2>
            {live && (
              <button onClick={() => act("cancel")} disabled={busy !== null}>
                {busy === "cancel" ? "Cancelling…" : "Cancel"}
              </button>
            )}
          </div>
          <Timeline actions={actions} live={live} />
        </section>

        <aside className="stack">
          <section className="card">
            <h2>Findings</h2>
            {session.hypothesis || session.root_cause ? (
              <dl className="findings">
                {session.root_cause ? (
                  <>
                    <dt>Root cause</dt>
                    <dd>{session.root_cause}</dd>
                  </>
                ) : (
                  <>
                    <dt>Hypothesis</dt>
                    <dd>{session.hypothesis}</dd>
                  </>
                )}
                {session.fix_explanation && (
                  <>
                    <dt>Proposed fix</dt>
                    <dd>{session.fix_explanation}</dd>
                  </>
                )}
              </dl>
            ) : (
              <p className="muted">{live ? "Investigating…" : "No findings recorded."}</p>
            )}
          </section>
          <section className="card">
            <h2>Files</h2>
            <h3>Inspected</h3>
            <FileList files={session.files_inspected} />
            <h3>Modified</h3>
            <FileList files={session.files_modified} />
          </section>
        </aside>
      </div>

      {session.status === "awaiting_approval" && (
        <section className="card highlight">
          <div className="card-header">
            <h2>Proposed changes</h2>
            <div className="actions">
              <button onClick={() => act("reject")} disabled={busy !== null}>
                {busy === "reject" ? "Rejecting…" : "Reject"}
              </button>
              <button className="primary" onClick={() => act("approve")} disabled={busy !== null}>
                {busy === "approve" ? "Applying & testing…" : "Approve & apply"}
              </button>
            </div>
          </div>
          {session.summary && <p className="summary">{session.summary}</p>}
          <p className="muted">These changes have not been written yet. Approving writes them and runs the tests.</p>
          <DiffViewer diff={session.proposed_diff} />
        </section>
      )}

      {session.status === "rejected" && (
        <section className="card">
          <h2>Rejected changes</h2>
          <p className="muted">Nothing was written to the repository.</p>
          <DiffViewer diff={session.proposed_diff} />
        </section>
      )}

      {session.status === "applied" && (
        <>
          <section className="card">
            <h2>Test results</h2>
            <TestResults command={session.test_command} passed={session.test_passed} output={session.test_output} />
          </section>
          <section className="card">
            <h2>Final Git diff</h2>
            {session.summary && <p className="summary">{session.summary}</p>}
            <DiffViewer diff={session.final_diff} />
          </section>
          <CommitPanel session={session} onCommitted={reload} />
        </>
      )}
    </div>
  );
}

const EMPTY: never[] = [];

function FileList({ files }: { files: string[] }) {
  if (files.length === 0) return <p className="muted">None</p>;
  return (
    <ul className="file-list">
      {files.map((file) => (
        <li key={file}>
          <code>{file}</code>
        </li>
      ))}
    </ul>
  );
}

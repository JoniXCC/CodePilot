import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { SessionSummary } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";

export function History() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listSessions().then(setSessions).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <h1>History</h1>
      {error && <p className="error">{error}</p>}
      {sessions?.length === 0 && (
        <p className="muted">
          No sessions yet. <Link to="/">Start one from the dashboard.</Link>
        </p>
      )}
      {sessions && sessions.length > 0 && (
        <div className="card table-card">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Project</th>
                <th>Bug</th>
                <th>Status</th>
                <th>Tests</th>
                <th className="num">Tool calls</th>
                <th className="num">Time</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <td className="nowrap">{new Date(s.created_at).toLocaleString()}</td>
                  <td>{s.project_name}</td>
                  <td>
                    <Link to={`/sessions/${s.id}`} className="truncate">
                      {s.bug_description}
                    </Link>
                  </td>
                  <td>
                    <StatusBadge status={s.status} />
                  </td>
                  <td>{s.test_passed === null ? "—" : s.test_passed ? "✓ Passed" : "✗ Failed"}</td>
                  <td className="num">{s.tool_calls}</td>
                  <td className="num">{(s.duration_ms / 1000).toFixed(1)}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

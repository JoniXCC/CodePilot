import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { EvalReport } from "../api/types";

function Stat({ label, value, total }: { label: string; value: number | string; total?: number }) {
  return (
    <div className="stat">
      <div className="stat-value">
        {value}
        {total !== undefined && <span className="stat-total">/{total}</span>}
      </div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

const tick = (ok: boolean) => (ok ? <span className="test-pass">✓</span> : <span className="test-fail">✗</span>);

export function Evaluation() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .latestEval()
      .then(setReport)
      .catch((e: Error) => (e instanceof ApiError && e.status === 404 ? setMissing(true) : setError(e.message)));
  }, []);

  return (
    <div className="page">
      <h1>Evaluation</h1>
      <p className="lead">
        CodePilot is scored on a set of small repositories with known bugs. Each case records whether the agent found the
        right file and line, and whether its patch makes the tests pass.
      </p>
      {error && <p className="error">{error}</p>}
      {missing && (
        <div className="card">
          <p>No evaluation results yet. From the <code>backend/</code> folder run:</p>
          <pre className="output">python -m app.evaluation</pre>
        </div>
      )}
      {report && (
        <>
          <p className="meta">
            {new Date(report.generated_at).toLocaleString()} · {report.provider}
            {report.model ? ` · ${report.model}` : ""}
            {report.provider === "reference" && " · reference fixes (harness check, not an LLM score)"}
          </p>
          <div className="stats">
            <Stat label="Cases" value={report.cases} />
            <Stat label="Correct file identified" value={report.correct_file} total={report.cases} />
            <Stat label="Correct bug location" value={report.correct_location} total={report.cases} />
            <Stat label="Successful fixes" value={report.successful_fixes} total={report.cases} />
            <Stat label="Tests pass after patch" value={report.tests_passed} total={report.cases} />
            <Stat label="Average tool calls" value={report.average_tool_calls.toFixed(1)} />
            <Stat label="Average time" value={`${(report.average_duration_ms / 1000).toFixed(1)}s`} />
          </div>
          <div className="card table-card">
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Expected file</th>
                  <th>File</th>
                  <th>Location</th>
                  <th>Tests</th>
                  <th>Fixed</th>
                  <th className="num">Tool calls</th>
                  <th className="num">Time</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {report.results.map((r) => (
                  <tr key={r.case_id}>
                    <td>
                      <strong>{r.case_id}</strong>
                      <div className="muted small">{r.bug_description}</div>
                    </td>
                    <td>
                      <code>{r.expected_file}</code>
                    </td>
                    <td>{tick(r.found_correct_file)}</td>
                    <td>{tick(r.found_bug_location)}</td>
                    <td>{tick(r.tests_passed)}</td>
                    <td>{tick(r.successful_fix)}</td>
                    <td className="num">{r.tool_calls}</td>
                    <td className="num">{(r.duration_ms / 1000).toFixed(1)}s</td>
                    <td className="small">
                      {r.error ?? (r.touched_protected_files ? "Edited protected test files" : r.status)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

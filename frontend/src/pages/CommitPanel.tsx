import { useState } from "react";
import { api } from "../api/client";
import type { SessionDetail } from "../api/types";

/** "Create commit": asks the backend for a suggested message, lets the user edit it, then commits. */
export function CommitPanel({ session, onCommitted }: { session: SessionDetail; onCommitted: () => void }) {
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (session.commit_sha) {
    return (
      <section className="card">
        <h2>Commit</h2>
        <p className="test-pass">
          ✓ Committed as <code>{session.commit_sha}</code>
        </p>
      </section>
    );
  }

  async function run<T>(task: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    try {
      return await task();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Commit</h2>
      <p className="muted">CodePilot never commits automatically. Only the modified files are included.</p>
      {message === null ? (
        <button onClick={() => run(async () => setMessage((await api.suggestCommitMessage(session.id)).message))} disabled={busy}>
          {busy ? "Writing message…" : "Create commit"}
        </button>
      ) : (
        <div className="form">
          <label htmlFor="commit-message">Commit message</label>
          <textarea id="commit-message" rows={4} value={message} onChange={(e) => setMessage(e.target.value)} />
          <div className="actions">
            <button onClick={() => setMessage(null)} disabled={busy}>
              Cancel
            </button>
            <button
              className="primary"
              disabled={busy || message.trim().length < 3}
              onClick={() => run(async () => {
                await api.commit(session.id, message);
                onCommitted();
              })}
            >
              {busy ? "Committing…" : "Commit"}
            </button>
          </div>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

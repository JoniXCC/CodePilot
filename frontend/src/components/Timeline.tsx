import { useState } from "react";
import type { Action } from "../api/types";

interface TimelineRow {
  key: string;
  kind: "tool" | "status" | "hypothesis" | "error" | "done";
  title: string;
  note?: string;
  state: "running" | "ok" | "warn" | "failed" | "info";
  detail?: string | null;
  durationMs?: number | null;
}

/** Merge each tool_started/tool_finished pair (same call_id) into one timeline row. */
function toRows(actions: Action[]): TimelineRow[] {
  const rows: TimelineRow[] = [];
  const toolRows = new Map<string, TimelineRow>();
  for (const action of actions) {
    if (action.type === "tool_started") {
      const row: TimelineRow = { key: `a${action.seq}`, kind: "tool", title: action.message, state: "running" };
      if (action.call_id) toolRows.set(action.call_id, row);
      rows.push(row);
    } else if (action.type === "tool_finished") {
      const row = action.call_id ? toolRows.get(action.call_id) : undefined;
      const update = {
        note: action.message !== row?.title ? action.message : undefined,
        // "warn": the tool worked but reported bad news, e.g. tests failing before the fix
        state: !action.success ? ("failed" as const) : action.warning ? ("warn" as const) : ("ok" as const),
        detail: action.detail,
        durationMs: action.duration_ms,
      };
      if (row) Object.assign(row, update);
      else rows.push({ key: `a${action.seq}`, kind: "tool", title: action.message, ...update });
    } else {
      rows.push({
        key: `a${action.seq}`,
        kind: action.type,
        title: action.message,
        state: action.type === "error" || action.success === false ? "failed" : "info",
      });
    }
  }
  return rows;
}

const ICONS = { running: "→", ok: "✓", warn: "!", failed: "✗", info: "•" };

function Row({ row }: { row: TimelineRow }) {
  const [open, setOpen] = useState(false);
  const expandable = Boolean(row.detail);
  return (
    <li className={`timeline-row timeline-${row.kind} state-${row.state}`}>
      <span className="timeline-icon" aria-hidden>
        {row.state === "running" ? <span className="spinner" /> : ICONS[row.state]}
      </span>
      <div className="timeline-body">
        <button
          type="button"
          className="timeline-title"
          onClick={() => expandable && setOpen(!open)}
          disabled={!expandable}
          aria-expanded={expandable ? open : undefined}
        >
          {row.kind === "hypothesis" && <strong>Hypothesis: </strong>}
          {row.title}
          {row.note && <span className="timeline-note"> — {row.note}</span>}
          {row.durationMs != null && <span className="timeline-duration">{row.durationMs} ms</span>}
        </button>
        {open && row.detail && <pre className="timeline-detail">{row.detail}</pre>}
      </div>
    </li>
  );
}

export function Timeline({ actions, live }: { actions: Action[]; live: boolean }) {
  const rows = toRows(actions);
  return (
    <ol className="timeline">
      {rows.map((row) => (
        <Row key={row.key} row={row} />
      ))}
      {live && rows.every((r) => r.state !== "running") && (
        <li className="timeline-row state-running">
          <span className="timeline-icon">
            <span className="spinner" />
          </span>
          <div className="timeline-body muted">Thinking about the next step…</div>
        </li>
      )}
    </ol>
  );
}

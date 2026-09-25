import type { SessionStatus } from "../api/types";

const LABELS: Record<SessionStatus, string> = {
  running: "Running",
  awaiting_approval: "Awaiting approval",
  applied: "Applied",
  rejected: "Rejected",
  no_changes: "No changes",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function StatusBadge({ status }: { status: SessionStatus }) {
  return <span className={`badge badge-${status}`}>{LABELS[status] ?? status}</span>;
}

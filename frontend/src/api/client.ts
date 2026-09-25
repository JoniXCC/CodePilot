import type { EvalReport, ProjectInfo, SessionDetail, SessionSummary } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      // non-JSON error body - keep the status text
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  listProjects: () => request<ProjectInfo[]>("/projects"),
  getProject: (name: string) => request<ProjectInfo>(`/projects/${encodeURIComponent(name)}`),

  createSession: (project: string, bugDescription: string) =>
    post<SessionDetail>("/sessions", { project, bug_description: bugDescription }),
  listSessions: () => request<SessionSummary[]>("/sessions"),
  getSession: (id: string) => request<SessionDetail>(`/sessions/${id}`),
  cancelSession: (id: string) => post<SessionDetail>(`/sessions/${id}/cancel`),
  approveSession: (id: string) => post<SessionDetail>(`/sessions/${id}/approve`),
  rejectSession: (id: string) => post<SessionDetail>(`/sessions/${id}/reject`),
  suggestCommitMessage: (id: string) => post<{ message: string }>(`/sessions/${id}/commit-message`),
  commit: (id: string, message: string) => post<{ sha: string; message: string }>(`/sessions/${id}/commit`, { message }),
  eventsUrl: (id: string) => `/api/sessions/${id}/events`,

  latestEval: () => request<EvalReport>("/evals/latest"),
};

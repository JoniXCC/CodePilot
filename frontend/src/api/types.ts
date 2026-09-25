// Mirrors the Pydantic response models in backend/app/schemas.

export type SessionStatus =
  | "running"
  | "awaiting_approval"
  | "applied"
  | "rejected"
  | "no_changes"
  | "failed"
  | "cancelled";

export interface ProjectInfo {
  name: string;
  is_git_repo: boolean;
  branch: string | null;
  uncommitted_files: string[];
  test_command: string | null;
}

export type ActionType = "status" | "tool_started" | "tool_finished" | "hypothesis" | "error" | "done";

export interface Action {
  seq: number;
  event_id: string;
  type: ActionType;
  message: string;
  tool: string | null;
  call_id: string | null;
  success: boolean | null;
  warning: boolean;
  detail: string | null;
  duration_ms: number | null;
  timestamp: string;
}

export interface SessionSummary {
  id: string;
  project_name: string;
  bug_description: string;
  status: SessionStatus;
  created_at: string;
  tool_calls: number;
  duration_ms: number;
  test_passed: boolean | null;
  files_modified: string[];
}

export interface SessionDetail extends SessionSummary {
  model: string | null;
  uncommitted_at_start: string[];
  hypothesis: string | null;
  summary: string | null;
  root_cause: string | null;
  fix_explanation: string | null;
  files_inspected: string[];
  proposed_diff: string | null;
  final_diff: string | null;
  test_command: string | null;
  test_output: string | null;
  commit_sha: string | null;
  input_tokens: number;
  output_tokens: number;
  error: string | null;
  actions: Action[];
}

export interface EvalCaseResult {
  case_id: string;
  bug_description: string;
  expected_file: string;
  status: string;
  tests_failed_before: boolean;
  found_correct_file: boolean;
  found_bug_location: boolean;
  patch_applied: boolean;
  tests_passed: boolean;
  touched_protected_files: boolean;
  successful_fix: boolean;
  tool_calls: number;
  duration_ms: number;
  files_modified: string[];
  error: string | null;
}

export interface EvalReport {
  generated_at: string;
  provider: string;
  model: string | null;
  cases: number;
  correct_file: number;
  correct_location: number;
  successful_fixes: number;
  tests_passed: number;
  average_tool_calls: number;
  average_duration_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  results: EvalCaseResult[];
}

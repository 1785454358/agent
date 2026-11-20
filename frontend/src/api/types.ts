/** 镜像后端 deeptrace.runtime.models 的公开字段。 */

export type ResearchMode = "workflow" | "plan_execute" | "multi_agent";
export type ResearchModeSelection = ResearchMode | "auto";

export type FinishReason =
  | "completed" | "partial" | "cancelled" | "budget_exhausted"
  | "iteration_limit" | "planning_limit" | "error_limit" | "context_limit"
  | "model_error" | "tool_error" | "response_error" | "runtime_error"
  | "interrupted" | "incomplete_plan" | "insufficient_evidence" | "no_progress" | "unknown";

export type ResearchSufficiency = "sufficient" | "insufficient" | "unknown" | "not_required";

export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "partial"
  | "failed"
  | "cancel_requested"
  | "cancelled";

/** 终态：轮询与 SSE 在这些状态后停止。 */
export const TERMINAL_STATUSES: readonly RunStatus[] = [
  "completed",
  "partial",
  "failed",
  "cancelled",
];

export function isTerminalStatus(status: RunStatus): boolean {
  return (TERMINAL_STATUSES as readonly string[]).includes(status);
}

export interface RunEvent {
  id?: number;
  event_type: string;
  message: string;
  ts?: string;
  tool?: string;
  details?: {
    tool?: string; call_id?: string; ok?: boolean; message?: string;
    error_code?: string; retryable?: boolean; url?: string; query?: string;
    round?: number; task?: string; tasks_json?: string; gaps_json?: string;
    reason?: string; action?: string; next_step?: string; covered?: number; total?: number;
    branch?: string; iteration?: number;
  };
}

export interface RunSummary {
  id: string;
  question: string;
  mode: ResearchModeSelection;
  status: RunStatus;
  created_at: string;
  thread_id: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

export interface RunDetail {
  id: string;
  question: string;
  mode: ResearchModeSelection;
  selected_mode?: ResearchMode | null;
  routing_reason?: string | null;
  status: RunStatus;
  thread_id: string;
  termination_reason: string;
  /** Older API deployments may omit these fields. */
  finish_reason?: FinishReason | null;
  research_sufficiency?: ResearchSufficiency;
  created_at: string;
  answer: string;
  sources: string[];
  search_queries: string[];
  unresolved_gaps: string[];
  events: RunEvent[];
  error: string | null;
  usage?: RunUsage | null;
}

export interface RunUsage {
  provider_attempts: number | null;
  total_tokens: number | null;
  missing_usage_attempts: number;
}

export interface CreateRunResponse {
  id: string;
  status: RunStatus;
  thread_id: string;
}

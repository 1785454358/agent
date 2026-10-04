/** 镜像后端 deeptrace.runtime.models 的公开字段。 */

export type ResearchMode = "workflow" | "plan_execute" | "multi_agent";

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
  mode: ResearchMode;
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
  mode: ResearchMode;
  status: RunStatus;
  thread_id: string;
  termination_reason: string;
  created_at: string;
  answer: string;
  sources: string[];
  search_queries: string[];
  unresolved_gaps: string[];
  events: RunEvent[];
  error: string | null;
}

export interface CreateRunResponse {
  id: string;
  status: RunStatus;
  thread_id: string;
}

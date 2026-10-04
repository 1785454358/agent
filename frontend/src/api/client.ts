import type {
  CreateRunResponse,
  ResearchMode,
  RunDetail,
  RunSummary,
} from "./types";

/** 统一 API 错误：携带状态码与后端 detail 文案。 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* 非 JSON 响应体，保留默认文案 */
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

export function listRuns(): Promise<RunSummary[]> {
  return request<RunSummary[]>("/researches");
}

export function getRun(runId: string): Promise<RunDetail> {
  return request<RunDetail>(`/researches/${runId}`);
}

export function createRun(
  question: string,
  mode: ResearchMode,
  threadId?: string,
): Promise<CreateRunResponse> {
  return request<CreateRunResponse>("/researches", {
    method: "POST",
    body: JSON.stringify({ question, mode, thread_id: threadId ?? null }),
  });
}

export function cancelRun(runId: string): Promise<{ id: string }> {
  return request<{ id: string }>(`/researches/${runId}/cancel`, {
    method: "POST",
  });
}

/** 批量删除结果：active/missing 表示被跳过的运行。 */
export interface DeleteRunsResult {
  deleted: string[];
  active: string[];
  missing: string[];
}

export function deleteRun(runId: string): Promise<{ id: string }> {
  return request<{ id: string }>(`/researches/${runId}`, {
    method: "DELETE",
  });
}

export function deleteRuns(runIds: string[]): Promise<DeleteRunsResult> {
  return request<DeleteRunsResult>("/researches/batch-delete", {
    method: "POST",
    body: JSON.stringify({ ids: runIds }),
  });
}

export function deleteAllRuns(): Promise<DeleteRunsResult> {
  return request<DeleteRunsResult>("/researches", { method: "DELETE" });
}

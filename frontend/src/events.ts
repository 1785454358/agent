/** 事件视觉分级：沿用单文件版的时间刻度轨语言。 */

export const MAJOR_EVENT_TYPES: ReadonlySet<string> = new Set([
  "planning.started",
  "planning.completed",
  "replanning.started",
  "replanning.completed",
  "plan.finish_rejected",
  "task.started",
  "supervisor.dispatched",
  "supervisor.retry",
  "supervisor.fallback",
  "supervisor.reviewed",
  "researcher.queued",
  "researcher.started",
  "researcher.completed",
  "tool.batch_limited",
  "research.completed",
  "writing.completed",
]);

export const FINAL_EVENT_TYPES: ReadonlySet<string> = new Set([
  "run.completed",
]);

export type EventLevel = "normal" | "major" | "final";

export function eventLevel(eventType: string): EventLevel {
  if (FINAL_EVENT_TYPES.has(eventType)) return "final";
  if (MAJOR_EVENT_TYPES.has(eventType)) return "major";
  return "normal";
}

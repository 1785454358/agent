import type { RunStatus } from "../api/types";

const STATUS_TEXT: Record<RunStatus, string> = {
  pending: "等待启动",
  running: "运行中",
  completed: "已完成",
  partial: "部分完成",
  failed: "失败",
  cancel_requested: "取消中",
  cancelled: "已取消",
};

interface StatusBarProps {
  status: RunStatus | null;
  runId: string | null;
  reconnecting: boolean;
  onCancel: (() => void) | null;
}

/** 状态点 + 文本 + run id + 取消按钮。 */
export function StatusBar({
  status,
  runId,
  reconnecting,
  onCancel,
}: StatusBarProps) {
  const state = status ?? "idle";
  const cancellable =
    status === "running" || status === "pending" || status === "cancel_requested";

  return (
    <div className={`statusline ${status ? state : ""}`}>
      <span className="dot" aria-hidden="true" />
      <span id="status">
        {status ? STATUS_TEXT[status] : "就绪"}
        {reconnecting && status === "running" ? "（连接中断，重连中…）" : ""}
      </span>
      {runId && <span className="runid">{runId}</span>}
      {cancellable && onCancel && (
        <button className="cancel" onClick={onCancel}>
          取消运行
        </button>
      )}
    </div>
  );
}

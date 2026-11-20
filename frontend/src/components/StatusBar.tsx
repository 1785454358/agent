import { isTerminalStatus, type ResearchMode, type ResearchModeSelection, type RunStatus, type RunUsage } from "../api/types";

const MODE_LABELS: Record<ResearchMode, string> = {
  workflow: "Workflow", plan_execute: "Plan-and-Execute", multi_agent: "Multi-Agent",
};

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
  usage?: RunUsage | null;
  mode?: ResearchModeSelection;
  selectedMode?: ResearchMode | null;
  routingReason?: string | null;
}

/** 状态点 + 文本 + run id + 取消按钮。 */
export function StatusBar({
  status,
  runId,
  reconnecting,
  onCancel,
  usage,
  mode,
  selectedMode,
  routingReason,
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
      {mode && <span className="routing-info">
        <span>{selectedMode
          ? `${mode === "auto" ? "自动选择" : "研究模式"}：${MODE_LABELS[selectedMode]}`
          : mode === "auto"
            ? status && isTerminalStatus(status) ? "未选择研究模式" : "正在选择研究模式…"
            : `研究模式：${MODE_LABELS[mode]}`}</span>
        {routingReason && <span className="runid">{routingReason}</span>}
      </span>}
      {usage && (
        <span className="runid">
          {usage.provider_attempts == null
            ? "模型调用次数未知"
            : `${usage.provider_attempts} 次模型调用`}
          {" · "}
          {usage.total_tokens == null || usage.missing_usage_attempts > 0
            ? "Token 用量不完整"
            : `${usage.total_tokens} token`}
        </span>
      )}
      {cancellable && onCancel && (
        <button className="cancel" onClick={onCancel}>
          取消运行
        </button>
      )}
    </div>
  );
}

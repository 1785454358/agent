import type { RunSummary } from "../api/types";
import {
  IconChevronLeft,
  IconClock,
  IconDoc,
  IconPlus,
} from "./icons";

interface RunHistoryProps {
  runs: RunSummary[];
  selectedId: string | null;
  onSelect: (runId: string) => void;
  onNewResearch: () => void;
  collapsed: boolean;
  onToggle: () => void;
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days <= 0) return "今天";
  if (days === 1) return "1 天前";
  return `${days} 天前`;
}

/** 全页面左侧边栏：展开为研究历史，收起为窄图标轨。 */
export function RunHistory({
  runs,
  selectedId,
  onSelect,
  onNewResearch,
  collapsed,
  onToggle,
}: RunHistoryProps) {
  if (collapsed) {
    return (
      <aside className="history rail" aria-label="研究历史（已收起）">
        <button
          type="button"
          className="rail-expand"
          title="展开研究历史"
          aria-label="展开研究历史"
          onClick={onToggle}
        >
          <IconDoc size={20} />
        </button>
      </aside>
    );
  }

  return (
    <aside className="history" aria-label="研究历史">
      <div className="history-head">
        <span className="history-title">Research History</span>
        <button
          type="button"
          className="history-toggle"
          title="收起侧边栏"
          aria-label="收起侧边栏"
          onClick={onToggle}
        >
          <IconChevronLeft size={16} />
        </button>
      </div>
      <button type="button" className="new-research" onClick={onNewResearch}>
        <IconPlus size={17} />
        新研究
      </button>
      <div className="history-list">
        {runs.length === 0 && <div className="history-empty">暂无运行记录</div>}
        <ul>
          {runs.map((run) => (
            <li key={run.id}>
              <button
                type="button"
                className={`history-item${
                  run.id === selectedId ? " selected" : ""
                } status-${run.status}`}
                onClick={() => onSelect(run.id)}
              >
                <span className="history-q" title={run.question}>
                  {run.question}
                </span>
                <span className="history-meta">
                  <IconClock size={13} />
                  {timeAgo(run.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

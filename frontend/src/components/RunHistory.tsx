import type { RunSummary } from "../api/types";

interface RunHistoryProps {
  runs: RunSummary[];
  selectedId: string | null;
  onSelect: (runId: string) => void;
}

const MODE_LABEL: Record<string, string> = {
  workflow: "Workflow",
  plan_execute: "Plan-Exec",
  multi_agent: "Multi-Agent",
  basic: "Workflow",
  deep: "Plan-Exec",
};

/** 左侧运行历史列表。 */
export function RunHistory({ runs, selectedId, onSelect }: RunHistoryProps) {
  return (
    <aside className="history" aria-label="运行历史">
      <div className="block-label">运行历史</div>
      {runs.length === 0 && <div className="history-empty">暂无运行</div>}
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
                <span className="history-mode">
                  {MODE_LABEL[run.mode] ?? run.mode}
                </span>
                <span className="history-badge">{run.status}</span>
                <span className="history-time">
                  {run.created_at.slice(11, 19)}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

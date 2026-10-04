import { useEffect, useState } from "react";
import { isTerminalStatus, type RunSummary } from "../api/types";
import {
  IconCheck,
  IconChevronLeft,
  IconClock,
  IconDoc,
  IconPlus,
  IconTrash,
} from "./icons";

interface RunHistoryProps {
  runs: RunSummary[];
  selectedId: string | null;
  onSelect: (runId: string) => void;
  onNewResearch: () => void;
  /** 删除目标：运行 ID 列表，或 "all" 表示清空全部历史。 */
  onDelete: (target: string[] | "all") => void;
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
  onDelete,
  collapsed,
  onToggle,
}: RunHistoryProps) {
  const [managing, setManaging] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());

  const runIds = new Set(runs.map((run) => run.id));

  const exitManaging = () => {
    setManaging(false);
    setChecked(new Set());
  };

  // 列表刷新后丢弃已不存在的勾选项；历史清空时自动退出批量模式
  useEffect(() => {
    setChecked((prev) => {
      const next = new Set([...prev].filter((id) => runIds.has(id)));
      return next.size === prev.size ? prev : next;
    });
    if (managing && runs.length === 0) {
      exitManaging();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs]);

  const allChecked = runs.length > 0 && checked.size === runs.length;

  const toggleChecked = (runId: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) {
        next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
  };

  const deleteOne = (run: RunSummary) => {
    if (!window.confirm(`删除这条研究记录？\n「${run.question}」`)) return;
    onDelete([run.id]);
  };

  const deleteChecked = () => {
    if (checked.size === 0) return;
    if (!window.confirm(`删除选中的 ${checked.size} 条研究记录？`)) return;
    onDelete([...checked]);
    exitManaging();
  };

  const deleteAll = () => {
    if (!window.confirm("清空全部研究历史？该操作不可恢复。")) return;
    onDelete("all");
  };

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
      <div className="history-actions">
        {managing ? (
          <>
            <button
              type="button"
              className="history-action"
              onClick={() =>
                setChecked(
                  allChecked
                    ? new Set()
                    : new Set(runs.map((run) => run.id)),
                )
              }
            >
              {allChecked ? "取消全选" : "全选"}
            </button>
            <button
              type="button"
              className="history-action danger"
              onClick={deleteChecked}
              disabled={checked.size === 0}
            >
              删除所选{checked.size > 0 ? ` (${checked.size})` : ""}
            </button>
            <button type="button" className="history-action" onClick={exitManaging}>
              退出
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className="history-action"
              onClick={() => setManaging(true)}
              disabled={runs.length === 0}
            >
              批量管理
            </button>
            <button
              type="button"
              className="history-action danger"
              onClick={deleteAll}
              disabled={runs.length === 0}
            >
              清空历史
            </button>
          </>
        )}
      </div>
      <div className="history-list">
        {runs.length === 0 && <div className="history-empty">暂无运行记录</div>}
        <ul>
          {runs.map((run) => {
            const isChecked = checked.has(run.id);
            return (
              <li
                key={run.id}
                className={`history-row${isChecked ? " checked" : ""}`}
              >
                <button
                  type="button"
                  className={`history-item${
                    run.id === selectedId ? " selected" : ""
                  }${isChecked ? " is-checked" : ""} status-${run.status}`}
                  onClick={() =>
                    managing ? toggleChecked(run.id) : onSelect(run.id)
                  }
                  aria-pressed={managing ? isChecked : undefined}
                >
                  <span className="history-item-main">
                    {managing && (
                      <span
                        className={`history-check${isChecked ? " on" : ""}`}
                        aria-hidden="true"
                      >
                        {isChecked && <IconCheck size={12} />}
                      </span>
                    )}
                    <span className="history-q" title={run.question}>
                      {run.question}
                    </span>
                  </span>
                  <span className="history-meta">
                    <IconClock size={13} />
                    {timeAgo(run.created_at)}
                  </span>
                </button>
                {!managing && isTerminalStatus(run.status) && (
                  <button
                    type="button"
                    className="history-item-delete"
                    title="删除该记录"
                    aria-label={`删除研究：${run.question}`}
                    onClick={() => deleteOne(run)}
                  >
                    <IconTrash size={15} />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}

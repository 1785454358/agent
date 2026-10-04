import { useMemo } from "react";
import type { RunEvent, RunStatus } from "../api/types";
import { IconBookOpen, IconCheckCircle, IconCompass, IconPen, IconSearch, IconChat, IconActivity } from "./icons";
import { buildResearchProgress, researchStopReason, type ResearchOperation } from "./researchProgress";

interface EventTimelineProps {
  events: RunEvent[];
  status?: RunStatus | null;
  terminationReason?: string;
}

const STATUS_LABEL: Record<RunStatus, string> = {
  pending: "等待开始", running: "研究进行中", completed: "已结束 · 已完成",
  partial: "已结束 · 部分完成", failed: "已结束 · 执行失败",
  cancel_requested: "正在停止", cancelled: "已结束 · 已取消",
};
const OPERATION_LABEL = { running: "进行中", done: "已完成", returned: "已返回", recorded: "已记录", failed: "未成功", retry: "正在重试", retried: "发生过重试" };
const STAGE_LABEL = { active: "当前阶段", recorded: "已记录", unrecorded: "未记录" };
const STAGE_ICONS = { prepare: IconChat, plan: IconCompass, search: IconSearch, read: IconBookOpen, review: IconCheckCircle, write: IconPen };

function eventTime(ts?: string) {
  if (!ts) return "";
  const date = new Date(ts);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function OperationList({ operations, compact = false }: { operations: ResearchOperation[]; compact?: boolean }) {
  return (
    <ol className="research-operations" aria-label={compact ? "研究操作" : "完整研究操作"}>
      {operations.map((operation, i) => {
        const Icon = operation.stage ? STAGE_ICONS[operation.stage] : IconActivity;
        return (
          <li key={`${operation.key}-${i}`} className={`research-operation is-${operation.state}${operation.boundary ? " is-plan-boundary" : ""}`}>
            <span className="operation-marker" aria-hidden="true"><Icon size={17} /></span>
            <div className="operation-content">
              <div className="operation-title"><strong>{operation.title}</strong><span className="operation-state">{OPERATION_LABEL[operation.state]}</span>
                {compact && !!operation.failedCalls && <span className="operation-state">{operation.failedCalls} 次未成功</span>}
              </div>
              <p>{operation.description}</p>
              {!compact && !!operation.tasks?.length && <ol className="operation-tasks" aria-label="本轮研究任务">{operation.tasks.map((task, index) => <li key={index}>{task}</li>)}</ol>}
              {!compact && !!operation.gaps?.length && <details className="operation-gaps" open={operation.boundary || undefined}><summary>待补充的证据（{operation.gaps.length} 项）</summary><ul>{operation.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul></details>}
            </div>
            {!compact && <div className="operation-meta">
              <time dateTime={operation.time}>{eventTime(operation.time)}</time>
              {operation.endedTime && eventTime(operation.endedTime) !== eventTime(operation.time) && <time dateTime={operation.endedTime}>至 {eventTime(operation.endedTime)}</time>}
              {operation.completedCalls > 1 && <span>{operation.completedCalls} 次调用完成</span>}
            </div>}
          </li>
        );
      })}
    </ol>
  );
}

export function EventTimeline({ events, status, terminationReason }: EventTimelineProps) {
  const { stages, operations, summary } = useMemo(() => buildResearchProgress(events, status), [events, status]);
  const hasPlan = events.some(event => event.event_type === "planning.started" || event.event_type === "planning.completed");
  const stopReason = researchStopReason(terminationReason);
  return (
    <section className="events-block">
      <div className="section-head">
        <span className="section-head-icon tone-teal" aria-hidden="true"><IconCompass size={17} /></span>
        <h2 className="section-title">研究流程</h2>
        <span className={`research-run-state${status === "running" ? " is-live" : ""}`}>{status ? STATUS_LABEL[status] : "过程记录"}</span>
      </div>
      <div className="research-progress">
        <ol className="research-stages" aria-label="研究阶段">
          {stages.map((stage, i) => (
            <li key={stage.id} data-state={stage.state} aria-current={stage.state === "active" ? "step" : undefined}>
              <span className="stage-number" aria-hidden="true">{stage.state === "recorded" ? <IconCheckCircle size={15} /> : String(i+1).padStart(2,"0")}</span>
              <strong>{stage.label}</strong>
              <small>{STAGE_LABEL[stage.state as keyof typeof STAGE_LABEL]}</small>
            </li>
          ))}
        </ol>
        <div className="research-operations-head"><span>研究操作</span><small>按研究轮次汇总</small></div>
        {operations.length === 0 && <p className="timeline-empty">提交问题后，可在这里查看研究进度。</p>}
        <OperationList operations={summary} compact />
        {operations.length > 0 && <details className="research-operation-details">
          <summary>查看操作详情（{operations.length} 项）</summary>
          {!hasPlan && <p className="research-record-note">这份记录未保存规划节点，以下展示已记录的真实操作。</p>}
          <OperationList operations={operations} />
          {stopReason && <p className="research-stop-note"><strong>取材结束原因</strong>{stopReason}</p>}
        </details>}
        <details className="research-raw-records">
          <summary>查看原始记录（{events.length} 条）</summary>
          <ol>{events.slice(-200).map((event,i) => <li key={`${event.id ?? "stored"}-${i}`}><time dateTime={event.ts}>{eventTime(event.ts)}</time><code>{event.event_type}</code>{(event.tool ?? event.details?.tool) && <code className="raw-tool-name">{event.tool ?? event.details?.tool}</code>}<p>{event.message}</p>{event.details && Object.keys(event.details).length > 0 && <pre>{JSON.stringify(event.details, null, 2)}</pre>}</li>)}</ol>
          {events.length>200 && <p>这里只展示最近 200 条记录。</p>}
        </details>
      </div>
    </section>
  );
}

import { useEffect, useRef } from "react";
import type { RunEvent } from "../api/types";
import {
  IconActivity,
  IconAlert,
  IconBookOpen,
  IconChat,
  IconClipboard,
  IconCompass,
  IconDatabase,
  IconGlobe,
  IconGauge,
  IconNetwork,
  IconPen,
  IconRobot,
  IconRocket,
  IconSearch,
  IconCheckCircle,
  IconWrench,
} from "./icons";

interface EventTimelineProps {
  events: RunEvent[];
}

type TileTone =
  | "sky"
  | "emerald"
  | "fuchsia"
  | "violet"
  | "indigo"
  | "cyan"
  | "amber"
  | "orange"
  | "green"
  | "teal"
  | "slate"
  | "red";

interface EventVisual {
  Icon: typeof IconActivity;
  tone: TileTone;
}

/**
 * 按研究阶段/工具类型分配图标与色调，避免所有事件使用同一种 glyph。
 * 失败类消息统一走告警红色。
 */
function eventVisual(event: RunEvent): EventVisual {
  const type = event.event_type;
  const failed = event.message.includes("失败");

  if (failed) return { Icon: IconAlert, tone: "red" };

  if (type.startsWith("tool.")) {
    switch (event.tool) {
      case "search_web":
        return { Icon: IconSearch, tone: "sky" };
      case "fetch_page":
        return { Icon: IconGlobe, tone: "emerald" };
      case "search_memory":
        return { Icon: IconDatabase, tone: "fuchsia" };
      default:
        return { Icon: IconWrench, tone: "slate" };
    }
  }

  if (type === "tool.batch_limited") return { Icon: IconGauge, tone: "amber" };
  if (
    type.startsWith("planning") ||
    type.startsWith("replanning") ||
    type.startsWith("plan.")
  )
    return { Icon: IconCompass, tone: "violet" };
  if (type.startsWith("supervisor"))
    return { Icon: IconNetwork, tone: "indigo" };
  if (type.startsWith("researcher")) return { Icon: IconRobot, tone: "cyan" };
  if (type.startsWith("task.")) return { Icon: IconClipboard, tone: "sky" };
  if (type === "research.completed")
    return { Icon: IconBookOpen, tone: "green" };
  if (type.startsWith("writing")) return { Icon: IconPen, tone: "orange" };
  if (type === "run.started") return { Icon: IconRocket, tone: "teal" };
  if (type === "response.completed" || type === "run.completed")
    return { Icon: IconCheckCircle, tone: "green" };
  return { Icon: IconActivity, tone: "slate" };
}

const FINAL_EVENTS = new Set(["response.completed", "run.completed"]);

/** 研究事件卡片流：AGENT WORK 面板 + 自动滚动。 */
export function EventTimeline({ events }: EventTimelineProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "nearest" });
  }, [events.length]);

  return (
    <section className="events-block">
      <div className="section-head">
        <span className="section-head-icon tone-teal" aria-hidden="true">
          <IconChat size={17} />
        </span>
        <h2 className="section-title">研究事件</h2>
      </div>
      <div className="agent-work">
        {events.length === 0 && (
          <div className="timeline-empty">（等待运行）</div>
        )}
        {events.map((event) => {
          const { Icon, tone } = eventVisual(event);
          return (
            <div
              key={event.id}
              className={`event-card${
                FINAL_EVENTS.has(event.event_type) ? " level-final" : ""
              }`}
              title={`${(event.ts ?? "").slice(11, 19)} ${event.event_type}`}
            >
              <span className={`event-icon tone-${tone}`} aria-hidden="true">
                <Icon size={16} />
              </span>
              <span className="event-text">{event.message}</span>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </section>
  );
}

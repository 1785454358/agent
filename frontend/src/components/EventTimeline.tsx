import { useEffect, useRef } from "react";
import { eventLevel } from "../events";
import type { RunEvent } from "../api/types";

interface EventTimelineProps {
  events: RunEvent[];
}

/** 时间刻度轨：normal / major / final 三级视觉。 */
export function EventTimeline({ events }: EventTimelineProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "nearest" });
  }, [events.length]);

  return (
    <section className="events-block">
      <div className="block-label">研究事件</div>
      <div className="timeline">
        {events.length === 0 && (
          <div className="timeline-empty">（等待运行）</div>
        )}
        {events.map((event) => {
          const level = eventLevel(event.event_type);
          return (
            <div key={event.id} className={`event ${level}`}>
              <span className="ts">{(event.ts ?? "").slice(11, 19)}</span>
              <span className="etype">{event.event_type}</span>
              {event.message}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </section>
  );
}

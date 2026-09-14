import { useEffect, useRef, useState } from "react";
import type { RunEvent } from "../api/types";

interface UseRunEventsResult {
  events: RunEvent[];
  /** SSE 连接处于断开重连中。 */
  reconnecting: boolean;
}

/**
 * 进行中运行的实时事件流。
 *
 * 断线依赖浏览器原生 EventSource 重连（后端按 Last-Event-ID 续传），
 * 收到 done 事件后主动关闭。
 */
export function useRunEvents(
  runId: string | null,
  live: boolean,
): UseRunEventsResult {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [reconnecting, setReconnecting] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    setEvents([]);
    setReconnecting(false);
    if (!runId || !live) return;

    const es = new EventSource(`/researches/${runId}/events`);
    esRef.current = es;

    es.onmessage = (e: MessageEvent<string>) => {
      setReconnecting(false);
      try {
        const item = JSON.parse(e.data) as RunEvent;
        setEvents((prev) => [...prev, item]);
      } catch {
        /* 忽略无法解析的帧 */
      }
    };
    es.addEventListener("done", () => {
      es.close();
      esRef.current = null;
    });
    es.onerror = () => {
      // done 事件触发 close 后 readyState 为 CLOSED，不算重连
      if (es.readyState === EventSource.CONNECTING) {
        setReconnecting(true);
      }
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [runId, live]);

  return { events, reconnecting };
}

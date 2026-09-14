import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useRunEvents } from "./useRunEvents";

/** EventSource 测试替身：jsdom 没有原生实现。 */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  static readonly CONNECTING = 0;
  url: string;
  readyState = FakeEventSource.CONNECTING;
  onmessage: ((e: { data: string }) => void) | null = null;
  close = vi.fn(() => {
    this.readyState = 2;
  });
  private listeners = new Map<string, () => void>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: () => void) {
    this.listeners.set(type, handler);
  }

  emit(type: string, payload?: string) {
    if (type === "message") this.onmessage?.({ data: payload ?? "{}" });
    else this.listeners.get(type)?.();
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useRunEvents", () => {
  it("appends parsed events in order", () => {
    const { result } = renderHook(() => useRunEvents("run-1", true));
    const es = FakeEventSource.instances[0];
    expect(es.url).toBe("/researches/run-1/events");

    act(() => es.emit("message", JSON.stringify({ id: 1, event_type: "planning.completed", message: "计划" })));
    act(() => es.emit("message", JSON.stringify({ id: 2, event_type: "task.started", message: "任务" })));

    expect(result.current.events.map((e) => e.id)).toEqual([1, 2]);
    expect(result.current.reconnecting).toBe(false);
  });

  it("closes the stream after the done event", () => {
    renderHook(() => useRunEvents("run-1", true));
    const es = FakeEventSource.instances[0];

    act(() => es.emit("done"));

    expect(es.close).toHaveBeenCalled();
  });

  it("closes the stream on unmount", () => {
    const { unmount } = renderHook(() => useRunEvents("run-1", true));
    const es = FakeEventSource.instances[0];

    unmount();

    expect(es.close).toHaveBeenCalled();
  });

  it("does not open a connection for historical runs", () => {
    renderHook(() => useRunEvents("run-1", false));
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});

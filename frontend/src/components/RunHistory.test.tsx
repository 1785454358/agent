import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { RunHistory } from "./RunHistory";
import type { RunSummary } from "../api/types";

const now = new Date().toISOString();

const runs: RunSummary[] = [
  {
    id: "run-1",
    question: "问题一",
    mode: "workflow",
    status: "completed",
    created_at: now,
    thread_id: "t1",
  },
  {
    id: "run-2",
    question: "问题二",
    mode: "workflow",
    status: "failed",
    created_at: now,
    thread_id: "t2",
  },
  {
    id: "run-3",
    question: "问题三",
    mode: "workflow",
    status: "running",
    created_at: now,
    thread_id: "t3",
  },
];

function setup() {
  const handlers = {
    onSelect: vi.fn(),
    onNewResearch: vi.fn(),
    onDelete: vi.fn(),
    onToggle: vi.fn(),
  };
  render(
    <RunHistory
      runs={runs}
      selectedId={null}
      onSelect={handlers.onSelect}
      onNewResearch={handlers.onNewResearch}
      onDelete={handlers.onDelete}
      collapsed={false}
      onToggle={handlers.onToggle}
    />,
  );
  return handlers;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("RunHistory 删除", () => {
  it("确认后回调要删除的单个 ID", () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { onDelete } = setup();

    fireEvent.click(screen.getByRole("button", { name: "删除研究：问题一" }));

    expect(onDelete).toHaveBeenCalledWith(["run-1"]);
  });

  it("取消确认时不触发删除", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { onDelete } = setup();

    fireEvent.click(screen.getByRole("button", { name: "删除研究：问题一" }));

    expect(onDelete).not.toHaveBeenCalled();
  });

  it("进行中的运行不显示删除按钮", () => {
    setup();

    expect(
      screen.queryByRole("button", { name: "删除研究：问题三" }),
    ).toBeNull();
  });

  it("批量模式勾选后删除所选，且不触发选中回调", () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { onDelete, onSelect } = setup();

    fireEvent.click(screen.getByRole("button", { name: "批量管理" }));
    fireEvent.click(screen.getByRole("button", { name: /问题一/ }));
    fireEvent.click(screen.getByRole("button", { name: /问题二/ }));
    fireEvent.click(screen.getByRole("button", { name: /删除所选/ }));

    expect(onDelete).toHaveBeenCalledWith(["run-1", "run-2"]);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("清空历史回调 all", () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { onDelete } = setup();

    fireEvent.click(screen.getByRole("button", { name: "清空历史" }));

    expect(onDelete).toHaveBeenCalledWith("all");
  });

  it("无运行记录时管理操作不可用", () => {
    const handlers = {
      onSelect: vi.fn(),
      onNewResearch: vi.fn(),
      onDelete: vi.fn(),
      onToggle: vi.fn(),
    };
    render(
      <RunHistory
        runs={[]}
        selectedId={null}
        onSelect={handlers.onSelect}
        onNewResearch={handlers.onNewResearch}
        onDelete={handlers.onDelete}
        collapsed={false}
        onToggle={handlers.onToggle}
      />,
    );

    expect(screen.getByRole("button", { name: "批量管理" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "清空历史" })).toBeDisabled();
  });
});

import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { EventTimeline } from "./EventTimeline";

function detailOperations() {
  fireEvent.click(screen.getByText(/查看操作详情/));
  return screen.getByRole("list", { name: "完整研究操作" });
}

describe("EventTimeline", () => {
  it("shows a compact stage list while the tool calls stay collapsed", () => {
    const events = Array.from({ length: 12 }, () => [
      { event_type: "tool.completed", message: "搜索完成", tool: "search_web" },
      { event_type: "tool.completed", message: "抓取完成", tool: "fetch_page" },
    ]).flat();
    render(<EventTimeline events={events} status="partial" />);
    const summary = screen.getByRole("list", { name: "研究操作" });
    expect(summary.children.length).toBeLessThanOrEqual(6);
    expect(within(summary).getByText("检索资料")).toBeInTheDocument();
    expect(within(summary).getByText("阅读原文")).toBeInTheDocument();
    expect(within(summary).queryByText("抓取网页内容")).toBeNull();
    const details = screen.getByText(/查看操作详情/).closest("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(detailOperations().children.length).toBe(24);
  });
  it("renders the tasks and evidence gap of a supplemental round", () => {
    render(<EventTimeline events={[
      { event_type: "planning.completed", message: "计划完成", details: { round: 1, tasks_json: '["基础理论"]' } },
      { event_type: "evaluation.completed", message: "核对结束", details: { round: 1, total: 3, covered: 1, gaps_json: '["需要实验验证"]' } },
      { event_type: "replanning.completed", message: "计划调整完成", details: { round: 2, tasks_json: '["查阅实验论文"]' } },
    ]} status="running" />);
    const operations = detailOperations();
    expect(screen.getByText("第 1 轮补查 · 计划已生成")).toBeInTheDocument();
    expect(screen.getByText("查阅实验论文")).toBeInTheDocument();
    expect(within(operations).getByText("本轮 1/3 项研究需求已有原文支持")).toBeInTheDocument();
    fireEvent.click(screen.getByText("待补充的证据（1 项）"));
    expect(screen.getByText("需要实验验证")).toBeVisible();
  });
  it("turns persisted tools into Chinese operations and keeps raw records available", () => {
    const events = [
      { event_type: "agent.context_view", message: "agent.context_view" },
      { event_type: "tool.started", message: "正在read_evidence…", details: { tool: "read_evidence" } },
      { event_type: "agent.tool_observation", message: "agent.tool_observation", details: { tool: "read_evidence" } },
      { event_type: "tool.completed", message: "read_evidence完成", details: { tool: "read_evidence" } },
      { event_type: "agent.context_view", message: "agent.context_view" },
    ];
    render(<EventTimeline events={events} status="running" />);
    expect(screen.getByRole("heading", { name: "研究流程" })).toBeInTheDocument();
    const operations = detailOperations();
    expect(within(operations).getAllByText("阅读原文证据")).toHaveLength(1);
    expect(operations.textContent).not.toMatch(/agent\.|read_evidence/);
    expect(within(operations).getByText("已完成")).toBeInTheDocument();
    const raw = screen.getByText(/查看原始记录/).closest("details")!;
    expect(raw).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText(/查看原始记录/));
    expect(raw).toHaveAttribute("open");
    expect(within(raw).getAllByText("agent.context_view").length).toBeGreaterThan(0);
  });

  it("does not invent stages or promote a partial outcome to completion", () => {
    render(<EventTimeline events={[
      { id: 1, event_type: "tool.completed", message: "网页搜索完成", tool: "search_web" },
      { id: 2, event_type: "response.completed", message: "研究部分完成" },
    ]} status="partial" />);
    expect(screen.getByText("已结束 · 部分完成")).toBeInTheDocument();
    const stages = screen.getByRole("list", { name: "研究阶段" });
    expect(within(stages).getByText("制定计划").closest("li")).toHaveAttribute("data-state", "unrecorded");
    expect(within(stages).getByText("阅读原文").closest("li")).toHaveAttribute("data-state", "unrecorded");
    expect(within(stages).getByText("生成回答").closest("li")).toHaveAttribute("data-state", "recorded");
    expect(screen.queryByText("研究已完成")).not.toBeInTheDocument();
  });

  it("keeps failure and retry visible without calling them completed", () => {
    render(<EventTimeline events={[
      { id: 1, event_type: "tool.completed", message: "网页抓取失败（timeout）", tool: "fetch_page" },
      { id: 2, event_type: "tool.retry", message: "网页抓取调用失败，正在重试…", tool: "fetch_page" },
    ]} status="running" />);
    const operations=detailOperations();
    expect(within(operations).getByText("未成功")).toBeInTheDocument();
    expect(within(operations).getByText("正在重试")).toBeInTheDocument();
    expect(within(operations).queryByText("已完成")).toBeNull();
  });

  it("shows unknown events in Chinese and leaves the technical name in details", () => {
    render(<EventTimeline events={[{ id: 1, event_type: "future.event", message: "future.event" }]} status="running" />);
    expect(screen.getByRole("list", { name: "研究操作" }).textContent).not.toContain("future.event");
    detailOperations();
    expect(screen.getByText("其他运行记录")).toBeInTheDocument();
  });

  it("keeps the whole research path visible when a long run repeats evidence review", () => {
    const events = [
      { id: 1, event_type: "tool.completed", message: "网页搜索完成", tool: "search_web" },
      { id: 2, event_type: "tool.completed", message: "网页抓取完成", tool: "fetch_page" },
      ...Array.from({ length: 10 }, (_, i) => ({ id: i+3, event_type: i%2 ? "response.excerpts" : "evidence.view", message: i%2 ? "response.excerpts" : "evidence.view" })),
      { id: 13, event_type: "response.completed", message: "研究部分完成" },
    ];
    render(<EventTimeline events={events} status="partial" />);
    expect(screen.getByRole("list", { name: "研究操作" }).children.length).toBeLessThanOrEqual(6);
    const operations=detailOperations();
    expect(within(operations).getByText("搜索网页资料")).toBeInTheDocument();
    expect(within(operations).getByText("抓取网页内容")).toBeInTheDocument();
    expect(operations.querySelectorAll("li").length).toBe(13);
  });

  it("shows a return to search as the current stage and ignores replayed event ids", () => {
    render(<EventTimeline events={[
      { id: 1, event_type: "tool.completed", tool: "search_web", message: "网页搜索完成" },
      { id: 1, event_type: "tool.completed", tool: "search_web", message: "网页搜索完成" },
      { id: 2, event_type: "evidence.view", message: "evidence.view" },
      { id: 3, event_type: "tool.started", tool: "search_web", message: "正在网页搜索…" },
    ]} status="running" />);
    const stages=screen.getByRole("list", { name: "研究阶段" });
    expect(within(stages).getByText("检索资料").closest("li")).toHaveAttribute("aria-current", "step");
    expect(within(stages).getByText("核对证据").closest("li")).not.toHaveAttribute("aria-current");
    const operations=detailOperations();
    expect(within(operations).getAllByText("搜索网页资料")).toHaveLength(2);
  });

  it("retains retries in a terminal run without claiming they are still running", () => {
    render(<EventTimeline events={[
      { id: 1, event_type: "tool.retry", tool: "fetch_page", message: "网页抓取调用失败，正在重试…" },
    ]} status="failed" />);
    expect(within(detailOperations()).getByText("发生过重试")).toBeInTheDocument();
    expect(screen.queryByText("正在重试")).toBeNull();
  });
});

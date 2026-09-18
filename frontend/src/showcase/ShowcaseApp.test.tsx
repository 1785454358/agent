import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ShowcaseApp } from "./ShowcaseApp";
import { SHOWCASE_SCENARIOS } from "./fixtures";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("ShowcaseApp", () => {
  it("renders the Plan-and-Execute fixture without network access", () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("network must stay unused"));
    const eventSource = vi.fn();
    vi.stubGlobal("EventSource", eventSource);

    render(<ShowcaseApp />);

    expect(
      within(screen.getByRole("main")).getByText(
        "长时运行 Agent 如何避免恢复时重复执行外部工具？",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("main")).getAllByText(/Execution Policy/)
        .length,
    ).toBeGreaterThan(0);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(eventSource).not.toHaveBeenCalled();
  });

  it("switches to the Multi-Agent fixture", () => {
    render(<ShowcaseApp />);

    fireEvent.change(screen.getByLabelText("研究策略"), {
      target: { value: "multi_agent" },
    });
    fireEvent.click(screen.getByRole("button", { name: "加载示例" }));

    expect(
      within(screen.getByRole("main")).getByText(
        "三个策略怎样共享同一个 Agent Runtime？",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("main")).getAllByText(/Supervisor/).length,
    ).toBeGreaterThan(0);
  });

  it("renders public repository source links", () => {
    render(<ShowcaseApp />);

    const sourceLinks = screen.getAllByRole("link", { name: /github\.com/ });
    expect(sourceLinks.length).toBeGreaterThan(0);
    for (const link of sourceLinks) {
      expect(link.getAttribute("href")).toMatch(
        /^https:\/\/github\.com\/1785454358\/agent\//,
      );
    }
  });

  it("labels all content as SHOWCASE DATA", () => {
    render(<ShowcaseApp />);

    expect(screen.getByText("SHOWCASE DATA")).toBeInTheDocument();
    expect(
      screen.getByText(/固定演示数据，不会调用模型或外部工具/),
    ).toBeInTheDocument();
  });

  it("assigns planning, recovery, and outcome responsibilities accurately", () => {
    const messages = SHOWCASE_SCENARIOS.plan_execute.events.map(
      (event) => event.message,
    );
    const trace = messages.join("\n");

    expect(trace).toContain(
      "Planner 根据原始任务与当前约束拆分 3 项可执行研究 todo",
    );
    expect(trace).toContain(
      "Checkpoint 恢复 Agent State，Ledger 恢复工具执行与幂等记录",
    );
    expect(trace).toContain(
      "Execution Policy 根据恢复后的状态生成 AgentOutcome",
    );
    expect(trace).not.toMatch(/Planner 生成上下文、错误、恢复三个验证步骤/);
    expect(trace).not.toMatch(/Checkpoint 与 Ledger.*生成 AgentOutcome/);
  });
});

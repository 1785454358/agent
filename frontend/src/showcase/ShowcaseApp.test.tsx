import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { ShowcaseApp } from "./ShowcaseApp";

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
        "上下文、错误和恢复如何协作？",
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
});

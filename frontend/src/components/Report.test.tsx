import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Report } from "./Report";

describe("Report", () => {
  it("renders the answer when present", () => {
    render(<Report answer="# 结论" error={null} />);
    expect(screen.getByRole("heading", { name: "结论" })).toBeInTheDocument();
  });

  it("shows a placeholder before the answer exists", () => {
    render(<Report answer="" error={null} />);
    expect(screen.getByText(/报告生成后将在此展示/)).toBeInTheDocument();
  });

  it("surfaces the run error", () => {
    render(<Report answer="" error="provider unavailable" />);
    expect(screen.getByText(/provider unavailable/)).toBeInTheDocument();
  });

  it("renders comparison tables, code, emphasis and citation numbers", () => {
    const answer = "## 对比\n\n**结论**见 [1]。\n\n| 方案 | 条件 |\n| --- | --- |\n| A | 隔离 |\n\n```python\nprint('ok')\n```";
    const { container } = render(<Report answer={answer} error={null} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "方案" })).toBeInTheDocument();
    expect(container.querySelector("pre code")).toHaveTextContent("print('ok')");
    expect(container.querySelector("strong")).toHaveTextContent("结论");
    expect(screen.getByText(/见 \[1\]/)).toBeInTheDocument();
  });

  it("does not execute raw HTML, dangerous links or load remote images", () => {
    const { container } = render(<Report
      answer={'<script>alert(1)</script>\n\n<img src="https://tracker.example/pixel">\n\n![remote](https://tracker.example/pixel)\n\n[bad](javascript:alert%281%29)\n\n[Source](https://example.com)'}
      error={null}
    />);
    expect(container.querySelector("script")).not.toBeInTheDocument();
    expect(container.querySelector("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "bad" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Source" })).toHaveAttribute("rel", "noopener noreferrer");
  });
});

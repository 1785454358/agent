import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Report } from "./Report";

describe("Report", () => {
  it("renders the answer when present", () => {
    render(<Report answer="# 结论" error={null} />);
    expect(screen.getByText("# 结论")).toBeInTheDocument();
  });

  it("shows a placeholder before the answer exists", () => {
    render(<Report answer="" error={null} />);
    expect(screen.getByText(/报告生成后将在此展示/)).toBeInTheDocument();
  });

  it("surfaces the run error", () => {
    render(<Report answer="" error="provider unavailable" />);
    expect(screen.getByText(/provider unavailable/)).toBeInTheDocument();
  });
});

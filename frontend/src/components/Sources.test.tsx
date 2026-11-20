import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Sources } from "./Sources";

describe("Sources", () => {
  it("renders numbered source links with hostname", () => {
    render(
      <Sources
        sources={["https://example.com/a", "https://langchain.com/b"]}
        unresolvedGaps={[]}
      />,
    );
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "https://example.com/a");
    expect(screen.getByText("example.com")).toBeInTheDocument();
    expect(screen.getByText("langchain.com")).toBeInTheDocument();
  });

  it("shows the empty state and unresolved gaps block", () => {
    render(<Sources sources={[]} unresolvedGaps={["缺少对比数据"]} />);
    expect(screen.getByText(/无成功抓取来源/)).toBeInTheDocument();
    expect(screen.getByText("缺少对比数据")).toBeInTheDocument();
  });

  it("does not present internal diagnostics as missing research", () => {
    render(<Sources sources={["https://example.com/a"]} unresolvedGaps={[
      "diagnostic:read_anchor_omitted:evidence-123",
    ]} />);
    expect(screen.queryByText("未解决的研究缺口")).not.toBeInTheDocument();
    expect(screen.queryByText(/read_anchor_omitted/)).not.toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "https://example.com/a");
  });

  it("keeps real research gaps when internal diagnostics also exist", () => {
    render(<Sources sources={[]} unresolvedGaps={[
      "diagnostic:read_anchor_omitted:evidence-123", "缺少对比数据",
    ]} />);
    expect(screen.getByText("未解决的研究缺口")).toBeInTheDocument();
    expect(screen.getByText("缺少对比数据")).toBeInTheDocument();
    expect(screen.queryByText(/read_anchor_omitted/)).not.toBeInTheDocument();
  });
});

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
});

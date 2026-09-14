import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { TopBar } from "./TopBar";

function setup(submitting = false) {
  const onSubmit = vi.fn();
  const onModeChange = vi.fn();
  render(
    <TopBar
      mode="workflow"
      onModeChange={onModeChange}
      onSubmit={onSubmit}
      submitting={submitting}
    />,
  );
  return { onSubmit, onModeChange };
}

describe("TopBar", () => {
  it("does not submit an empty question", () => {
    const { onSubmit } = setup();
    fireEvent.click(screen.getByRole("button", { name: /开始研究/ }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits the trimmed question on Enter", () => {
    const { onSubmit } = setup();
    const input = screen.getByPlaceholderText(/输入研究问题/);
    fireEvent.change(input, { target: { value: "  什么是 LangGraph？  " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledWith("什么是 LangGraph？");
  });

  it("disables the submit button while submitting", () => {
    setup(true);
    expect(screen.getByRole("button", { name: /创建中/ })).toBeDisabled();
  });
});

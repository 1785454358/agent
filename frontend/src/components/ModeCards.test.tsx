import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ModeCards } from "./ModeCards";

describe("ModeCards", () => {
  it("marks the selected mode and notifies on click", () => {
    const onModeChange = vi.fn();
    render(<ModeCards mode="workflow" onModeChange={onModeChange} />);

    const selected = screen.getByRole("button", { name: /Plan-and-Execute/ });
    expect(selected).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(selected);
    expect(onModeChange).toHaveBeenCalledWith("plan_execute");
  });
});

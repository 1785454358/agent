import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBar } from "./StatusBar";

describe("StatusBar", () => {
  it("offers cancel while the run is active", () => {
    const onCancel = vi.fn();
    render(
      <StatusBar status="running" runId="run-1" reconnecting={false} onCancel={onCancel} />,
    );
    expect(screen.getByText("run-1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /取消运行/ })).toBeEnabled();
  });

  it("hides cancel for terminal statuses", () => {
    render(
      <StatusBar status="completed" runId="run-1" reconnecting={false} onCancel={null} />,
    );
    expect(screen.queryByRole("button", { name: /取消运行/ })).toBeNull();
  });

  it("shows the ready state when nothing is selected", () => {
    render(<StatusBar status={null} runId={null} reconnecting={false} onCancel={null} />);
    expect(screen.getByText("就绪")).toBeInTheDocument();
  });
});

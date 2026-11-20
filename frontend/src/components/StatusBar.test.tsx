import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBar } from "./StatusBar";

describe("StatusBar", () => {
  it("shows the actual automatically selected strategy and reason", () => {
    render(<StatusBar status="running" runId="run-1" reconnecting={false} onCancel={null}
      mode="auto" selectedMode="plan_execute" routingReason="后续步骤依赖诊断结果" />);
    expect(screen.getByText(/自动选择：Plan-and-Execute/)).toBeInTheDocument();
    expect(screen.getByText("后续步骤依赖诊断结果")).toBeInTheDocument();
  });

  it("does not label an automatic request as Workflow before a decision arrives", () => {
    render(<StatusBar status="running" runId="run-1" reconnecting={false} onCancel={null} mode="auto" />);
    expect(screen.getByText("正在选择研究模式…")).toBeInTheDocument();
    expect(screen.queryByText(/Workflow/)).not.toBeInTheDocument();
  });
  it("shows measured usage for a completed run", () => {
    render(<StatusBar status="completed" runId="run-1" reconnecting={false} onCancel={null}
      usage={{ provider_attempts: 2, total_tokens: 82, missing_usage_attempts: 0 }} />);
    expect(screen.getByText(/82 token/)).toBeInTheDocument();
    expect(screen.getByText(/2 次模型调用/)).toBeInTheDocument();
  });

  it("shows unknown usage when any model attempt has no usage", () => {
    render(<StatusBar status="partial" runId="run-1" reconnecting={false} onCancel={null}
      usage={{ provider_attempts: 2, total_tokens: null, missing_usage_attempts: 1 }} />);
    expect(screen.getByText(/Token 用量不完整/)).toBeInTheDocument();
    expect(screen.queryByText(/0 token/)).toBeNull();
  });

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

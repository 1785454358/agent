import { describe, expect, it } from "vitest";
import { isTerminalStatus, TERMINAL_STATUSES } from "./types";

describe("isTerminalStatus", () => {
  it("treats completed/partial/failed/cancelled as terminal", () => {
    expect(TERMINAL_STATUSES).toEqual([
      "completed",
      "partial",
      "failed",
      "cancelled",
    ]);
    for (const status of TERMINAL_STATUSES) {
      expect(isTerminalStatus(status)).toBe(true);
    }
  });

  it("treats pending/running/cancel_requested as non-terminal", () => {
    expect(isTerminalStatus("pending")).toBe(false);
    expect(isTerminalStatus("running")).toBe(false);
    expect(isTerminalStatus("cancel_requested")).toBe(false);
  });
});

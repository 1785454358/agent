import { describe, expect, it } from "vitest";
import { refetchIntervalFor } from "./useRun";

describe("refetchIntervalFor", () => {
  it("stops polling on terminal statuses", () => {
    expect(refetchIntervalFor("completed")).toBe(false);
    expect(refetchIntervalFor("partial")).toBe(false);
    expect(refetchIntervalFor("failed")).toBe(false);
    expect(refetchIntervalFor("cancelled")).toBe(false);
  });

  it("polls every 2s while running or before data arrives", () => {
    expect(refetchIntervalFor("running")).toBe(2_000);
    expect(refetchIntervalFor("pending")).toBe(2_000);
    expect(refetchIntervalFor(undefined)).toBe(2_000);
  });
});

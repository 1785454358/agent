import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getRun } from "./client";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("returns parsed JSON for successful responses", async () => {
    const run = { id: "run-1", status: "completed", answer: "ok" };
    vi.stubGlobal("fetch", mockFetch(200, run));
    await expect(getRun("run-1")).resolves.toEqual(run);
  });

  it("extracts backend detail into ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch(409, { detail: "thread busy" }),
    );
    const error = await getRun("run-1").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).message).toBe("thread busy");
  });
});

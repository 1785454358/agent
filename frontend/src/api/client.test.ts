import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, deleteAllRuns, deleteRun, deleteRuns, getRun } from "./client";

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

  it("issues a DELETE for a single run", async () => {
    const fetchMock = mockFetch(200, { id: "run-1" });
    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteRun("run-1")).resolves.toEqual({ id: "run-1" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/researches/run-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("posts a batch delete and clears history with DELETE", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => {
      const body = { deleted: ["run-1"], active: [], missing: [] };
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await deleteRuns(["run-1", "run-2"]);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/researches/batch-delete",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ ids: ["run-1", "run-2"] }),
      }),
    );

    await deleteAllRuns();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/researches",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});

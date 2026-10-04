import { describe, expect, it } from "vitest";
import { buildResearchProgress } from "./researchProgress";

describe("chronological research progress", () => {
  it("shows batch synthesis as evidence review with one compact stage", () => {
    const progress = buildResearchProgress([
      { event_type: "tool.completed", message: "阅读完成", tool: "read_evidence" },
      { event_type: "research.batch_synthesis.started", message: "开始整理", details: { task: "子任务" } },
    ], "running");
    expect(progress.operations.at(-1)?.stage).toBe("review");
    expect(progress.operations.at(-1)?.title).toBe("整理研究发现");
    expect(progress.summary.map(item => item.title)).toEqual(["阅读原文", "核对证据"]);
  });
  it("ends a started operation on failure while keeping a later retry separate", () => {
    const { operations } = buildResearchProgress([
      { event_type: "tool.started", message: "正在抓取", details: { tool: "fetch_page", call_id: "f1" } },
      { event_type: "tool.completed", message: "抓取失败", details: { tool: "fetch_page", call_id: "f1", ok: false, message: "页面持续跳转" } },
      { event_type: "tool.retry", message: "重试", details: { tool: "fetch_page", call_id: "f1" } },
    ], "running");
    expect(operations.map(op => op.state)).toEqual(["failed", "retry"]);
    expect(operations[0].description).toBe("页面持续跳转");
  });
  it("includes preflight and cached observations without duplicating completed calls", () => {
    const { operations } = buildResearchProgress([
      { event_type: "tool.completed", message: "搜索完成", details: { tool: "search_web", call_id: "s1", ok: true } },
      { event_type: "agent.tool_observation", message: "观察", details: { tool: "search_web", call_id: "s1", ok: true } },
      { event_type: "agent.tool_observation", message: "观察", details: { tool: "read_evidence", call_id: "r1", ok: false, error_code: "evidence_not_authorized", message: "该证据未获读取授权" } },
    ], "partial");
    expect(operations).toHaveLength(2);
    expect(operations[1].state).toBe("failed");
    expect(operations[1].description).toBe("该证据未获读取授权");
  });
  it("keeps failures between the surrounding successful actions in a long run", () => {
    const events = Array.from({ length: 5 }, (_, i) => [
      { event_type: "tool.completed", message: "网页搜索完成", tool: "search_web", id: i * 3 },
      { event_type: "tool.completed", message: i === 1 ? "网页抓取失败" : "网页抓取完成", tool: "fetch_page", id: i * 3 + 1 },
      { event_type: "tool.completed", message: "阅读完成", tool: "read_evidence", id: i * 3 + 2 },
    ]).flat();
    const { operations } = buildResearchProgress(events, "partial");
    expect(operations.map(op => op.state)).toEqual(events.map(e => e.message.includes("失败") ? "failed" : "done"));
    expect(operations[4].title).toBe("抓取网页内容");
  });

  it("shows each stage once per recorded round without mixing supplemental research", () => {
    const events = [
      { event_type: "planning.completed", message: "计划完成", details: { round: 1, tasks_json: '["初始任务"]' } },
      ...Array.from({ length: 6 }, () => [
        { event_type: "tool.completed", message: "搜索完成", tool: "search_web" },
        { event_type: "tool.completed", message: "抓取完成", tool: "fetch_page" },
      ]).flat(),
      { event_type: "evaluation.completed", message: "核对结束", details: { round: 1, covered: 1, total: 3 } },
      { event_type: "replanning.completed", message: "补查计划完成", details: { round: 2, tasks_json: '["补查任务"]' } },
      { event_type: "tool.completed", message: "搜索完成", tool: "search_web" },
    ];
    const { summary } = buildResearchProgress(events, "running");
    expect(summary.map(op => op.title)).toEqual(["制定计划", "检索资料", "阅读原文", "核对证据", "第 1 轮补查 · 制定计划", "检索资料"]);
    expect(summary[1].completedCalls).toBe(6);
    expect(summary[5].completedCalls).toBe(1);
  });

  it("preserves distinct replans with their new tasks and the evidence gaps", () => {
    const { operations } = buildResearchProgress([
      { event_type: "evaluation.completed", message: "核对结束", details: { round: 1, gaps_json: '["需要基础理论证据"]', action: "replan" } },
      { event_type: "replanning.started", message: "开始补查", details: { round: 2, reason: "需要基础理论证据" } },
      { event_type: "replanning.completed", message: "补查计划完成", details: { round: 2, tasks_json: '["检索论文原文"]' } },
      { event_type: "tool.completed", message: "搜索完成", tool: "search_web" },
      { event_type: "evaluation.completed", message: "核对结束", details: { round: 2 } },
      { event_type: "replanning.started", message: "开始补查", details: { round: 3, reason: "需要实验数据" } },
    ], "running");
    expect(operations.map(op => op.title)).toEqual(["核对本轮证据", "第 1 轮补查 · 调整计划", "第 1 轮补查 · 计划已生成", "搜索网页资料", "核对本轮证据", "第 2 轮补查 · 调整计划"]);
    expect(operations[2].tasks).toEqual(["检索论文原文"]);
    expect(operations[0].gaps).toEqual(["需要基础理论证据"]);
  });

  it("shows the stop reason without claiming a replan occurred", () => {
    const { operations } = buildResearchProgress([
      { event_type: "research.route", message: "路由", details: { next_step: "finalize", reason: "iteration_limit", action: "replan" } },
      { event_type: "tool.completed", message: "阅读完成", tool: "read_evidence", details: { ok: false, error_code: "evidence_not_authorized", message: "该证据未获读取授权" } },
    ], "partial");
    expect(operations[0].description).toContain("迭代上限");
    expect(operations[0].description).toContain("未进入再次规划");
    expect(operations[1].state).toBe("failed");
    expect(operations[1].description).toContain("该证据未获读取授权");
  });
});

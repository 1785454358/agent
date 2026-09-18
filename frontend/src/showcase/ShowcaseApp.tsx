import { useState } from "react";
import type { ResearchMode } from "../api/types";
import { EventTimeline } from "../components/EventTimeline";
import { Report } from "../components/Report";
import { Sources } from "../components/Sources";
import { IconLink, IconRocket, IconUsers } from "../components/icons";
import { SHOWCASE_SCENARIOS } from "./fixtures";

const REPOSITORY = "https://github.com/1785454358/agent";

export function ShowcaseApp() {
  const [selectedMode, setSelectedMode] =
    useState<ResearchMode>("plan_execute");
  const [activeMode, setActiveMode] = useState<ResearchMode>("plan_execute");
  const scenario = SHOWCASE_SCENARIOS[activeMode];
  const selection = SHOWCASE_SCENARIOS[selectedMode];

  return (
    <div className="showcase-shell">
      <header className="showcase-header">
        <a className="showcase-brand" href={REPOSITORY}>
          <span className="showcase-mark" aria-hidden="true">
            <IconRocket size={18} />
          </span>
          <span>DeepResearch</span>
        </a>
        <span className="showcase-badge">SHOWCASE DATA</span>
        <a className="showcase-repository" href={REPOSITORY}>
          查看 GitHub 仓库
          <IconLink size={15} />
        </a>
      </header>

      <section className="showcase-hero">
        <div>
          <p className="showcase-eyebrow">Governed Agent Harness</p>
          <h1>把开放式 Agent 循环放进可验证的运行边界</h1>
          <p className="showcase-lead">
            固定演示数据，不会调用模型或外部工具。切换策略即可查看同一个
            Agent Runtime 如何完成研究、工具治理与明确退出。
          </p>
        </div>
        <div className="showcase-controls">
          <label>
            <span>研究策略</span>
            <select
              aria-label="研究策略"
              value={selectedMode}
              onChange={(event) =>
                setSelectedMode(event.target.value as ResearchMode)
              }
            >
              <option value="workflow">Workflow</option>
              <option value="plan_execute">Plan-and-Execute</option>
              <option value="multi_agent">Multi-Agent</option>
            </select>
          </label>
          <div className="showcase-selection">
            <span>示例问题</span>
            <strong>{selection.question}</strong>
          </div>
          <button type="button" onClick={() => setActiveMode(selectedMode)}>
            加载示例
          </button>
        </div>
      </section>

      <div className="showcase-layout">
        <main className="showcase-main">
          <section className="question-card showcase-question">
            <span className="question-card-icon" aria-hidden="true">
              <IconUsers size={18} />
            </span>
            <span>
              <small>{scenario.summary}</small>
              <strong>{scenario.question}</strong>
            </span>
          </section>
          <EventTimeline events={scenario.events} />
          <Report answer={scenario.answer} error={null} />
          <Sources sources={scenario.sources} unresolvedGaps={[]} />
        </main>

        <aside className="showcase-aside" aria-label="Harness 核心不变量">
          <p className="showcase-aside-label">Runtime invariants</p>
          <h2>每种策略都必须满足</h2>
          <ul>
            <li>模型调用包含 instruction、task 与 constraints</li>
            <li>每个 tool call 都有对应 ToolMessage</li>
            <li>模型与外部工具分别经过统一 Gateway</li>
            <li>所有受控退出都产生 AgentOutcome</li>
          </ul>
          <a href={scenario.sourceCodeUrl}>
            查看当前策略源码
            <IconLink size={15} />
          </a>
        </aside>
      </div>
    </div>
  );
}

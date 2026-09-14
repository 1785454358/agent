import type { ResearchMode } from "../api/types";

/** 文案取自 README 三种研究模式表。 */
const MODES: ReadonlyArray<{
  value: ResearchMode;
  name: string;
  summary: string;
  scene: string;
}> = [
  {
    value: "workflow",
    name: "Workflow",
    summary: "查询规划、并行 Topic 研究、证据评估",
    scene: "边界清楚、希望快速获得可靠答案",
  },
  {
    value: "plan_execute",
    name: "Plan-and-Execute",
    summary: "任务拆解、逐项执行、评估、有界重规划",
    scene: "有依赖关系且需要补查的复杂问题",
  },
  {
    value: "multi_agent",
    name: "Multi-Agent",
    summary: "Supervisor 拆解和评估，多个 Researcher 并发研究",
    scene: "多个方向可以独立调查的问题",
  },
];

interface ModeCardsProps {
  mode: ResearchMode;
  onModeChange: (mode: ResearchMode) => void;
}

/** 三张模式说明卡片，点选与下拉联动。 */
export function ModeCards({ mode, onModeChange }: ModeCardsProps) {
  return (
    <section className="mode-cards" aria-label="研究模式说明">
      {MODES.map((item) => (
        <button
          key={item.value}
          type="button"
          className={`mode-card${mode === item.value ? " selected" : ""}`}
          aria-pressed={mode === item.value}
          onClick={() => onModeChange(item.value)}
        >
          <span className="mode-name">{item.name}</span>
          <span className="mode-summary">{item.summary}</span>
          <span className="mode-scene">{item.scene}</span>
        </button>
      ))}
    </section>
  );
}

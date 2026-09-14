import { useState } from "react";
import type { ResearchMode } from "../api/types";

interface TopBarProps {
  mode: ResearchMode;
  onModeChange: (mode: ResearchMode) => void;
  onSubmit: (question: string) => void;
  submitting: boolean;
}

/** 品牌 + 模式选择 + 问题输入 + 提交。 */
export function TopBar({
  mode,
  onModeChange,
  onSubmit,
  submitting,
}: TopBarProps) {
  const [question, setQuestion] = useState("");

  const submit = () => {
    const trimmed = question.trim();
    if (!trimmed || submitting) return;
    onSubmit(trimmed);
  };

  return (
    <header className="topbar">
      <div className="brand">
        <h1>
          Research<em>Pilot</em>
        </h1>
        <div className="tagline">Plan · Research · Refine</div>
      </div>
      <div className="search">
        <select
          aria-label="研究模式"
          value={mode}
          onChange={(e) => onModeChange(e.target.value as ResearchMode)}
        >
          <option value="workflow">Workflow · 并行研究</option>
          <option value="plan_execute">Plan-and-Execute · 有界重规划</option>
          <option value="multi_agent">Multi-Agent · 协作研究</option>
        </select>
        <input
          placeholder="输入研究问题，例如：2026 年量子计算领域有哪些最新进展？"
          autoComplete="off"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
        />
        <button onClick={submit} disabled={submitting || !question.trim()}>
          {submitting ? "创建中…" : "开始研究"}
        </button>
      </div>
    </header>
  );
}

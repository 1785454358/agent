import { useEffect, useRef, useState } from "react";
import type { ResearchMode } from "../api/types";
import { IconChat, IconSearch } from "./icons";

interface TopBarProps {
  mode: ResearchMode;
  onModeChange: (mode: ResearchMode) => void;
  onSubmit: (question: string) => void;
  submitting: boolean;
  /** 变化时聚焦问题输入框（用于“新研究”）。 */
  focusToken: number;
  chatEnabled: boolean;
  chatOpen: boolean;
  onToggleChat: () => void;
}

/** 模式选择 + 问题输入 + 提交 + Chat 分屏开关（无品牌区）。 */
export function TopBar({
  mode,
  onModeChange,
  onSubmit,
  submitting,
  focusToken,
  chatEnabled,
  chatOpen,
  onToggleChat,
}: TopBarProps) {
  const [question, setQuestion] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (focusToken > 0) inputRef.current?.focus();
  }, [focusToken]);

  const submit = () => {
    const trimmed = question.trim();
    if (!trimmed || submitting) return;
    onSubmit(trimmed);
  };

  return (
    <header className="topbar">
      <div className="search">
        <select
          aria-label="研究模式"
          value={mode}
          onChange={(e) => onModeChange(e.target.value as ResearchMode)}
        >
          <option value="workflow">Workflow</option>
          <option value="plan_execute">Plan-and-Execute</option>
          <option value="multi_agent">Multi-Agent</option>
        </select>
        <input
          ref={inputRef}
          placeholder="输入研究问题，例如：2026 年量子计算领域有哪些最新进展？"
          autoComplete="off"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
        />
        <button
          className="start-btn"
          onClick={submit}
          disabled={submitting || !question.trim()}
        >
          <IconSearch size={16} />
          {submitting ? "创建中…" : "开始研究"}
        </button>
      </div>
      <button
        type="button"
        className={`chat-btn${chatOpen ? " open" : ""}`}
        disabled={!chatEnabled}
        title={chatEnabled ? "分屏追问" : "先选择一个研究"}
        onClick={onToggleChat}
      >
        <IconChat size={17} />
        Chat
      </button>
    </header>
  );
}

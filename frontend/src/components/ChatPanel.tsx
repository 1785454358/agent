import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../api/types";
import {
  IconChat,
  IconChevronRight,
  IconRobot,
  IconSend,
} from "./icons";

interface ChatPanelProps {
  open: boolean;
  onClose: () => void;
  messages: ChatMessage[];
  busy: boolean;
  onSend: (question: string) => void;
}

/** 右侧追问面板：基于当前研究会话继续对话。 */
export function ChatPanel({ open, onClose, messages, busy, onSend }: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages.length, open]);

  if (!open) return null;

  const submit = () => {
    const trimmed = draft.trim();
    if (!trimmed || busy) return;
    onSend(trimmed);
    setDraft("");
  };

  return (
    <aside className="chat-panel" aria-label="追问面板">
      <div className="chat-head">
        <span className="chat-avatar" aria-hidden="true">
          <IconRobot size={20} />
        </span>
        <span className="chat-title">Research Assistant</span>
        <span className="chat-active">
          <i aria-hidden="true" />
          active
        </span>
        <button
          type="button"
          className="chat-close"
          aria-label="收起对话"
          onClick={onClose}
        >
          <IconChevronRight size={16} />
        </button>
      </div>
      <div className="chat-body">
        {messages.length === 0 && (
          <div className="chat-msg assistant">
            <span className="chat-msg-icon" aria-hidden="true">
              <IconChat size={15} />
            </span>
            <span>我已分析本次研究的全部结果，可以围绕报告继续提问。</span>
          </div>
        )}
        {messages.map((msg, index) => (
          <div key={index} className={`chat-msg ${msg.role}`}>
            {msg.role === "assistant" && (
              <span className="chat-msg-icon" aria-hidden="true">
                <IconChat size={15} />
              </span>
            )}
            <span className="chat-msg-text">{msg.text}</span>
          </div>
        ))}
        {busy && (
          <div className="chat-typing" aria-label="正在生成回答">
            <span />
            <span />
            <span />
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input">
        <textarea
          rows={2}
          placeholder="关于这次研究，还有什么想问的？"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          type="button"
          aria-label="发送"
          disabled={busy || !draft.trim()}
          onClick={submit}
        >
          <IconSend size={18} />
        </button>
      </div>
    </aside>
  );
}

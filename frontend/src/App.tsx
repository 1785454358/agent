import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  cancelRun,
  createRun,
  deleteAllRuns,
  deleteRun,
  deleteRuns,
  ApiError,
  type DeleteRunsResult,
} from "./api/client";
import {
  isTerminalStatus,
  type ChatMessage,
  type ResearchMode,
} from "./api/types";
import { useRun } from "./hooks/useRun";
import { useRuns } from "./hooks/useRuns";
import { useRunEvents } from "./hooks/useRunEvents";
import { TopBar } from "./components/TopBar";
import { StatusBar } from "./components/StatusBar";
import { RunHistory } from "./components/RunHistory";
import { EventTimeline } from "./components/EventTimeline";
import { Report } from "./components/Report";
import { Sources } from "./components/Sources";
import { ChatPanel } from "./components/ChatPanel";
import { Toast } from "./components/Toast";
import { IconUsers } from "./components/icons";

export default function App() {
  const [mode, setMode] = useState<ResearchMode>("workflow");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const [focusToken, setFocusToken] = useState(0);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatPending, setChatPending] = useState(false);
  const [followUpRunId, setFollowUpRunId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const runsQuery = useRuns();
  const runQuery = useRun(selectedRunId);
  const run = runQuery.data ?? null;
  const live = run !== null && !isTerminalStatus(run.status);
  const threadId = run?.thread_id || null;

  // 进行中走 SSE；历史运行直接回放 detail 里的事件
  const sse = useRunEvents(selectedRunId, live);
  const events = live ? sse.events : (run?.events ?? []);

  // 追问产生的后续运行：轮询其结果并写回聊天面板
  const followUpQuery = useRun(followUpRunId);
  const followUp = followUpQuery.data ?? null;

  const chatThreadRef = useRef<string | null>(null);
  useEffect(() => {
    if (chatThreadRef.current !== threadId) {
      chatThreadRef.current = threadId;
      setChatMessages([]);
    }
  }, [threadId]);

  useEffect(() => {
    if (followUpRunId && followUp && isTerminalStatus(followUp.status)) {
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text:
            followUp.answer ||
            (followUp.error ? `追问失败：${followUp.error}` : "（无回答内容）"),
        },
      ]);
      setSelectedRunId(followUpRunId);
      setFollowUpRunId(null);
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    }
  }, [followUpRunId, followUp, queryClient]);

  const createMutation = useMutation({
    mutationFn: (args: {
      question: string;
      mode: ResearchMode;
      threadId?: string;
    }) => createRun(args.question, args.mode, args.threadId),
    onSuccess: (created) => {
      setSelectedRunId(created.id);
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (error) => {
      setFollowUpRunId(null);
      setToast(
        error instanceof ApiError
          ? `创建运行失败：${error.message}`
          : "创建运行失败：网络错误",
      );
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (runId: string) => cancelRun(runId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (error) => {
      setToast(
        error instanceof ApiError
          ? `取消失败：${error.message}`
          : "取消失败：网络错误",
      );
    },
  });

  // 删除历史：单个走专用接口，批量/清空走聚合接口，统一归一化结果
  const deleteMutation = useMutation({
    mutationFn: async (
      target: string[] | "all",
    ): Promise<DeleteRunsResult> => {
      if (target === "all") return deleteAllRuns();
      if (target.length === 1) {
        const removed = await deleteRun(target[0]);
        return { deleted: [removed.id], active: [], missing: [] };
      }
      return deleteRuns(target);
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      for (const id of result.deleted) {
        queryClient.removeQueries({ queryKey: ["runs", id] });
      }
      if (selectedRunId && result.deleted.includes(selectedRunId)) {
        setSelectedRunId(null);
        setFollowUpRunId(null);
        setChatOpen(false);
      }
      if (result.active.length > 0) {
        setToast(`已删除 ${result.deleted.length} 条记录；${result.active.length} 条进行中已跳过`);
      }
    },
    onError: (error) => {
      setToast(
        error instanceof ApiError
          ? `删除失败：${error.message}`
          : "删除失败：网络错误",
      );
    },
  });

  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);

  const startNewResearch = () => {
    setSelectedRunId(null);
    setFollowUpRunId(null);
    setChatOpen(false);
    setFocusToken((t) => t + 1);
  };

  const sendFollowUp = (question: string) => {
    if (!threadId) return;
    setChatMessages((prev) => [...prev, { role: "user", text: question }]);
    setChatPending(true);
    void createRun(question, run?.mode ?? mode, threadId)
      .then((created) => {
        setFollowUpRunId(created.id);
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
      })
      .catch((error: unknown) => {
        setChatMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            text: `追问失败：${error instanceof ApiError ? error.message : "网络错误"}`,
          },
        ]);
      })
      .finally(() => setChatPending(false));
  };

  return (
    <div className="app-frame">
      {/* 全页面左侧边栏：展开为历史面板，收起为窄图标轨 */}
      <RunHistory
        runs={runs}
        selectedId={selectedRunId}
        onSelect={setSelectedRunId}
        onNewResearch={startNewResearch}
        onDelete={(target) => deleteMutation.mutate(target)}
        collapsed={historyCollapsed}
        onToggle={() => setHistoryCollapsed((v) => !v)}
      />
      <div className="content">
        <TopBar
          mode={mode}
          onModeChange={setMode}
          onSubmit={(question) => createMutation.mutate({ question, mode })}
          submitting={createMutation.isPending}
          focusToken={focusToken}
          chatEnabled={selectedRunId !== null}
          chatOpen={chatOpen}
          onToggleChat={() => setChatOpen((v) => !v)}
        />
        <div className="content-inner">
          <Toast message={toast} />
          <StatusBar
            status={run?.status ?? null}
            runId={selectedRunId}
            reconnecting={sse.reconnecting}
            onCancel={
              selectedRunId && live
                ? () => cancelMutation.mutate(selectedRunId)
                : null
            }
          />
          <div className={`workspace${chatOpen ? " with-chat" : ""}`}>
            <main className="main">
              {run && (
                <section className="question-card">
                  <span className="question-card-icon" aria-hidden="true">
                    <IconUsers size={18} />
                  </span>
                  <span className="question-card-text">{run.question}</span>
                </section>
              )}
              <EventTimeline events={events} status={run?.status} terminationReason={run?.termination_reason} />
              <Report answer={run?.answer ?? ""} error={run?.error ?? null} />
              <Sources
                sources={run?.sources ?? []}
                unresolvedGaps={run?.unresolved_gaps ?? []}
              />
            </main>
            <ChatPanel
              open={chatOpen}
              onClose={() => setChatOpen(false)}
              messages={chatMessages}
              busy={chatPending || followUpRunId !== null}
              onSend={sendFollowUp}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

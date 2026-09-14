import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cancelRun, createRun, ApiError } from "./api/client";
import { isTerminalStatus, type ResearchMode } from "./api/types";
import { useRun } from "./hooks/useRun";
import { useRuns } from "./hooks/useRuns";
import { useRunEvents } from "./hooks/useRunEvents";
import { TopBar } from "./components/TopBar";
import { ModeCards } from "./components/ModeCards";
import { StatusBar } from "./components/StatusBar";
import { RunHistory } from "./components/RunHistory";
import { EventTimeline } from "./components/EventTimeline";
import { Report } from "./components/Report";
import { Sources } from "./components/Sources";
import { Toast } from "./components/Toast";

export default function App() {
  const [mode, setMode] = useState<ResearchMode>("workflow");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const runsQuery = useRuns();
  const runQuery = useRun(selectedRunId);
  const run = runQuery.data ?? null;
  const live = run !== null && !isTerminalStatus(run.status);

  // 进行中走 SSE；历史运行直接回放 detail 里的事件
  const sse = useRunEvents(selectedRunId, live);
  const events = live ? sse.events : (run?.events ?? []);

  const createMutation = useMutation({
    mutationFn: (args: { question: string; mode: ResearchMode }) =>
      createRun(args.question, args.mode),
    onSuccess: (created) => {
      setSelectedRunId(created.id);
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (error) => {
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

  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);

  return (
    <div className="shell">
      <TopBar
        mode={mode}
        onModeChange={setMode}
        onSubmit={(question) => createMutation.mutate({ question, mode })}
        submitting={createMutation.isPending}
      />
      <ModeCards mode={mode} onModeChange={setMode} />
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
      <div className="workbench">
        <RunHistory
          runs={runs}
          selectedId={selectedRunId}
          onSelect={setSelectedRunId}
        />
        <main className="main">
          <EventTimeline events={events} />
          <Report answer={run?.answer ?? ""} error={run?.error ?? null} />
          <Sources
            sources={run?.sources ?? []}
            unresolvedGaps={run?.unresolved_gaps ?? []}
          />
        </main>
      </div>
    </div>
  );
}

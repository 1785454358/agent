import { useQuery } from "@tanstack/react-query";
import { getRun } from "../api/client";
import { isTerminalStatus, type RunStatus } from "../api/types";

/** 轮询决策：终态停止，其余 2s。导出纯函数便于测试。 */
export function refetchIntervalFor(
  status: RunStatus | undefined,
): number | false {
  if (status !== undefined && isTerminalStatus(status)) {
    return false;
  }
  return 2_000;
}

/** 单运行详情：非终态每 2s 轮询，终态自动停止。 */
export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ["runs", runId],
    queryFn: () => getRun(runId as string),
    enabled: runId !== null,
    refetchInterval: (query) =>
      refetchIntervalFor(query.state.data?.status as RunStatus | undefined),
  });
}

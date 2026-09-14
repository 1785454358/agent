import { useQuery } from "@tanstack/react-query";
import { listRuns } from "../api/client";

/** 运行历史列表：10s 轮询 + 窗口聚焦重取。 */
export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: listRuns,
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
  });
}

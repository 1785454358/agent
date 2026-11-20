# 全部逐次运行记录

两道题均为开发题；所有阶段与错误均保留。自动完成不等于事实准确，不能按单次耗时排序产品。

| 阶段 | 问题 | 秒 | 模型 | 工具 | 已知输入/输出 token | partial_reason | 调用错误 | 原始答案 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| before-2026-10-24 | comparison | 35.348 | 7 | 26 | 35074/5519 | 无 | 无 | [答案](outputs/before-comparison.md) |
| before-2026-10-24 | sqlite | 40.947 | 10 | 17 | 38447/7411 | insufficient_evidence | 无 | [答案](outputs/before-sqlite.md) |
| candidate-a | comparison | 36.148 | 8 | 18 | 35840/6678 | model_error | researcher:ModelCallError | [答案](outputs/candidate-a-comparison.md) |
| candidate-a | sqlite | 26.698 | 7 | 15 | 27467/4619 | 无 | 无 | [答案](outputs/candidate-a-sqlite.md) |
| final | comparison | 50.592 | 11 | 31 | 60202/8179 | 无 | 无 | [答案](outputs/final-comparison.md) |
| final | sqlite | 31.227 | 9 | 16 | 26859/5349 | insufficient_evidence | 无 | [答案](outputs/final-sqlite.md) |
| focus-final | comparison | 28.818 | 7 | 19 | 29632/5443 | 无 | 无 | [答案](outputs/focus-final-comparison.md) |
| focus-final | sqlite | 49.690 | 11 | 11 | 28507/4212 | insufficient_evidence | planner:ModelCallError | [答案](outputs/focus-final-sqlite.md) |
| release-check | comparison | 69.318 | 10 | 43 | 60846/7668 | insufficient_evidence | 无 | [答案](outputs/release-check-comparison.md) |
| release-check | sqlite | 34.581 | 9 | 25 | 42218/6301 | insufficient_evidence | 无 | [答案](outputs/release-check-sqlite.md) |
| verification | sqlite | 29.158 | 11 | 9 | 26990/4439 | insufficient_evidence | planner:ModelCallError | [答案](outputs/verification-sqlite.md) |
| capacity-check | comparison | 44.027 | 11 | 30 | 54214/7655 | 无 | 无 | [答案](outputs/capacity-check-comparison.md) |

每次配置、实际返回模型、需求覆盖、来源和记录哈希见 [runs.json](runs.json)。失败调用缺 usage 时，仅加总已知 usage，不等于完整计费量。

最后成对阶段 `release-check` 两题仍为部分完成；随后 `capacity-check` 仅追加主问题，自动完成且补回关键操作，但调用增加。SQLite 未追加去重后的联网采样。不能用较好的中间答案取代失败，也不能据一个追加样本宣称稳定胜出。

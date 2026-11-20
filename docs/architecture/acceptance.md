# 核心 Runtime 验收

验收关注实际交付：问题是否被回答、依据是否有效、失败是否可解释、预算和权限是否守住。`completed` 只是执行状态，不能单独当作答案合格。

实际执行记录见[2026-11-09 全量验收](../benchmarks/2026-11-09-full-acceptance/README.md)：两轮共 180 次运行，包含逐题结果、已修复缺陷和仍未通过的案例。

## 数据与范围

默认 LangSmith 数据集 `deeptrace-grounded-v1` 包含原来的 30 道问题，覆盖单跳、多跳、比较、版本边界、矛盾材料和资料不足六类。每道题的原生 `inputs.documents` 都包含同一组完整的 14 份官方文档，没有依据参考答案挑选来源。原文来自同一上游提交，逐份 SHA-256 校验，总正文约 511 KB；许可见 `backend/src/deeptrace/evaluation/data/LICENSE.txt`。

完整语料写入普通 EvidenceStore，host 授予 `HarnessContext.source_evidence_ids`，并通过 `AgentToolGateway.with_source_scope()` 绑定同一范围。三种策略仍使用原来的规划、选材、读取、证据核验与 Writer。限定来源时 Gateway 拒绝网络工具及范围外读取；候选发现只提供文档元信息，实际证据读取经过 Gateway、授权和执行账本。默认 context 不设范围，继续真实联网。

`deeptrace-web-smoke-v1` 另用 Python 3.11 官方文档题验证真实搜索、抓取与版本约束，不把冻结资料测试冒充联网覆盖。评测关闭跨样本记忆，使用临时 DB，不改变生产默认记忆设置。

## 验收规则

- 工程回归通过；已有预算、恢复、权限和取消契约保持有效。
- 每个运行必须记录结果或明确错误；未处理异常、范围外取证、超出共享预算均需调查。
- 问题与参考输出分离，运行只接收原生 example inputs，参考答案不进入目标。
- `answer_correctness_v4` 检查原问题及参考要求；`answer_groundedness_v4` 使用 Writer 真正看到的原文，而不是研究员摘要或少量短引用。
- 最终答案的引用可能已压缩编号，裁判按最终来源 URL 映射核对，不能混用 Writer 原编号。
- `task_accepted_v4` 的诊断条件为正确性、证据支持均不低于 0.8，来源及预算检查通过，且有实际回答。资料不足题允许有依据的拒绝推导，不强制 completed。
- LLM 裁判仍可能误判；保留评分解释，逐题复核低分、未评分和运行错误。未要求逐字引用、未问的可选细节不应变成扣分项。该阈值是本项目的诊断门槛，不是行业标准或准确率。

## 使用

从 `backend` 运行：

```powershell
# 默认同步会附带已验证的公开冻结文档
uv run python -m deeptrace.evaluation sync-dataset

# 小样本 / 明确回归案例
uv run python -m deeptrace.evaluation run --mode workflow --case-id single_hop-dev-01 --judge
uv run python -m deeptrace.evaluation run --mode multi_agent --case-ids multi_hop-dev-02 multi_hop-test-03 --judge

# 完整 30 题；三个模式分别运行，共 90 次
uv run python -m deeptrace.evaluation run --mode workflow --concurrency 3 --judge
uv run python -m deeptrace.evaluation run --mode plan_execute --concurrency 3 --judge
uv run python -m deeptrace.evaluation run --mode multi_agent --concurrency 3 --judge

# 通过 --dataset-version 指定时间戳或标签，锁定数据版本
# 对历史运行重新评分只调用裁判，不重跑研究；按 reference_example_id 对齐并使用原数据版本
uv run python -m deeptrace.evaluation rescore --experiment <project-uuid> --concurrency 3

# 不同文件默认按其原生 inputs 运行；不会自动附加上述语料
uv run python -m deeptrace.evaluation sync-dataset --dataset deeptrace-web-smoke-v1 --file src/deeptrace/evaluation/data/web-smoke-v1.jsonl
uv run python -m deeptrace.evaluation run --dataset deeptrace-web-smoke-v1 --mode workflow --judge
```

正式门禁可追加 `--require-acceptance`：任一题低于门槛或缺少裁判结果即返回失败，实验记录仍留在 LangSmith；手动 CI 工作流已启用该选项。普通运行不启用门禁，便于留存诊断实验。

LangSmith 继续管理数据、实验、Trace 和反馈。`rescore` 是 SDK 重新评估现有运行的薄适配：只补齐尚未评分或裁判失败的完成项，不建立本地评分平台。旧 v1 短引用评分、v2 试验配对及 v3 压缩前编号的反馈均不用于当前验收；保留历史记录，正式结果使用已对齐的 v4 系列和实验中记录的具体 rubric 版本。

本轮验证覆盖核心 Runtime、真实模型和真实联网工具；工程测试另覆盖 API、持久化和恢复。容器部署、远程 CI 与生产负载测试需要单独验证，不由本次任务结果推断。

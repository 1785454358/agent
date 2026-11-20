# 核心 Runtime 全量验收（2026-11-09）

本轮已完成两轮「30 题 × 3 策略」真实模型执行，共 180 次，另有失败案例回归与真实联网补测。第二轮 90 次均返回可检查结果，未处理运行异常为 0，来源范围与共享预算检查均为 90/90。答案质量门禁仍有失败，**不能据此声明项目已经全部达标**。

后续针对这些失败的定位与修复见[失败根因优化记录](../2026-11-09-root-cause-optimization/README.md)。本页保留原完整矩阵，不以补测结果替换历史失败。

## 数据、执行与评分条件

- 默认原生 LangSmith 数据集为 `deeptrace-grounded-v1`，共 30 题，单跳、多跳、比较、版本边界、矛盾材料、资料不足六类各 5 题。每个样本输入同一组完整的 14 份公开官方文档，而非按参考答案挑选资料。
- 文档固定在上游提交 `99dd9a9e38d59b9bff54354f6c3ef790c1be946d`；14 份 SHA-256 均核对原记录，总正文 UTF-8 大小 511446 字节。参考答案只供评分，不传入运行目标。
- 第二轮固定数据版本 `2026-11-09T09:26:48.687291+00:00`，每个策略并发 3。模型配置为 `deepseek-v4.1-flash`，关闭 thinking；共享上限保持 20 次模型调用、100000 输入 token。裁判调用单独计费，不混入目标执行预算。
- 复用生产 Runtime、EvidenceStore、选材、读取、核验和 Writer。工具 Gateway 绑定 host 授予的资料范围；冻结模式拒绝联网和越界读取。每个样本使用独立 run/thread，关闭跨样本记忆，临时 DB 隔离生产数据。
- 正确性与证据支持均要求不低于 0.8，并检查来源、预算和实际回答。`completed` 不等于合格；资料不足题允许有依据的有限回答或拒绝推导。
- 使用 `actual-writer-context-citation-aligned-v4.1` rubric：从原生模型 Trace 取得 Writer 真正可见的原文，并按最终来源 URL 对齐压缩后的引用编号。早期 v1/v2/v3 反馈不用于本表。评分服务曾超时，已补齐原运行的裁判反馈，没有因此重跑或替换目标答案。

数据、Trace、实验与评分由 LangSmith 保存。[逐题结果快照](results.json)仅导出运行标识、诊断、用量和评分解释，便于审查，不构建本地评分平台。

## 第二轮完整矩阵

| 策略 | 已运行 | 合格 | 未合格 | 缺少验收判定 | 未处理异常 | 来源 / 预算检查 |
|---|---:|---:|---:|---:|---:|---|
| Workflow | 30 | 28 | 2 | 0 | 0 | 各 30/30 |
| Plan-and-Execute | 30 | 28 | 2 | 0 | 0 | 各 30/30 |
| Multi-Agent | 30 | 29 | 1 | 0 | 0 | 各 30/30 |

这是本项目固定题池上的诊断计数，不是泛化准确率。冻结资料与真实联网的能力范围不同；测试题已用于失败分析，后续迭代不能再把它们视为未接触的独立测试集。

原生实验：[Workflow](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/5c68f50b-7d5d-4e8d-a581-06f26fe4815d)、[Plan-and-Execute](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/ea391dde-66e7-4df5-8bfd-4ec284c2ff01)、[Multi-Agent](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/72fd6b04-377c-4119-b00a-4f88f36b4399)。

| 未合格样本 | 策略 | 核对结论 |
|---|---|---|
| `single_hop-test-03` | Workflow、Multi-Agent | 混淆 Runtime 容器与其静态 Context 字段，后续列表或标题又将 Store、执行元信息写成 Context 内容。仍未稳定解决。 |
| `single_hop-dev-02` | Plan-and-Execute | 漏掉 interrupt payload 必须可 JSON 序列化的必要条件。仍需解决。 |
| `conflicting_evidence-test-03` | Plan-and-Execute | 过度保守，将工具调用/返回配对要求与裁剪的合理协调也判为无法回答。仍需解决。 |
| `comparison-test-01` | Workflow | 选材 JSON 格式错误导致未获得 Writer 证据。已增加有界结构修复；独立回归正确性和证据支持均为 1，原全量失败记录保留。 |

最后一项没有实际 Writer 原文，因此 `answer_groundedness_v4` 为 null、验收判定明确失败。这与裁判服务超时导致缺少验收判定不同。

## Trace 驱动的修改与回归

1. 第一轮发现 Writer/事实审查的临时传输错误会抛出或退化成只有来源的回答。现在只对 transient 错误做一次显式只读恢复，每次重试仍重新经过共享预算和调用账本；取消、致命错误与预算拒绝保留原契约。第二轮未再出现未处理运行异常。
2. 原文读取窗口被 CamelCase API 名称过度锚定，遗漏联合使用条件和参数支持边界。为组合、比较和版本任务保留条件词，加入真实冻结文档回归，验证同样窗口内含 simultaneous-tools 兼容条件和 strict 的 provider/default 限制。
3. 选材输出偶发非法 JSON 时，原逻辑直接清空来源。加入一次结构修复，限制候选和需求 ID，重新检查上下文和共享预算；不允许新增来源或借修复放宽授权。[修复后独立回归](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/b51f61d3-cfa5-4bec-9356-fdd5329bbf3c)通过。
4. 裁判原先只见研究摘要，且可能混用压缩前后编号。现使用实际 Writer 资料、最终 URL 映射、严格 example ID 与数据版本对齐。Trace 查询设 60 秒超时并只对连接/限流错误有界恢复；评分失败可通过原生重新评估补齐。
5. CLI 增加 `--case-ids`、`--dataset-version`、`--require-acceptance` 和原生 `rescore`。门禁对失败或缺少评分返回非零；实验诊断仍保留在 LangSmith。手动评测 CI 已启用门禁。

结构修复与最终联网版本发现是在第二轮批处理启动后加入，已验证对应单元测试和真实失败案例，**没有另做第三轮完整矩阵**。第二轮结果不能冒充这些最新错误分支的全量重跑结果。

## 效率观测

| 策略 | 目标运行耗时中位数 | Provider 尝试数中位数 | 已知输入 token 中位数 | 输入用量不完整样本 |
|---|---:|---:|---:|---:|
| Workflow | 35.4 秒 | 6 | 25105 | 3 |
| Plan-and-Execute | 38.2 秒 | 6 | 23295 | 2 |
| Multi-Agent | 38.0 秒 | 6 | 23917.5 | 0 |

这些是第二轮原生根运行的分布摘要，不包含后续补评分耗时；不是优化前后的因果比较。部分 transient 尝试未返回 provider usage，完整用量为 null，不当作 0，也不据此计算金额。预算门禁使用已准入调用与输入预算记录，和 provider 实测 token 完整性分开检查。

另外尝试了开启 thinking 的单题运行，出现多次 60 秒模型超时，总耗时约 308 秒，未采用为默认方案，未通过增加调用或 token 上限换取表面通过。

## 真实联网补测

另建 `deeptrace-web-smoke-v1`，仅输入一道比较 Python 3.11 TaskGroup、gather 与取消清理的问题，通过真实搜索和抓取取证。这个单题只证明相应路径，不代表开放研究题的全面覆盖。

- 初次 Workflow 和 Multi-Agent 搜索到其他版本文档，来源准入正确拒绝，但任务没有足够资料，验收失败。Plan-and-Execute 同题通过。
- 增加显式文档版本搜索提示；规划未给域名时，可从真实搜索结果的版本路径构造第二次搜索提示，最多两次搜索，不将推测 URL 直接授权抓取。
- 修复后 [Multi-Agent](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/4873064f-93ef-4dc1-863b-481f5fe62260)以 partial 状态给出有依据的核心对比，正确性 1、证据支持 0.95，通过验收；[Workflow](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/b7f52f0e-ae38-41bb-b468-ae40be947b78)仍只拿到 3.11 的异常说明页，核心 TaskGroup/gather 资料缺失，正确性 0.25，门禁返回失败。版本定向检索的召回稳定性仍需改进。
- [Plan-and-Execute 已通过实验](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/1578d684-fc29-47b3-baae-356fec0e33e2)保留；未将冻结来源通过数合并进联网结果。

## 工程验证与交付边界

- 后端：1472 passed，1 deselected，33 warnings；覆盖来源授权、预算、重试、取消、选材修复、读取窗口和评估对齐。告警包括现有 SDK 弃用/Beta、测试环境未配云端 Key 等。
- 前端：54 项测试通过，lint 与生产构建通过。
- 本轮没有运行 Docker 部署、远程 CI 或生产压力测试；跨任务记忆质量也不在隔离样本验收的结论内。

后续优先处理上表概念层级混淆、必要条件遗漏、过度拒答和联网召回失败，再用新增且未参与调优的案例复验稳定性。已有工程回归和硬约束通过，可继续开发；答案质量门禁目前应保留失败状态。

复现命令与完整规则见[验收说明](../../architecture/acceptance.md)。

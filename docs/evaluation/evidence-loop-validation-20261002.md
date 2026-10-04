# Evidence Loop：实现与离线验证记录

日期：2026-10-02。对应 `docs/superpowers/plans/2026-10-02-evidence-loop-implementation.md` 的 A 范围。

## 当前结论

已实现三模式的统一正文读取、封存需求、原文支持核验、逐项覆盖判断，以及 Plan-and-Execute / Multi-Agent 的缺口定向补查。Answer 和 Report 均消费相同的证据契约，但结果身份分开；Workflow 不新增外层补查循环。

这是**离线行为验证**，不是新的真实模型质量评分，不证明已经生产就绪。全仓库静态检查尚未通过，不能把本轮记录写成“全部工程门槛通过”。本轮没有新增付费 Provider、搜索或裁判调用。

## 实现要点

| 边界 | 本轮实现 | 行为依据 |
| --- | --- | --- |
| 正文读取 | `read_evidence` 只读现有 EvidenceStore；可信租户、调用者与授权由宿主传入 | 跨租户/越权、授权撤销后 replay 与等待中的 follower 均不得读取；SQL 已删除记录不误映射为 superseded |
| 有界视图 | query 与 start 互斥；最多 3000 字符，含定位信息的完整 JSON 不超过 4000 字符 | Unicode、JSON 转义、尾部原文、原文范围往返；读取不新增抓取/网络次数 |
| 固定目标 | 首次规划封存 r1…r6，描述最多 500 字符；无效分解降级为原问题的整体要求 | 三种规划节点均测试无效分解、长任务与旧中间 checkpoint 拒绝继续 |
| 支持核验 | evaluator 只认证本次实际可见 passage 内唯一出现的逐字 quote；坐标、版本和 hash 由宿主计算 | 摘要/标题/元数据、重复 quote、被 token 丢弃的片段不能认证 Finding |
| 需求覆盖 | 每项 covered 必须引用有效 Finding；未知/遗漏需求、无支持结论不能完成 | missing / conflicting 不因模型返回 complete 自动消失 |
| 定向补查 | P&E 最多 2 轮 replan、MA 最多 1 轮 follow_up；每个补查批最多 2 个方向 | 目标必须属于当前缺口；实际 Store 查询/读取与目标 r2 传播通过真实策略图验收 |
| 无进展停止 | 按 URL+hash、有效支持范围、已覆盖需求判断；一整轮补查完成后才检查 | 缓存重复不无限循环；同来源新增有效原文范围算进展；旧缺口可关闭，诊断历史保留 |
| 最终回答 | 支持范围优先选段；未可见来源不能认证引用；固定目标与当前缺口始终保留 | Answer / Report 参数化验收；删掉第一个来源后第二个来源编号不串位 |
| 事实记忆 | 新 FACT 同时要求有效来源 ID 与宿主核验；写入前复核 ACTIVE、版本/hash 和原文 | 无支持、篡改范围、已删除/过期来源、存储失败均不写入；偏好、TTL 与原子 upsert 保持 |
| 轨迹与 oracle 隔离 | 记录有界 ID/hash/范围/visibility，不默认保存正文审计；gold 仅评分侧使用 | 修改 gold 答案/参考调用不改变实际模型输入；导出最多 512 条 view 事件并过滤未知字段 |

原文位置采用 Python 字符索引：从 0 开始、end 不包含端点；行号从 1 开始。它不是 UTF-8 字节或 JavaScript UTF-16 偏移。

## 设计调整与边界修复

1. 领域覆盖 DTO 放在独立 `domain/coverage.py`，再公共导出，避免 research / execution 循环导入。三模式复用同一评估实现，但保留不同调度图，不包装成三个标签的同一流程。
2. 规划降级时，发现用 query 取原问题前 1000 字符，以满足已有 TopicQuery 上限；**原问题、全部约束与整体完成标准不截断**。这是对计划中 `[question]` 示例与既有字段上限冲突的修正。
3. 回答材料放在本次调用的局部对象中，正文只读一次，格式/长度合并修复复用材料；正文不进入控制状态。被整体预算丢弃的来源及其事实清单不认证。
4. 最后审查发现回答预算只计算了内层 prompt，漏掉 `task_messages` 的完整任务/约束外层。Answer / Report 各新增失败回归后修复：先预留外层估计 tokens 和 32 tokens 消息开销，再选择正文。固定块溢出时不发出模型调用。该估计沿用 cl100k_base，**不是 Provider 实际 token 计费值**。
5. evaluator 与 writer 的单个来源读取异常不会抹掉健康来源；缺少支持的事实不进入有效清单。新增 metadata/body 读取故障回归，取消信号继续传播，异常细节不拼入模型 prompt。
6. 受控记忆评测资产升级为 `backend/src/deeptrace/eval/data/memory/lifecycle-v2.json`，v1 保留。v2 的期望事实与受控来源原文对应，仍只在评分侧使用。它是合成生命周期资产，**不能把 v1/v2 分数直接比较为项目质量提升**。

## 验证执行记录

以下命令均在 `backend` 下执行，生产与独立评分环境不混装。

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 全量非真实测试：`.venv/Scripts/python.exe -m pytest -q -m 'not real' --tb=short` | **913 passed，2 deselected，118.54 秒，退出码 0** | 不包含付费质量测试 |
| 隔离评分适配：`.venv-ragas/Scripts/python.exe -m pytest evaluation/tests -q --tb=short` | 34 passed，6.12 秒，退出码 0 | 验证 Ragas 适配与数据契约，不表示裁判已经评分 |
| 三模式 × Answer/Report 应用集成 | 6 passed | 实际注册策略图、Gateway、EvidenceStore 与共享 Agent，不仅改变模式标签 |
| 三模式故障矩阵 | 18 passed，6.95 秒，退出码 0 | 瞬时失败、空页改查下一来源、全空来源、搜索失败、持续瞬时失败、致命错误 |
| writer 支持/预算/读取异常/取消边界 | 17 passed，1.86 秒，退出码 0 | 固定块溢出不调用模型；单来源失败不破坏健康来源 |
| 记忆与相关响应选集 | 82 passed | 包含事实准入负例、偏好、删除、隔离、TTL、SQL 事务；与全量用例重叠，不能相加 |
| 定向 Ruff | 通过，退出码 0 | 61 个核心改造文件；仅忽略已有 `citations.py` 的 PIE810；eval/scripted、env、trajectory 另行通过无忽略检查 |
| 全仓库 Ruff：`uv tool run --offline ruff check src tests --output-format concise` | **115 errors，退出码 1** | 主要在 API/worker/旧策略辅助/既有评测等未改范围；含 F821、导入及风格告警；本轮没有批量修复无关模块 |
| `git diff --check` | 通过，退出码 0 | 有 LF/CRLF 转换提示，不是 diff 校验失败；暂存区为空 |

定向检查不替代全仓库质量闸。保留 Ruff 的既有告警不是宣称它们无害；后续应独立清理并验证，尤其 worker/context 中的未定义类型引用。本轮不安装新运行依赖、不提交混合工作区，不改用户既有评测/部署工作。

## 可复跑的离线样本

最终代码快照样本位于 `tmp/evidence-loop-20261002-verified/report.md`：`../../tmp/evidence-loop-20261002-verified/report.md`（本地实验留样），完整记录、来源、实际工具调用与 view 范围位于同目录 `records.json`、`tool_eval.json`、`quality_eval.json`、`manifest.json` 及逐样本目录。脚本模型只复制实际可见正文，不联网，也不调用裁判。CLI 退出码 0。

```powershell
.venv/Scripts/python.exe -m deeptrace.eval --model scripted --response-mode answer --modes plan_execute,workflow,multi_agent --run-prefix evidence-loop-verified --out D:/Dev/Projects/agent_new/tmp/evidence-loop-20261002-verified
```

| 模式 | Answer 合成 smoke 次数 | completed | 每次实际工具调用 | 每次模型调用 | 每次 view 事件 |
| --- | --- | --- | --- | --- | --- |
| **Plan-and-Execute（主模式）** | 3 | 3 | 3 | 8 | 2 |
| Workflow | 3 | 3 | 3 | 8 | 2 |
| Multi-Agent | 3 | 3 | 3 | 8 | 2 |

3 次工具调用为 search / fetch / read；2 条视图分别来自 evaluator 与 writer。该 CLI 是 Answer smoke，Report 验收来自上面的独立应用集成测试；没有将 Report 混入 9 次 Answer。执行顺序按 P&E → Workflow → MA，旧 CLI 摘要目前按模式字母排序展示，主验收以本表为准。

manifest identity SHA-256：`431d9183e613bd08cbe0241302900ddac4e27764ecbd32017f1fac3265eab53c`。manifest 记录 source_files 指纹和 dirty=true；Git HEAD 为 `606cfbeac8297aa5b7de4f0230a3d61c06fd50e9`，**不能把这个旧 HEAD 当作包含本轮未提交实现**。资料/数据集指纹和全部运行身份保留在原始 manifest，不只靠摘要数字复现。

最终以 PowerShell Get-FileHash 复核 manifest 的 184 个源文件/受控资产指纹，0 个不一致；9 条记录的 artifact_errors 为 0、judge_attempted 为 0。生成后仅更新人类阅读文档，不覆盖任何已有实验快照。

初次样本位于 `tmp/evidence-loop-20261002-offline/`：3 道合成 smoke × 三模式 = 9 次运行，9 次 completed；每模式 3 次。该样本在最后边界修复前生成，其 manifest 是当时快照，保留原件，不覆盖成最终代码身份。

gold_coverage、合法引用编号和脚本 completed 仅说明资料/管线有效，**不等于 Answer 正确率、Faithfulness、引用语义正确率或真实端到端成功率**。离线集成的缺口题中，Workflow 应保持 partial，P&E/MA 应执行目标补查再完成，不能为了统一表格把 Workflow 强改成成功。

## 审查与尚未覆盖的验收

按 code-review-and-quality 做了当前会话的正确性、简化程度、架构、权限与性能自审；没有可用的独立子代理，不伪称有第二模型审查。核对授权先于 replay、无 runtime→eval 导入、控制状态不保存全文、循环限制不扩大、正文仅作不可信数据、记忆准入 fail closed。批量来源元数据/单次正文材料复用避免记忆 consolidation 与回答格式修复中的重复读取。

逐字 quote 核验仅证明该文字在本次可见原文中出现，**不自动证明 claim 被蕴含，也不保证每个答案句子被支持**。语义正确性仍需要真实模型独立评分和人工校准。若来源内容、标题或历史记忆包含注入文字，宿主权限和配置不可由这些文字改写；没有声称消灭所有语义层提示注入。

以下仍未验收，不纳入本轮完成声明：

- **B：** 三模式硬进程重启、durable Ledger、本地显式恢复、全运行 Provider 尝试预算与回答额度预留。已有 checkpoint 往返/受控恢复回归不等于该矩阵通过。
- **C：** 抓取正文保存上限、静态格式支持、动态网页回退与真实公开网页端到端。
- Docker daemon / 完整部署 / 远端 CI，本轮未执行。
- 新真实 Plan-and-Execute + Answer 主基线与改造后配对评分，其他两种模式分别报告；Report 独立验收，不与 Answer 混合。
- 全仓库 Ruff 质量闸与人工代码审查。

既往 Workflow + Report 单题 pilot 的 F1=0.50、Faithfulness=0.48 不是本次主基线，也不能用本轮 scripted 9/9 替换或宣称提升。下一次付费校准应先冻结运行列表、模型与温度、资料/工具条件、长期记忆关闭、各运行与整批调用上限，获得新额度确认后执行；保留失败/partial/评分失败，不删除低分，不给缺失评分补零。

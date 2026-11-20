# Harness 运行时优化与验收

日期：2026-10-10。基于共享工作区实施，保留原有未提交修改。沿用 LangGraph、现有数据库、三种研究策略和证据管道，没有增加服务或升级依赖。优化前依据见[调研](2026-10-10-harness-engineering-review.md)。

## 已完成的变化

| 问题 | 实现 | 可核对产物 |
| --- | --- | --- |
| 工具循环绑定研究 State | 六个显式节点的共享路由；研究与文档任务提供各自 State/Context/完成规则 | harness/loop.py、examples/local_documents.py |
| 工具名称只支持封闭枚举 | 保留内置契约，新增宿主注册的 CustomToolName 与 ToolSpec；能力显式授予 | domain/tools.py、tools/registry.py、tools/policy.py |
| 模型预算重启后清零 | 调用前 SQL 保守预留，调用后结算，恢复原始限制与期限，CAS 拒绝旧版本覆盖 | model_budget.py、persistence/model_budget.py |
| 工具预算恢复失败仍可执行 | seed 失败拒绝派发；Local Ledger 也改为 SQL | application/assembly.py、persistence/execution_ledger.py |
| 生产结果用量为空／零 | Local 与 Worker 接入已观察 usage、缺失标识、角色模型耗时及脱敏事件 | observability/model_metrics.py、agent_adapter.py、runtime/local.py |
| run 进程资源缺少回收 | 完成／失败／取消后释放网关与 recorder；持久快照独立保留 | HarnessRuntimeBundle.release_run |
| 组合根包含供应商与建表逻辑 | 抽出 model_provider.py 与 persistence/schema.py | application/assembly.py |
| 上下文协议依赖中文标签 | TaskContext 元数据校验，任务文本仍显式可见 | harness/model_context.py、prompts.py、model_gateway.py |

不是将整个研究执行器改成通用框架：agent_tools、Finding、证据覆盖与收尾角色额度仍是研究领域规则。共享循环负责路由，领域节点负责治理细节与完成语义。

## 恢复与用量语义

调用前持久化次数和估算预留；供应商 usage 返回后结算实际输入。失败、取消、未知返回保留保守消耗，恢复不会退款。原始 deadline 包含停机时间，预算限制在恢复时也不会被新配置扩大。SQL 读取、保存、损坏或 revision 冲突失败时停止派发。

公开总 input/output/total 只有观察完整时才是实测值；缺失返回 null，observed_usage 保留已知子集。角色累计模型时间不是整次任务 wall time。`provider_attempts` 字段统计已准入的 Gateway 尝试，校验或绑定失败时可能还没触达远端。当前生产关闭内部重试，正常路径一次对应一次请求；带内部重试的自定义网关不能据此推导真实请求次数。

SQL 与远端模型没有原子提交，保守预留可能多算，远端执行仍可能未知。CAS 保护快照写入，不是外部调用的 fencing；Worker 租约、结果 owner guard、Checkpoint 与工具 Ledger 有各自边界。Local 启动仍标记中断任务，未加入自动续跑 UI。

## 第二任务的复用证明

backend 目录运行：

```powershell
uv run --no-sync python -m deeptrace.examples.local_documents README.md --root .. --offline
```

DocumentState 不包含 ResearchTopicInput/Finding。脚本模型产生一次文档工具请求，真实工具通过权限、参数、安全、预算和账本执行；ToolMessage 返回后再调用模型退出。正常路径两次模型派发，用量未知，工具失败为受控终态。

文档工具限制在宿主目录内，允许少量文本扩展名，最大 1MB、预览 4000 字符；阻塞读取在线程执行。它只读，未实现命令或写入；路径约束不能等同 OS 沙箱，也不能保证抵御并发恶意符号链接替换。示例使用内存账本，生产 Local/Distributed 使用 SQL。

## 数据库升级

新增 `model_run_budgets` 表，包含 run_id、revision 与版本化 JSON 快照。Local 补表逻辑同时确保工具 Ledger 表存在；MySQL 使用新增 Alembic `20261010_01`，保留历史迁移。分布式部署需先执行 `uv run --no-sync alembic upgrade head`。本轮未连接真实 MySQL/Redis 或更新现有运行数据库。

## 验收

| 命令／检查 | 结果 |
| --- | --- |
| backend：`uv run --no-sync pytest -m "not real" -q --tb=short` | 1383 passed、2 deselected，141.65 秒 |
| 最后涉及运行时文件的专项回归 | 38 passed |
| frontend：`npm test` | 52 passed（12 个文件） |
| frontend：`npm run build`、`npm run lint` | 通过 |
| 本轮相关 Python 文件 Ruff | 通过 |
| `git diff --check` | 通过 |
| `alembic heads` | 单一 head：20261010_01 |
| `alembic upgrade 20260914_01:head --sql` | MySQL 新增表 SQL 生成成功，无实际数据库变更 |
| 独立文档离线 CLI | 中文可读、正常退出、两次派发、usage 未知 |
| 文档本地链接核对 | 19 页、216 个链接，无缺失 |

覆盖恢复额度／期限、SQLite engine 重建、取消消耗、保存失败、损坏快照、版本冲突、未知用量、生产适配与资源释放、工具拒绝／越界、共享循环与第二任务。按正确性、简洁性、架构、权限和资源五项自查，保留显式节点组合和领域适配，没有引入通用插件平台。

以上为优化完成时的离线验收。随后按用户要求切换 `deepseek-v4.1-flash`，新增真实 API、联网研究及文档循环测试，结果与失败诊断见 [DeepSeek 真实重测](2026-10-10-deepseek-live-retest.md)。历史作品、质量评分和时延保留原版本语义；离线回归不能证明开放回答质量提升、真实提速或高并发可靠性。

## 面试材料

本地 `docs/resume/` 已更新架构口述、运行时追问、成本恢复、源码路线、简历和事实核对，定位为“知识研究场景验证共享 Agent 运行时”。该目录由既有 .gitignore 忽略，未改变忽略规则；作品 PDF 本轮未重新制作。

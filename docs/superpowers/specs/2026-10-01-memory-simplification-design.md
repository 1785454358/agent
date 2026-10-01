# Harness 简化：记忆入口与证据核验

日期：2026-10-01。状态：设计待审阅，尚未修改生产代码。

## 目标

在现有记忆架构上消除重复准入与重复证据读取，使代码职责和数据库调用更明确。不新增 Memory Agent、记忆服务层、异步队列、框架依赖或配置选项。

工作记忆仍由 State / Checkpoint 持有，长期偏好和事实由 Memory Store 持有，网页正文由 Evidence Store 持有，Chroma 只提供检索候选。保持版本、tombstone、来源和注入预算，不以删掉保护换取代码更短。

## 核查结果

1. `lifecycle._memory_update_node` 先调用 `policy.can_store`，随后 `remember` 再调用同一策略。拒绝与存储失败目前通过不同响应表达，因此移除预检时必须保留错误分类。
2. `_consolidate_memory` 对每条 finding 调用 EvidenceStore.get_many，多个 finding 共用同一证据时重复读取；还重复构造 ResearchOutcome 的 Evidence ID 集合。
3. SQL EvidenceStore.get_many 内部循环调用 get，每个 ID 单独开启会话和查询，并非真正批量读取。内存适配器已经在一次锁内读取。
4. 内存与 SQL 的 get_many 都是严格读取：任意 ID 缺失或不属于 workspace 时抛 KeyError。直接将所有 finding 合成一次调用会放大单条缺失的影响。
5. MemoryRecord 每条来源上限 20；自动整理最多处理前 20 条 finding。先构造合法候选，再汇总来源，可将一次整理的来源集合限制在最多 400 个 ID。
6. 语义检索器已经负责索引、语义排序、权威回查与故障词汇回退；生命周期选择偏好和可选事实检索。这些条件不是同一种重复控制路径，不需要为收敛而再建检索框架。
7. EVIDENCE / EPISODE、namespace_for、apply_lifecycle 有现有契约或公开导出。没有生产自动写入这些类型，不等于可以无成本删除持久化枚举和公开接口。

## 方案比较

### 推荐：小范围入口与查询收敛

保持架构和公共协议，统一一次准入；去重核验当前 findings 的证据，正常情况批量读取；SQL 底层使用分组 IN 查询。缺失证据只阻止依赖它的候选事实。

收益可以直接验收：合法批次最多 400 个去重来源，一次 SQL 元数据查询；相同来源不随 finding 数量被反复读取。代价是需要明确一个拒绝异常和一个有界缺失回退分支。

### 不采用：统一所有检索模式为新的 Memory Service

可以隐藏 lexical / semantic 的分支，但会牵动装配、Retriever 协议和索引职责。现有语义回退已经有效，单纯包一层不能减少系统概念，本次不做。

### 不采用：接入完整记忆框架或背景记忆 Agent

会新增依赖、模型调用与恢复 / 调度边界，超出当前“简化、标准化”的诉求。当前已有的 findings 可以确定性整理，无需另一个模型开放式提取记忆。

## 推荐设计

### 1. 一个写入准入边界

`remember(store, record, policy, source=...)` 是生产写入入口，执行一次策略检查、TTL 设置和原子 upsert。

- 移除显式保存节点的 can_store 预检。
- write.py 定义 `MemoryWriteRejected(ValueError)`；策略拒绝时由 remember 抛出，消息仍为 `memory_write_rejected`。已有捕获 ValueError 的调用者仍有效。
- 显式保存节点单独捕获此异常，返回原来的 `memory_rejected`，不回复已保存。
- Store 的普通 ValueError / RuntimeError 不被误判为策略拒绝，仍记录降级并返回 `memory_unavailable`。
- 现有 `MemoryWritePolicy.can_store` 对外保留，规则、来源、30 天 FACT TTL 和用户显式重新保存语义不变。
- 只有权威存储成功才尽力索引；索引失败不推翻已经成功的权威写入。取消不被普通异常分支吞掉。

不新增写入结果状态机、策略基类或注册器。

### 2. 自动整理一次去重核验

流程：

1. 固定当前时间和当前结果允许的 Evidence ID 集合。
2. 对前 20 条 finding 检查来源属于当前结果，并构造 MemoryRecord 候选。超长内容、超出 20 条来源等记录仍由领域契约拒绝；单条候选失败不阻止其他候选。
3. 汇总合法候选的去重来源 ID，调用一次 workspace 范围内的 get_many。没有候选时不读证据。
4. 仅当严格批量读取抛 KeyError 时，逐个读取去重 ID，跳过缺失项；每个唯一来源最多再尝试一次。其他存储故障不启动逐条重试风暴，而是记录一次降级，本轮不写无法核验的事实。
5. 形成 ACTIVE 来源 ID 集合，仅保存所有引用均存在且 ACTIVE 的候选。保留逐条 Memory Store 写入失败隔离；一个 upsert 失败仍可保存其他候选。
6. 最后统一尽力索引已保存的 ACTIVE 记录。删除标记返回值不进入索引，不因整理重放复活 tombstone。

KeyError 回退的最坏代价为一次失败批次加最多 400 次去重读取，不声称缺失批次一定更快；正常批次不进入回退。缺失数据仍发出降级观测，不能把“未能找到”伪装成来源已核验。

只读取证据元数据，正文不进入 MemoryRecord、图 State 或 Checkpoint。检查来源存在不等于已经验证 claim 被原文蕴含，也不提供跨 Evidence Store 与 Memory Store 的事务快照保证。

### 3. SQL get_many 真正批量化，保留公共契约

不修改 EvidenceStore 协议、数据库 schema 或迁移文件。

- 对输入进行现有标识符校验、去重，以 tenant_id 和 Evidence ID 集合执行 IN 查询。
- 每批最多 400 个唯一 ID；一般记忆整理仅一批。更大的已有调用使用同一会话中的多个有界批次，不退化成逐 ID 查询，不因数据库绑定参数上限破坏已有调用。
- 查询不加载 body 列，只构建 Evidence 元数据；正文仍通过 read_body / read_chunks 获取。
- 返回顺序和重复项与输入一致。每个返回位置使用独立记录副本，不因批量映射引入共享可变对象。
- 空列表返回空 tuple，不查数据库。缺失或其他 tenant 的 ID 仍抛同类 KeyError，不改成静默部分成功。
- 其他租户的相同 ID 不能借助批量 IN 读取；状态仍返回实际元数据，由记忆生命周期决定是否为 ACTIVE。

## 召回与兼容边界

这次只在 lifecycle 内使用已有非可选 HarnessContext，减少重复 context 访问和 namespace 切片，不新增统一检索服务。

保留偏好优先、事实相关性排序、语义失败时词汇回退、向量命中后权威回查、最新版本优先、状态 / 过期过滤和条数 / token 双预算。should_recall 的现有签名、MemoryRetrieverPort、SemanticMemoryRetriever、持久化类型和遗忘导出不变。

不删除历史记忆或向量，不自动启动 apply_lifecycle，不引入新的遗忘对话意图，不扩展 EVIDENCE / EPISODE 自动写入。后续若要删除兼容类型或改检索协议，应独立设计数据迁移，不能混入这次查询优化。

## 实施文件

生产修改限定为：

- `backend/src/deeptrace/harness/memory/write.py`：明确拒绝类型，保持单一准入。
- `backend/src/deeptrace/harness/memory/lifecycle.py`：去掉重复预检，整理候选、去重来源与部分失败语义；不重做召回框架。
- `backend/src/deeptrace/persistence/evidence_store.py`：批量元数据查询，保留严格读取契约。

测试修改：

- `backend/tests/harness/memory/test_lifecycle.py`：显式拒绝与存储失败分类、共享来源去重、有效 / 缺失 / 非 ACTIVE 混合、候选边界与降级。
- `backend/tests/harness/memory/test_memory_transactions.py`：保留写入准入、NOOP、并发版本、tombstone 和 SQL 原子性回归。
- `backend/tests/persistence/test_evidence_store.py`：真实 SQLite 查询次数、排序 / 重复副本、空输入、参数分组和 workspace 边界。
- `backend/tests/tools/test_evidence_store.py`：保持内存 / SQL 读取契约一致。

更新 `docs/architecture/memory.md` 与实施计划；用户已有引用 / 评测 / 配置 / 其他文档修改不纳入。

## 验收

先增加并观察能区分当前实现的失败用例，再做最小修改：

- 显式保存一次准入检查，拒绝返回 memory_rejected，Store 普通异常返回 memory_unavailable。
- 20 条合法 finding 共享一个来源，20 条事实正常保存且来源仅批量读取一次；不是仅检查假对象调用次数，必须检查真实 Memory Store 结果。
- 一条缺失来源不阻止另一条有效事实保存；跨 workspace 或 SUPERSEDED 来源不进入自动事实记忆。
- 无候选、超过单条来源 / 正文上限、引用不属于本轮结果时，不产生不合法写入。
- SQL 真实查询探针确认 1–400 个去重 ID 一次查询；超过 400 个分组读取，无正文列；返回顺序、重复独立副本、缺失 KeyError 和空输入正确。
- 保留故障隔离、权威写入后索引失败、取消、版本 / tombstone、召回来源 / token 预算以及完整 Harness 恢复测试。

运行记忆与证据专项、响应与 Harness 集成，再运行全仓库 `pytest -m "not real"`；检查修改文件 Ruff、格式和 diff。单个 SQL 查询与去重次数是可验证目标，不预先承诺生产延迟提升百分比。

## 参考与取舍

[LangGraph 记忆概念](https://docs.langchain.com/oss/python/concepts/memory) 区分线程内 State / Checkpoint 与跨线程 namespace Store，并描述运行内写入和后台写入的取舍。本项目保留现有分层与运行内整理，不把后台任务作为“标准架构”的必要条件。

[Mem0 更新操作](https://docs.mem0.ai/core-concepts/memory-operations/update) 的更新与历史追踪提供参考；本项目继续使用现有确定性版本策略，不接入其服务。本设计的证据准入、严格读取和错误分类是针对本项目的工程选择，不冒称这些框架规定了同一接口。

## 审阅

- [x] 检查记忆入口、召回、版本、遗忘、SQL / 内存证据契约和测试消费者。
- [x] 比较小范围收敛、增加服务层、接入完整框架的取舍。
- [x] 明确缺失证据不扩大失败、批量上限、接口兼容与可验证目标。
- [x] 自审无类型删除、数据迁移、配置扩展或无界重试。
- [ ] 用户审阅此文档，确认实施范围。
- [ ] 审阅后用 writing-plans 制定实施计划，再开始 TDD。

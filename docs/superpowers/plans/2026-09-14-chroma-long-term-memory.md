# Chroma Long-Term Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将长期记忆升级为 MySQL 结构化权威存储、Chroma 语义索引和本地 BAAI/bge-m3 向量生成的可恢复检索链路。

**Architecture:** MySQL 先按 user/workspace 作用域、记忆类型、状态和有效期筛出候选记录。BGE-M3 为查询和候选内容生成归一化向量，Chroma 只保存 `memory_id`、受限正文、向量及检索元数据并在候选 ID 集合中执行 TopK；命中的 ID 必须回查 MySQL 才能进入 Harness 上下文。MySQL 是唯一事实源，Chroma 写入失败不阻断记忆保存，后续召回会按内容哈希修复索引。

**Tech Stack:** Python 3.12、LangGraph、SQLAlchemy、MySQL、Chroma、sentence-transformers、BAAI/bge-m3、Docker Compose、pytest

**Spec:** `docs/superpowers/specs/2026-09-10-langgraph-agent-harness-refactor-design.md` 第 13 节，并以 2026-09-14 用户确认的 MySQL + Chroma + BGE-M3 三段式检索约束为准。

## Global Constraints

- 三种研究策略的业务语义保持不变。
- MySQL 是长期记忆的权威数据源，Chroma 不得绕过 MySQL 直接向 Graph State 注入正文。
- 检索顺序固定为 MySQL 结构化过滤、Chroma TopK、MySQL 按 memory_id 回查。
- 向量模型固定使用本地 `BAAI/bge-m3`，每个 Worker 进程懒加载一次，不在单次请求内重复加载。
- Chroma 故障时保存链路可用，召回降级到现有确定性排序并记录错误。
- 已发布迁移不修改，只增加新的 Alembic 迁移。
- Graph State 只保存召回后的受限记忆片段和 ID，不保存向量。

---

### Task 1: 记忆领域模型与结构化查询端口

**Files:**
- Modify: `backend/src/deeptrace/domain/memory.py`
- Modify: `backend/src/deeptrace/harness/context.py`
- Modify: `backend/src/deeptrace/harness/memory/store.py`
- Modify: `backend/src/deeptrace/persistence/memory_store.py`
- Test: `backend/tests/harness/memory/test_memory_policies.py`
- Create: `backend/tests/persistence/test_memory_store.py`

**Interfaces:**
- Produces: `MemoryRecord.importance: float`；`MemoryStorePort.list_eligible(namespaces, memory_types, now)`；`MemoryStorePort.get_many_by_ids(memory_ids)`。

- [ ] **Step 1: Write the failing tests**，覆盖 importance 范围校验、按 namespace/type/status/expiry 过滤，以及按 `memory_id` 保序回查。
- [ ] **Step 2: Run tests to verify they fail**，运行 `uv run pytest tests/harness/memory/test_memory_policies.py tests/persistence/test_memory_store.py -q`，预期因字段和方法不存在失败。
- [ ] **Step 3: Write minimal implementation**，为内存与 SQL Store 提供同一端口；SQL 实现只返回 ACTIVE/STALE/CANDIDATE 且未过期的候选。
- [ ] **Step 4: Run tests to verify they pass**，重复运行步骤 2。

### Task 2: BGE-M3 与 Chroma 适配器

**Files:**
- Create: `backend/src/deeptrace/harness/memory/embedding.py`
- Create: `backend/src/deeptrace/harness/memory/vector_index.py`
- Create: `backend/src/deeptrace/persistence/chroma_memory.py`
- Create: `backend/tests/harness/memory/test_embedding.py`
- Create: `backend/tests/persistence/test_chroma_memory.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`

**Interfaces:**
- Produces: `EmbeddingGateway.embed_documents(texts)`、`EmbeddingGateway.embed_query(text)`；`MemoryVectorIndex.sync(records)`、`query(query_embedding, candidate_ids, limit)`、`delete(memory_ids)`；`BgeM3EmbeddingGateway` 与 `ChromaMemoryVectorIndex`。

- [ ] **Step 1: Write the failing adapter tests**，使用轻量假向量器和临时 Chroma 客户端验证 upsert、ID 约束、TopK 与内容哈希更新。
- [ ] **Step 2: Run tests to verify they fail**，预期模块不存在。
- [ ] **Step 3: Add the Chroma dependency and lock it**，通过 `uv add chromadb` 更新声明与锁文件。
- [ ] **Step 4: Write minimal adapters**，BGE 编码放入 `asyncio.to_thread`，输出归一化 `float32` 列表；Chroma ID 等于 `MemoryRecord.id`，metadata 包含 namespace/type/status/content_hash。
- [ ] **Step 5: Run adapter tests to verify they pass**。

### Task 3: 语义召回编排与降级

**Files:**
- Create: `backend/src/deeptrace/harness/memory/retriever.py`
- Modify: `backend/src/deeptrace/harness/context.py`
- Modify: `backend/src/deeptrace/harness/graph.py`
- Create: `backend/tests/harness/memory/test_semantic_retriever.py`
- Modify: `backend/tests/harness/test_graph.py`

**Interfaces:**
- Consumes: Task 1 的结构化 Store 和 Task 2 的向量端口。
- Produces: `SemanticMemoryRetriever.recall(namespaces, memory_types, query, now, limit)` 与 `index(records)`。

- [ ] **Step 1: Write failing orchestration tests**，证明调用顺序为 MySQL filter、Chroma query、MySQL refetch，并验证 Chroma 异常时走 `select_memories`。
- [ ] **Step 2: Run tests and confirm expected failures**。
- [ ] **Step 3: Implement the coordinator**，召回前同步候选索引，向量结果结合相似度、importance、confidence、recency 做稳定排序。
- [ ] **Step 4: Wire graph recall and writes**，记忆写入 MySQL 成功后异步尝试索引；索引失败仅记录日志。
- [ ] **Step 5: Run focused Harness tests**。

### Task 4: MySQL 迁移与运行时装配

**Files:**
- Modify: `backend/src/deeptrace/persistence/orm.py`
- Create: `backend/alembic/versions/20260914_01_add_memory_retrieval_fields.py`
- Modify: `backend/src/deeptrace/config/settings.py`
- Modify: `backend/src/deeptrace/application/assembly.py`
- Modify: `backend/tests/config/test_settings.py`
- Modify: `backend/tests/application/test_research_service.py`
- Create: `backend/tests/persistence/test_memory_migration.py`

**Interfaces:**
- Produces: query-critical MySQL columns `memory_id`、`memory_type`、`status`、`importance`、`confidence`、`created_at`、`expires_at`；配置 `memory_retrieval`、`chroma_url`、`chroma_collection`、`memory_top_k`。

- [ ] **Step 1: Write failing settings, migration and assembly tests**。
- [ ] **Step 2: Run them and verify missing behavior fails**。
- [ ] **Step 3: Add a forward-only migration**，从现有 JSON payload 回填新列并创建候选过滤索引。
- [ ] **Step 4: Assemble semantic memory only where configured**，distributed 使用 `HttpClient`，local 使用持久化客户端；模型与客户端生命周期属于 runtime bundle。
- [ ] **Step 5: Run focused tests and Alembic SQLite compatibility checks**。

### Task 5: Docker 与真实链路验证

**Files:**
- Modify: `docker-compose.yml`
- Create: `docker-compose.semantic.yml`
- Modify: `.env.docker.example`
- Modify: `backend/tests/deployment/test_compose_config.py`

**Interfaces:**
- Produces: 基础 Compose 同时启动 MySQL、Redis、Chroma、API、Worker；仅 Worker 挂载 BGE-M3，API 通过队列提交任务，不加载本地模型。

- [ ] **Step 1: Write failing Compose contract tests**，要求 Chroma 健康检查、持久卷、Worker 健康依赖与仅 Worker 模型挂载。
- [ ] **Step 2: Run and verify failures**。
- [ ] **Step 3: Update Compose and environment examples**。
- [ ] **Step 4: Run Compose config validation, MySQL migration, Redis/Chroma health checks**。
- [ ] **Step 5: Run one real API smoke test**，验证写入长期记忆、跨 thread 语义召回和普通研究链路。

### Task 6: 对外文档与仓库展示

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `docs/README.md`
- Modify: `docs/resume/多模式深度研究Agent简历项目材料.md`
- Modify: `docs/resume/多模式深度研究Agent面试与学习资料/01-项目介绍与表达.md`
- Modify: `docs/resume/多模式深度研究Agent面试与学习资料/04-Harness核心机制.md`
- Modify: `docs/resume/多模式深度研究Agent面试与学习资料/05-面试高频问题与答案.md`
- Create: `docs/resume/作品展示制作指南.md`
- Create: `.github/workflows/ci.yml`
- Delete: `1.txt`

**Interfaces:**
- Produces: 与当前实现一致的快速开始、Mermaid 架构图、90 秒演示分镜、GitHub 展示清单与 CI。

- [ ] **Step 1: Add documentation contract tests or executable link/config checks**，检查旧 Basic/Deep/ReAct 与“无向量召回”等失实描述消失。
- [ ] **Step 2: Rewrite the three entry READMEs**，明确 Harness 公共治理、策略子图、MySQL/Chroma/Redis 所有权及启动命令。
- [ ] **Step 3: Update resume/interview claims**，只描述已验证行为。
- [ ] **Step 4: Add the showcase guide and CI, remove `1.txt`**。
- [ ] **Step 5: Run link grep, full non-real test suite and clean-tree review**。

## Self-Review

- Spec coverage: MySQL 权威存储、Chroma TopK、BGE-M3、作用域过滤、回查、降级、Docker、文档和作品展示均有对应任务。
- Placeholder scan: 无 TBD、TODO 或省略实现步骤。
- Type consistency: Store 候选记录进入 `sync/query`，向量命中只返回 ID/距离，最终由 `get_many_by_ids` 产生 `MemoryRecord`。

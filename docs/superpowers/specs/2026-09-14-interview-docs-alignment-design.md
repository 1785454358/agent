# 面试与学习资料事实对齐设计

## 目标

让简历材料、项目介绍、架构图、源码导读和高频问答与 `fc056b9` 后的真实实现一致。保留现有分文件结构，不重写已经准确的 Harness、策略子图、Tool Gateway、Evidence 和恢复内容。

## 修改范围

### 简历项目材料

- 项目描述删除“可多轮追问”，继续以 Harness、三种研究策略和按需报告为主线。
- Redis 职责拆成 Streams 投递、Pub/Sub 唤醒和取消键传播。
- 删除“Evidence 与工具调用恰好一次”的承诺，改成 Checkpoint 与 Ledger 重放已提交结果，并明确 Provider 成功、Ledger 提交前仍存在重复窗口。
- 长期记忆的“唯一来源”改为“受控 Evidence 引用”。更新规则限定为相同 `namespace + type + subject` 身份下的版本链，不能声称系统已经完成同主题事实合并。

### 项目介绍与架构图

- 90 秒介绍准确区分 Redis Streams 与 Pub/Sub。
- 长期记忆召回增加运行模式限定。Distributed 使用 MySQL 权威记录与 Chroma；Local 使用进程内 Memory Store 与本地 Chroma，结构化记忆不跨进程重启。
- Mermaid 中数据流改为正文或查询先由 BGE-M3 编码，再进入 Chroma；所有权图同时标明 Local 与 Distributed 的差异。

### 源码导读与高频问答

- BGE-M3 改为“执行进程内懒加载”。Local 在 API 进程加载，Distributed 只在 Worker 加载。
- MySQL 与 Chroma 的回答限定为 Distributed 完整形态，并补充 Local 的持久化边界。
- 更新、遗忘和 exactly-once 的回答与当前代码边界保持一致。

### 新增长期记忆专题

新增 `07-长期记忆源码与面试专题.md`，包含以下内容。

1. 一条记忆从写入到召回的 Mermaid 时序图。
2. MySQL、BGE-M3、Chroma 的数据所有权和字段映射。
3. 用户偏好与研究事实的写入条件。
4. MySQL 候选过滤、候选内 TopK、MySQL 回查和最终重排。
5. MySQL 写入成功而索引失败、Chroma 查询失败、索引残留等故障路径。
6. 版本身份、更新能力、遗忘策略、单租户和 Local 持久化限制。
7. 源码阅读顺序与可脱稿回答的面试题。

阅读目录增加第 07 篇入口。

## 统一表述

- Harness 是项目的运行协议和模块边界，不对应 `HarnessGraph` 类。
- 三种执行行为称为研究策略、研究模式或策略子图，不使用 Profile。
- MySQL 是 Distributed 模式长期记忆的权威数据源，Chroma 是可重建的非权威语义索引。
- 系统控制和降低重复执行，不承诺任意外部副作用 exactly-once。
- 自动遗忘清扫、多租户认证、Local 结构化长期记忆持久化仍未完成。

## 验收

- `docs/resume` 中不再出现 HarnessGraph、Profile 或 exactly-once 能力承诺。
- Redis Streams、Pub/Sub 与取消键的职责不混写。
- BGE-M3 的加载位置同时覆盖 Local 和 Distributed。
- Mermaid 数据流与源码一致。
- 长期记忆专题中的函数名都能在当前源码中找到。
- Markdown 相对链接有效，中文写作检查不出现禁用句式。

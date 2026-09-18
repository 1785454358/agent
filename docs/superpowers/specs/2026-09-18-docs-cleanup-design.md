# Docs 当前态收敛设计

日期：2026-09-18  
状态：用户已确认

## 目标

把 `docs` 从实施过程档案收敛成面向当前代码的项目文档，减少重复入口、过时描述和临时生成物。清理后，读者应能从一个索引找到当前 Harness 架构、求职材料、面试手册、源码学习指南和作品展示说明。

## 最终目录

```text
docs/
├── README.md
├── architecture/
│   └── agent-harness.md
└── resume/
    ├── README.md
    ├── 多模式深度研究Agent简历项目材料.md
    ├── Agent Harness面试手册.md
    ├── Agent Harness源码学习指南.md
    └── 作品展示制作指南.md
```

## 删除与合并

- 删除未被项目引用的 `docs/harness-source-map.html`。
- 删除已经完成且被当前实现取代的 `docs/superpowers/plans` 与 `docs/superpowers/specs`。仍有效的架构决定先合并进 `docs/architecture/agent-harness.md`。
- 将 `Harness面试速记手册.md`、`多模式深度研究Agent五个核心面试问题.md` 和 `多模式深度研究Agent面试与学习资料/00-07` 合并为两份文档：
  - `Agent Harness面试手册.md`：项目表达、核心问题、高频问答和边界。
  - `Agent Harness源码学习指南.md`：架构、目录、调用链、长期记忆和自测路径。
- 保留并更新简历项目材料和作品展示指南。

## 当前事实边界

整理后的文档以当前代码和离线测试为准，统一描述：

- LangGraph Session Graph 管理 conversation lifecycle、memory lifecycle 和 strategy routing。
- Workflow、Plan-and-Execute、Multi-Agent 是三个 orchestration strategy，共享同一个 Agent Harness Runtime。
- Shared Agent Loop 为 `prepare_context → ModelGateway → tool_calls/finish → ToolGateway → observe → execution policy`。
- 每次生产 ModelGateway 调用必须包含 system instruction、original task 和 current constraints。
- `write_todos` 是循环内状态工具；`search_web` 与 `fetch_page` 是必须经过 ToolGateway 的外部工具。
- 无依赖外部工具有界并行；依赖搜索授权的抓取等待前置结果；ToolMessage 按原调用顺序闭合。
- Transport retry 属于 ModelGateway/ToolGateway，semantic repair 属于 Agent Loop，recovery replay 属于 Checkpoint/Worker/Ledger。
- 所有受控循环退出产生 AgentOutcome；Checkpoint 恢复后保持上下文、工具配对、Gateway 和 Outcome 不变量。
- 当前离线测试基线为 464 passed、1 deselected；真实 Provider 和外部服务不写成已完成验收。

## 索引与兼容

- 更新根 `README.md` 与 `docs/README.md`，只链接最终存在的文档。
- 更新 Markdown 内部链接，删除对旧文件名和 `docs/superpowers` 的引用。
- 不修改运行代码、前端代码、配置和数据文件。
- 被 Git 跟踪的旧文档可从历史恢复；未跟踪的 HTML 生成物删除后不保留副本。

## 验收

1. `docs` 最终只包含设计中的文件。
2. Markdown 相对链接全部指向存在文件。
3. 文档中的源码路径全部存在，或明确标注为历史/演进方向。
4. 不再出现已过时的运行时描述：Topic RetryPolicy 参与当前执行、Researcher 未接入 Token Budget、工具批只能串行、Outcome 只有 stop_reason。
5. 简历材料、面试手册和源码学习指南对同一能力的“已实现/演进方向”判断一致。

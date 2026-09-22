# Agent Harness 项目文章、学习路线与面试材料设计

## 1. 目标

围绕当前 DeepResearch 项目，产出一套面向 Agent 开发与大模型应用岗位的中文内容材料。

主文章参考微信公众号文章《Agent Harness 项目，简历怎么写出深度？》的叙事方式：从复杂任务出发，依次拆解 Agent Loop、Context、Tool、稳定工程和系统评估，再压缩为简历表达。参考文章仅作为写作结构和视觉节奏样本，其中的业务场景、系统结论和配图不作为本项目事实依据。

这套材料同时实现三个目标：

1. 展示 DeepResearch Agent Harness 的完整系统设计和工程深度；
2. 给项目作者提供一条可执行的 Harness 学习、完善和验证路线；
3. 将源码、测试、Trace、架构图和项目描述组织成可用于面试的证据链。

## 2. 目标读者与成功标准

主要读者是 Agent 开发、大模型应用工程和相近岗位的面试官与候选人。

完成后的材料应满足以下标准：

- 不依赖阅读全部源码，也能理解项目解决的问题和核心架构；
- 能清楚解释 Agent Loop、Context、Tool Gateway、Checkpoint、Evidence、Memory 和 Eval 的职责边界；
- 每项关键设计都能落到当前项目中的模块、测试或明确的完善清单；
- 主文章具备参考文章的短段落、强结论、Field Note、简历句和面试追问节奏；
- 学习文档能指导作者按顺序读源码、做实验、补能力和准备面试；
- README 和简历版本可以独立阅读，不需要复制整篇文章；
- 不虚构真实运行结果、业务收益、通过率或成本改善。

## 3. 总体内容架构

### 3.1 主文章

文件：`docs/resume/Agent Harness项目深度拆解.md`

建议标题：`DeepResearch Agent Harness，简历怎么写出工程深度？`

文章使用“业务价值 → 决策难点 → 系统设计 → 验证证据 → 简历表达”的主线，按 11 个 Field Notes 组织：

1. 复杂研究任务：为什么“搜索 + 总结”不等于 DeepResearch；
2. 场景变化：为什么同一问题需要不同策略和工具路径；
3. Shared Agent Loop：如何让研究任务持续向证据收敛；
4. Context：如何围绕当前决策装配信息；
5. Tool：如何通过注册表、契约和 Gateway 治理外部能力；
6. Evidence 与 Citation：如何让结论能够回查和验收；
7. 稳定工程：transport retry、semantic repair 和 recovery replay 如何分工；
8. State、Checkpoint、Ledger 与 Memory：数据所有权如何划分；
9. 多策略编排：Workflow、Plan-and-Execute、Multi-Agent 如何共享 Harness；
10. 系统评估：如何比较任务完成、成本、接管和错误副作用；
11. 最终简历：将角色任务、核心实现和验证结果压缩为项目经历。

每个适合的章节使用以下内容单元：

- 一个可感知的问题或执行场景；
- 一句加粗的核心判断；
- 2–4 个系统设计要点；
- 与当前项目对应的源码入口或测试证据；
- “简历怎么写”“面试追问”或“怎么验证”之一；
- 必要时插入一张只回答一个问题的配图。

主文章按完整、成熟的最终系统形态组织，不使用“下一阶段”“未来计划”等标签打断叙事。设计完整性不等于声称全部实现；实现状态由独立差距文档负责说明。所有带有实测含义的数字必须来自实际命令输出或仓库中可验证的记录。

### 3.2 学习与面试路线

文件：`docs/resume/Agent Harness学习与面试路线.md`

该文档回答“如何真正学会这个 Harness，并能在面试中讲清楚”。内容按五个学习阶段组织：

1. Agent Loop：画出一次研究请求的控制流，理解继续、等待和退出；
2. Context：追踪模型输入，验证稳定信息、工作状态和证据切片的保留规则；
3. Tool：理解工具契约、参数校验、权限、预算、并发和结果配对；
4. Runtime：制造超时、重复投递、恢复和预算竞争，理解三类重试；
5. Eval：固定任务、模型与预算，比较三种策略并记录副作用。

每个阶段必须包含：

- 学习目标；
- 对应源码入口；
- 推荐阅读顺序；
- 必须亲手完成的实验；
- 完成标准；
- 常见面试问题；
- 应准备的演示或证据。

文档末尾提供一份面试证据清单，包括完整执行 Trace、两条不同策略轨迹、一次工具失败修复、一次 Checkpoint 恢复、Context 裁剪对照、评测报告和三分钟项目介绍。

### 3.3 实现差距与完善清单

文件：`docs/resume/Agent Harness实现差距与完善清单.md`

该文档将主文章中的能力逐项映射到当前源码，采用以下字段：

| 字段 | 含义 |
| --- | --- |
| 能力 | 主文章中的设计能力 |
| 当前状态 | 已实现、部分实现或尚未实现 |
| 代码证据 | 对应模块、测试或命令 |
| 缺口 | 当前行为与完整方案的差异 |
| 推荐方案 | 与现有架构一致的补齐方式 |
| 验收方法 | 可重复执行的测试或评测 |
| 优先级 | 面试前必须、重要或可选 |

差距文档是后续开发与学习清单，不承担项目宣传功能。它应明确区分架构设计、离线模拟验证、真实 Provider 联调和真实业务效果。

### 3.4 README 与简历材料

修改文件：

- `README.md`
- `docs/resume/多模式深度研究Agent简历项目材料.md`
- `docs/resume/README.md`
- `docs/README.md`

根 README 保持快速理解和运行入口的职责，新增主文章、学习路线、差距清单和面试材料链接；不复制主文章的大段正文。

简历材料面向 Agent 开发岗位，输出：

- 一段项目定位；
- 4–5 条可追问的核心实现；
- 一组只在有实际证据时填写的验证结果；
- 不同岗位侧重点建议；
- 30 秒、3 分钟和深挖版项目介绍。

两个资料索引文件负责把文章、学习路线、差距清单、源码指南和面试手册组织成清晰的阅读顺序。

## 4. 视觉设计

配图采用 Engineering Field Notes 视觉体系：暖纸色背景、墨黑主体、铜橙关键边界、青绿已验证状态、红棕失败或需接管状态。中文标题与英文模块名并用。

图形语义保持一致：

- 实线箭头表示确定的数据流或控制流；
- 虚线箭头表示恢复、召回、异步或可选关系；
- 铜橙表示模型决策、Gateway 或关键约束边界；
- 青绿表示 Evidence、通过验证或成功状态；
- 红棕表示失败、UNKNOWN 或人工接管状态。

正式配图以可维护的项目内 SVG 实现，不使用生成式位图绘制系统架构。现有真实工作台截图继续作为产品主图。

新增或重制以下图片：

1. `docs/assets/harness-five-core-problems.svg`：Loop、Context、Tool、Runtime、Eval 五个核心问题；
2. `docs/assets/harness-research-loop.svg`：一次研究请求从输入到 AgentOutcome 的执行闭环；
3. `docs/assets/harness-context-assembly.svg`：稳定层、任务层、工作层与证据层的装配和裁剪；
4. `docs/assets/harness-failure-ownership.svg`：三类重试及其所有者；
5. `docs/assets/harness-data-ownership.svg`：State、Evidence、Ledger、Memory 的数据边界；
6. `docs/assets/harness-learning-interview-roadmap.svg`：读懂、修改、验证、表达的学习与面试路径。

每张图只回答一个核心问题，并在文章中配一行说明“这张图证明或解释什么”。SVG 需要在 GitHub Markdown 中可读，避免依赖外部字体、脚本或远程资源。

## 5. 事实与表达边界

内容采用以下规则：

1. 架构设计可以完整描述最佳方案；
2. “当前已实现”必须能由源码、测试或可重复命令验证；
3. “已验证”“通过率”“成本下降”“真实效果”等结果只能使用实际数据；
4. 离线模拟、Showcase 固定数据、真实 Provider 和真实业务结果必须分开表述；
5. 主文章保持连贯，不在正文中逐项插入状态标签；
6. 差距文档必须完整记录主文章与当前实现之间的差异；
7. 不把参考文章中的跨境电商场景、数据或实现边界移植为本项目事实；
8. 不暴露 API Key、Cookie、访问令牌或个人敏感信息。

## 6. 源码证据范围

文章优先引用以下项目边界：

- Session Graph：`backend/src/deeptrace/harness/graph.py`
- Shared Agent Loop：`backend/src/deeptrace/harness/agent_executor.py`
- Model Gateway：`backend/src/deeptrace/harness/model_gateway.py`
- Tool 执行与配对：`backend/src/deeptrace/harness/agent_tools.py`
- Tool Gateway：`backend/src/deeptrace/tools/gateway.py`
- Context 与 Execution Policies：`backend/src/deeptrace/harness/policies/`
- Checkpoint：`backend/src/deeptrace/harness/checkpoint.py`
- Memory Lifecycle：`backend/src/deeptrace/harness/memory/lifecycle.py`
- Workflow、Plan-and-Execute、Multi-Agent：`backend/src/deeptrace/strategies/`
- Evidence、Ledger 与持久化：`backend/src/deeptrace/persistence/`
- 运行时不变量与相关测试：`backend/tests/harness/`、`backend/tests/tools/`、`backend/tests/integration/`

实现时需要重新检查这些文件及最新测试结果，不能仅依据现有文档转述。

## 7. 验证与验收

内容验收包括：

- 主文章 11 个 Field Notes 的逻辑顺序完整；
- 主文章中的关键架构结论能映射到源码或差距清单；
- 三份新增文档职责互不混淆；
- README 和资料索引链接有效；
- 简历材料与主文章事实一致；
- 所有 SVG 在 Markdown 中路径正确、文字不溢出、缩放后仍可读；
- 引用的测试数字来自本次实际执行结果；
- 全仓搜索不存在遗留占位符、错误路径和从参考文章误带入的跨境业务表述。

技术验证应至少包括：

- 运行与文档内容相关的后端确定性测试；
- 运行前端测试与构建，确认 README 中的命令仍然有效；
- 对新增 Markdown 执行链接与资源路径检查；
- 将 SVG 渲染为 PNG 进行视觉检查，确认无裁切、重叠和乱码。

## 8. 非目标

本次工作不包含：

- 为了让文章描述成立而直接补齐全部后端功能；
- 虚构线上业务数据或真实 Provider 评测结果；
- 复制参考文章正文、配图或跨境业务案例；
- 对项目进行与内容产出无关的大规模重构；
- 将系统图改为不可维护的生成式位图。

## 9. 工作区保护

当前工作树存在用户的未提交修改。实施时必须：

- 只修改本规格列出的文档和图片文件；
- 在修改已有文件前检查差异并保留用户内容；
- 不重置、覆盖或清理其他未提交文件；
- 测试与格式化命令不得对无关文件执行批量重写。

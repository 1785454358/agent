# ResearchPilot Harness 简历与面试材料设计

## 目标

围绕项目完成后的最终形态准备求职材料。简历与面试回答以项目实现的 Agent Harness 为主线，三种研究模式、工具执行、状态、记忆、持久化和可靠性都放在同一套运行治理设计中讲解。

本文档不描述当前开发进度，不保留旧版 Basic、Deep 命名，也不把重构过程作为简历主线。

## 事实口径

- 项目标题固定为“多模式深度研究 Agent”，不使用 ResearchPilot 名称。
- 项目性质使用个人项目、独立开发。
- 三种研究模式使用 Workflow、Plan-and-Execute、Multi-Agent。用户与 API 通过 `ResearchMode` 选择模式，`StrategyRegistry` 解析对应的 `ResearchStrategyGraph`。
- Agent Harness 是项目自行设计的运行治理层，不称为 LangGraph 官方架构、官方规范或官方类型。
- LangGraph 是状态编排与持久化运行时。项目用顶层 `StateGraph` 编排公共生命周期，用策略子图实现三种研究模式。面试讲解不使用 `HarnessGraph` 或“Agent Harness 主图”作为架构概念。
- 所有 Agent 编排、条件路由、并发派发、重规划、恢复边界统一使用 LangGraph。
- 普通回答是默认输出。只有用户明确要求报告时才进入 Report Graph。
- 短期上下文按 thread 保存，采用滑动窗口与结构化动态压缩。它作为状态与记忆设计讲解，不把“连续追问”或“多轮对话”列为项目卖点。
- 长期记忆覆盖存储时机、内容选择、命名空间、召回、版本更新和遗忘策略。
- MySQL 保存业务数据、Evidence、长期记忆、工具执行账本和 LangGraph Checkpoint。
- LangGraph Checkpoint 通过社区包 `langgraph-checkpoint-mysql[asyncmy]` 接入。面试中不称为官方内置 MySQL 支持。
- Redis Streams 用于任务投递、唤醒和取消通知，不作为权威状态源。
- Tool Gateway 只注册 `search_web`、`fetch_page`、`search_memory` 三个原子工具。
- `research_topic` 是 LangGraph 子图，不包装成复合工具。
- 不编造尚未得到的线上用户数、准确率、成本降幅或吞吐数据。
- 测试数量不作为简历长期卖点。面试时可按最终测试结果说明验证范围。

## 简历结构

沿用用户旧版简历的紧凑格式。

1. 一行项目标题、职责和时间。
2. 一行技术栈。
3. 两行以内项目描述。
4. 一组可自由选取的项目要点。

先提供适合直接投递的五条核心版本，再提供可按岗位和版面替换的扩展要点。项目要点按下面主题组织。

1. Agent Harness
2. 三种研究模式与策略子图
3. Tool Gateway 与 Evidence
4. 记忆与上下文
5. 持久化与可靠性
6. 输出路由
7. 可观测性与评测

Memory 相关内容至少拆成短期记忆、动态压缩、长期记忆生命周期三个可独立选择的要点。每条说明做了什么、解决了什么问题以及关键机制。避免连续罗列名词，也避免写无法验证的效果数字。

## 面试讲解结构

### 第一层 项目介绍

准备九十秒和三分钟两个版本。两种版本都按同一条叙事链展开。

1. 项目处理需要检索、阅读原文与交叉验证的复杂开放问题。
2. 三种研究模式需要共享一致的运行协议，因此项目实现统一 Agent Harness。
3. Harness 规定状态、依赖、策略、模型、工具、证据、记忆、预算、恢复和观测怎样协作。
4. LangGraph 承担图编排、状态流转、子图、Checkpoint 和恢复边界。
5. Workflow、Plan-and-Execute 与 Multi-Agent 通过统一输入输出契约接入，内部状态各自隔离。
6. Tool Gateway、Evidence Store、Memory、Checkpointer 和响应图沿一次执行生命周期串联起来。
7. 最后说明可靠性边界和关键取舍，不把项目介绍写成技术名词清单。

介绍中不得使用“项目以 LangGraph Agent Harness 为组织中心”。推荐表述为“项目基于 LangGraph 实现了一套统一 Agent Harness”。前者容易把 Agent Harness 误解成 LangGraph 的官方组件，后者能准确区分运行时与项目设计。

### 第二层 Harness 深挖

按一次请求的生命周期讲解。

```text
Request
→ 顶层 StateGraph 接收并规范化请求
→ 意图判断与研究模式路由
→ Context and Memory Recall
→ Research Strategy Subgraph
→ Tool Gateway and Evidence Store
→ Response Graph
→ Memory Consolidation
→ Checkpoint and Events
```

每个环节都要说明输入输出契约、状态归属、失败处理和恢复方式。

### 第三层 专题追问

准备以下专题。

- Harness 与普通 Agent 封装的区别
- Harness 与 LangGraph 分别负责什么
- 为什么所有循环和路由都使用 LangGraph
- 三种研究策略子图如何共享能力又保持状态隔离
- Tool Gateway 的中间件顺序
- Evidence 为什么只在 State 中保存引用
- 滑动窗口与动态压缩如何配合
- 长期记忆的六个生命周期问题
- Checkpoint、幂等账本与 at-least-once 投递
- MySQL Checkpointer 的选型、限制和验证方式
- Redis 与 MySQL 的职责边界
- 如何比较三种研究模式的质量、成本和时延

## 模拟面试方式

用户扮演面试官，助手扮演候选人。

每一轮只回答当前问题，先给可直接说出口的回答。回答后提供两项简短复盘。

- 这段回答向面试官证明了什么。
- 面试官最可能继续追问什么。

用户可以针对回答要求更短、指出漏洞或切换到压力面。助手不一次性倾倒所有题库。

第一轮从“请你介绍一下这个多模式深度研究 Agent”开始，使用三分钟版本。

## 交付文件

- 重写 `docs/resume/researchpilot-project-experience.md`
- 新建 `docs/resume/researchpilot-harness-interview-guide.md`

前者提供可以复制到简历中的项目经历。后者保存项目讲解、Harness 深挖提纲和模拟面试复盘，不混入简历正文。

## 验收标准

- 项目标题使用“多模式深度研究 Agent”。
- 简历以 Harness 为第一要点。
- 简历同时提供核心版本和可选要点库，Memory 至少有三个独立候选要点。
- 不再出现 Basic 和 Deep 作为最终模式名称。
- 不把“连续追问”或“多轮对话”作为项目介绍和专题标题。
- 全文不使用 Research Profile、Profile Registry、Profile 子图等旧术语。
- 全文不把 `HarnessGraph`、“Agent Harness 主图”或“LangGraph Agent Harness”当成正式架构概念。
- 项目介绍以项目实现的 Harness 为叙事主线，并准确说明 LangGraph 是底层状态编排运行时。
- 默认回答和显式报告的输出策略一致。
- MySQL 的表述准确区分社区 Checkpointer 与官方内置能力。
- 短期记忆和长期记忆边界清楚。
- 每条简历内容都能在面试指南中展开说明。
- 没有未经验证的量化结论。

# ResearchPilot 项目简历材料

## 可直接放入简历的版本

**ResearchPilot｜多模式深度研究 Agent｜个人项目**

面向复杂开放问题构建自主研究 Agent，覆盖任务规划、网页检索、原文获取、动态补查和带引用报告生成。  
独立实现 Workflow、Plan-and-Execute 和 Supervisor Multi-Agent 三种研究模式，可按研究深度和成本要求选择执行策略。

**技术栈**　Python、LangGraph、LangChain、FastAPI、Pydantic、OpenAI Function Calling、Tavily、Playwright、BGE-M3、SSE、Pytest

- 设计三层研究架构，Basic 采用固定 Workflow 完成一次规划、并行检索和报告生成，Deep 采用 Plan-and-Execute 与 ReAct 执行，Multi-Agent 通过 LangGraph 编排 Supervisor 和多个 Researcher。
- 实现面向复杂问题的任务拆解和持续执行，由 Planner 生成研究目标、完成条件与任务依赖，Executor 根据工具反馈推进任务，Replanner 针对未完成内容动态调整后续计划。
- 基于 Function Calling 封装网页搜索、正文抓取和历史资料检索工具，使用 BGE-M3 筛选相关原文，结合可选长期记忆生成正文顺序引用与文末参考内容。
- 构建 Supervisor Multi-Agent 协作流程，限并发执行多个隔离的 ReAct Researcher，根据执行结果识别未解决叶子缺口，并生成与具体缺口对齐的定向补查任务。
- 通过异步并行、本地语义筛选、上下文长度限制、请求缓存、单飞复用和终止短路减少重复网络请求与无效模型调用，使用 FastAPI、SSE 展示运行过程，完成 210 项自动化测试。

## 一分钟面试介绍

ResearchPilot 是我独立开发的深度研究 Agent。我做这个项目时，主要想解决开放问题需要多轮检索、资料核对和报告汇总的问题，同时比较不同 Agent 架构在速度、研究深度和成本上的差异。

项目保留了三种模式。Basic 是固定 Workflow，适合快速完成一次规划和并行检索。Deep 使用 Plan-and-Execute，Planner 拆任务，ReAct Executor 根据工具结果执行，出现缺口后由 Replanner 调整计划。Multi-Agent 使用 LangGraph 编排 Supervisor 和多个 Researcher，让不同研究方向并行推进，再根据未解决缺口补充研究。

我在开发中重点处理了任务和搜索行为对不齐的问题。现在每个补查任务只对应一个具体缺口，Researcher 的工具调用也要关联任务检查项，避免重新进行宽泛搜索。Writer 直接使用网页原文或 BGE-M3 筛选出的相关片段生成带引用报告。下一步我准备建立固定评测集，对三种模式的事实正确性、来源覆盖、耗时和 Token 消耗做可复现比较。

## 面试追问准备

### 为什么同时保留 Workflow、Plan-and-Execute 和 Multi-Agent

三种模式对应不同任务成本。固定 Workflow 路径短、调用次数少，适合边界清晰的问题。Plan-and-Execute 能根据执行反馈调整计划，适合需要多轮查证的复杂问题。Multi-Agent 可以并行覆盖互相独立的研究方向，适合范围更广的主题。保留三种模式也方便在统一输入和 Writer 下进行效果与成本比较。

### Supervisor 和普通 Planner 有什么区别

Planner 主要在任务开始时生成执行计划。Supervisor 除了初始分工，还会持续读取各 Researcher 的完成状态和具体缺口，决定是否派发补查任务或结束研究。项目中的 Supervisor 管理一张持久任务表，补查任务只追加，不会覆盖已经完成的任务。

### 如何避免 Researcher 重复搜索或偏离任务

初始任务允许围绕指定检查项建立资料基础，补查任务只能面向一个具体叶子缺口。每次研究工具调用都要关联 Assignment 中的检查项，错误目标会在网络请求前被拒绝。同次运行还会复用相同查询和 URL 的结果，减少重复抓取。

### 如何控制报告幻觉和引用错误

搜索摘要只用于发现候选页面，不能直接作为报告依据。Researcher 必须实际读取网页，Writer 只接收成功抓取的正文或 BGE-M3 筛选出的原文片段。正文引用按照来源首次出现顺序编号，URL 统一放在文末，任务摘要只用于 Supervisor 协调，不作为事实输入。

### 为什么目前没有写 Token 降幅，下一步怎样评测

现有运行记录来自不同阶段的代码和模型配置，直接比较容易混入口径差异。下一步会建立固定问题集，为三种模式设置相同模型、搜索服务和运行参数，多次记录事实正确性、来源覆盖率、完整度、墙钟耗时与 Token。拿到稳定结果后，再把简历中的成本控制改成带样本规模和质量约束的量化结论。

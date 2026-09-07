# Deep Research Implementation Plan

**Goal:** 实现已确认的 Plan-and-Execute / ReAct 深度研究模式。
**Architecture:** 独立 deep 包拥有计划、工具循环、工作状态和重规划，复用现有 Writer、抓取器、BGE 与页面记忆。API/CLI 在组装边界选择模式。
**Tech Stack:** Python、asyncio、Pydantic、LangChain 原生 tool_calls、pytest。
**Spec:** ../specs/2026-09-05-deep-research-design.md

用户已要求直接实施，在当前任务内完成；保留用户未提交的前端改动。

- [x] 1. 新增 tests/deep：脚本 AIMessage 的真实工具调用、缺口触发重规划、依赖校验、次数上限与取消、记忆时效与语义排序，先验证失败再实现。
- [x] 2. 新增 deep/models.py（任务/计划/反馈验证）、runtime.py（工具计数、耗时与用量）、tools.py（搜索/阅读/记忆工具）、agent.py（规划与执行），复用 Writer。不设总时间、Token、费用预算。
- [x] 3. 新增 API 模式路由与启动失败用例；service.py 组装 deep，Settings 增加独立次数限制，UsageBreakdown 加 executor/replanner。CLI 与现有页面加模式入口。
- [x] 4. 运行 pytest 和 compileall。检查原有前端 diff，确认用户变更保留。审查循环上限、工具消息配对、失败时降级、输入校验、上下文增长与用量归属。
- [x] 5. 更新 README、docs 索引与 .env.example。做少量工具调用的真实 Provider/页面冒烟，记录实测结果与限制，不夸大性能或研究质量。
- [ ] 6. 用户停止当前 8000 端口的旧后端，再启动新版服务。自动重启命令被执行策略拦截；尚未把新版后端加载到该端口。

## 接口与测试示例

```python
agent = DeepResearchAgent(model=model, writer=writer, tools=toolbox, settings=settings)
result = await agent.arun("研究问题")
assert result.role_usage.executor.total_tokens > 0
assert any(e.event_type == "replanning.completed" for e in result.events)
assert result.events[-1].details["total_tokens"] == result.provider_usage.total_tokens
```

Toolbox 暴露 async execute(name, args) -> dict、documents、contexts、queries。
Runtime 暴露 async invoke(model, messages, role)、remaining_tools()、claim_tool()、emit。
计划由 Pydantic 校验，工具 dispatch 只允许显式白名单，网页是非可信资料。

# LangSmith 迁移验证

日期：2026-11-09。本记录验证平台接入，不作为整体质量或效率提升结论。

## 迁移结果

- 通过本地 `.env` 完成账户连接；密钥未写入示例、源码或文档，`.env` 被 Git 忽略。
- 自建 Trace 存储/模型/查询接口/面板、旧评测执行器/评分器/容器及其专属测试已删除。
- 直接依赖 LangSmith 0.11.2；原生 LangGraph / LangChain 调用树及 SDK 应用、工具 spans 已接通。
- 30 道现有题迁移为原生 JSONL，上传到 [deeptrace-research-v1](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/datasets/4533dc24-94a4-4a39-90ef-5a35959cb58a)。参考答案保留来源，目标不读取参考输出。

## 真实云端冒烟

对相同示例 `07ee3417-880d-5420-ac0a-06be2c8b4270` 各执行一次。通过 SDK 回读云端 run 和 feedback 核验，三个实验均成功上传调用树、Token 和四项反馈。

| 策略与实验 | Runtime 结果 | 完成率 | 证据充分 | 工具成功率 | 答案评分 | 目标模型调用 / Token |
| --- | --- | --- | --- | --- | --- | --- |
| [Workflow](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/64e2bba8-90d3-407c-9cd2-021a96d5ab22) | completed | 1 | 1 | 1 | 1 | 7 / 47,690 |
| [Plan-and-Execute](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/9002ccd8-05bf-486a-811a-ae91c8bb1078) | partial / planning_limit | 0 | 0 | 1 | 0.9 | 17 / 76,897 |
| [Multi-Agent](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/a4d6ef91-1c82-49e4-b3d4-6341196b85f3) | partial / planning_limit | 0 | 0 | 0.9688 | 1 | 13 / 66,629 |

调用数及 Token 来自实验目标项目中的 LLM spans；独立裁判消耗不计入目标研究预算。三个实验分别记录 83、190、162 个 span；工具调用成功率以评测适配器的 Gateway 返回计数为准，不能把 wrapper 和 provider attempt 的 span 数相加作为分母。

两项 partial 已在云端反馈中保留，说明研究完成条件未满足。答案裁判高分与证据充分性不是同一指标。本轮没有针对这些结果调整 Prompt 或检索策略，也未执行 30 题完整批量评测。题目参考来自冻结文档，目标使用实时联网检索；样本和服务商均有局限，裁判仍需人工校准。

## 工程验证

- 后端确定性测试：**1443 passed，1 deselected**。
- 前端：**54 passed**，lint、Production 与 Showcase 构建通过。
- 覆盖 SDK 原生评测、异常 Trace、父子关联、工具失败与重试、参数边界、重复同步、trial 身份与取消清理、SDK 队列刷新、目标失败退出、迁移升降级。
- 存在 LangSmith SDK 的弃用/Beta 提示，以及已有测试中的 SQLite 线程清理警告；测试均通过。
- 本轮没有执行 Docker 镜像构建或远程 GitHub Actions；工作流配置与迁移在本地验证。

运行命令、数据含义与简历表述见 [LangSmith 使用说明](../../architecture/langsmith.md)。

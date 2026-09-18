# DeepResearch 文档

这里保存面向当前代码的架构和求职资料。历史实施计划与已被实现取代的规格不再保留在工作树中，提交历史仍可追溯。

## 架构

- [Agent Harness 当前架构](architecture/agent-harness.md)：Session Graph、三种策略、Shared Agent Loop、Gateway、重试、预算、记忆、Checkpoint 和 Outcome 的统一说明。
- [后端配置与运行](../backend/README.md)：环境变量、API、本地与分布式运行方式。
- [项目入口](../README.md)：项目定位、快速开始和验证命令。

## 求职与学习

- [资料索引](resume/README.md)
- [简历项目材料](resume/多模式深度研究Agent简历项目材料.md)
- [Agent Harness 面试手册](resume/Agent%20Harness面试手册.md)
- [Agent Harness 源码学习指南](resume/Agent%20Harness源码学习指南.md)
- [作品展示制作指南](resume/作品展示制作指南.md)

文档以当前源码和离线测试为事实边界。记录基线为 `464 passed, 1 deselected`；真实 Provider 和外部服务需要单独凭据与环境，不视为本次离线验收的一部分。

文档和示例不得包含真实 API Key、Cookie、访问令牌或其他凭据。

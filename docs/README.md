# DeepResearch 文档

这里提供项目使用、架构设计、部署和真实研究案例的阅读入口。

## 使用与展示

- [项目首页](../README.md)：使用场景、快速体验、技术亮点与源码入口。
- [Docker 打包与运行](deployment/docker.md)：镜像构建、单机运行、分布式 Compose 和镜像验收。
- [真实研究案例](showcase/case-asyncio.md)：Python 官方文档研究的原始回答、配置、来源与完整指标。
- [设计参考与演进方向](showcase/mature-projects.md)：同类成熟项目的展示和工程实践。
- [工作台截图](assets/deepresearch-workbench.png)：使用固定示例数据的交互演示界面，可通过首页的快速体验启动。

## 架构与源码

- [Agent Harness 架构](architecture/agent-harness.md)：Session Graph、三种策略、共享 Agent Loop、Gateway、预算和恢复机制。
- [记忆模块](architecture/memory.md)：记忆生命周期、版本更新、召回、证据准入与存储设计。
- [后端使用说明](../backend/README.md)：环境变量、API、本地与分布式运行方式。

建议先体验工作台，再阅读真实案例，最后结合架构文档和源码了解实现。测试与构建命令见[项目首页](../README.md#测试与工程验证)。

# DeepResearch 文档

这里提供项目使用、架构设计、研究案例和实验记录。阅读入口按使用目的组织，历史实施材料单独保存在设计目录。

## 使用与展示

- [项目首页](../README.md)：使用场景、快速体验、工程能力与源码入口。
- [Docker 打包与运行](deployment/docker.md)：单机镜像、分布式 Compose 和镜像验收。
- [真实研究案例](showcase/case-asyncio.md)：官方文档研究的原始回答、运行配置与指标数据。
- [设计参考与演进方向](showcase/mature-projects.md)：同类成熟项目的展示和工程实践。

## 架构

- [Agent Harness 当前架构](architecture/agent-harness.md)：Session Graph、三种策略、Shared Agent Loop、Gateway、重试、预算、记忆、Checkpoint 和 Outcome 的统一说明。
- [最小评测方案](evaluation/agent-benchmark-plan.md)：离线模拟环境与多策略 A/B 的评测设计。
- [真实校准与评测操作](evaluation/experiment-records.md)：预算、原生 Ragas、失败留样和严格续跑。
- [评测系统续建实测](evaluation/benchmark-continuation-20261002.md)：回答长度、配对统计和 24 个受控记忆变体。
- [评测数据治理](evaluation/governed-assets-20261002.md)：30 道真实资料题、12/18 切分、47 处引用及 5 道公开任务导入；与真实实测结果明确区分。
- [离线 CI 与长文送达诊断](evaluation/ci-long-context-20261002.md)：隔离评分 CI、指标输入限额修复与 6 个开发集脚本诊断；打包/远端 CI 尚待验证。
- [按问题选段与送达复测](evaluation/query-excerpts-20261002.md)：共享选段器、来源位置与预算观测；同组诊断完整片段可见数从 0 到 2，不代表质量提升。
- [证据闭环实现与离线验证](evaluation/evidence-loop-validation-20261002.md)：三模式原文支持、缺口补查、Answer/Report 与事实记忆准入；913 项离线回归通过，真实质量尚未重测。
- [证据闭环真实 API 校准](evaluation/evidence-loop-real-calibration-20261002.md)：12 个真实模型 Answer、两条高资源诊断与联网冒烟，保留 partial/failed；最小异常分类修复与 927 项离线回归。
- [共享规划与补查目标复测](evaluation/planning-gap-validation-20261002.md)：执行约束与事实要点分区、混合补查目标校验；953 项离线回归及登记的三模式真实 API 复测。
- [待办进度更新与同预算复测](evaluation/todo-progress-validation-20261002.md)：仅改共享提示契约，保留证据/恢复门禁；三模式真实校准及调用效率留样。
- [最小覆盖规划与同预算复测](evaluation/minimal-planning-validation-20261003.md)：只改共享初始规划提示，保护独立子问题；三模式真实结果与评分覆盖留样。
- [结构边界与答案要点选段复测](evaluation/structure-selection-validation-20261003.md)：共享结构候选与固定要点取材；记录真实效果及词项排序/引用限制。
- [读证据交接与宿主引用解析复测](evaluation/evidence-delivery-validation-20261003.md)：三模式共享v3证据管道、读取锚点与当次可见短引用；离线验证及登记真实结果。
- [证据优先简化与联网恢复验证](evaluation/evidence-first-validation-20261004.md)：实际URL、完整阅读组、原文直接评估及已读收尾；同预算真实结果和未达标项单列。
- [后端配置与运行](../backend/README.md)：环境变量、API、本地与分布式运行方式。
- [项目入口](../README.md)：项目定位、快速开始和验证命令。

## 求职与学习

- [资料索引](resume/README.md)
- [Agent Harness 项目深度拆解](resume/Agent%20Harness项目深度拆解.md)：仿工程 Field Notes 的完整项目文章，从复杂任务、系统设计到简历表达。
- [Agent Harness 学习与面试路线](resume/Agent%20Harness学习与面试路线.md)：按 Loop、Context、Tool、Runtime、Eval 学习并准备可验证证据。
- [Agent Harness 实现差距与完善清单](resume/Agent%20Harness实现差距与完善清单.md)：对齐完整方案、当前源码、缺口和验收方法。
- [简历项目材料](resume/多模式深度研究Agent简历项目材料.md)
- [Agent Harness 面试手册](resume/Agent%20Harness面试手册.md)
- [开源项目对比面试问答](resume/开源项目对比面试问答.md)
- [DeepResearch 核心差异面试与学习手册](resume/DeepResearch核心差异面试与学习手册.md)：围绕“与成熟项目有什么不同”训练 30 秒、90 秒、深挖和压力追问回答。
- [Agent Harness 源码学习指南](resume/Agent%20Harness源码学习指南.md)
- [作品展示制作指南](resume/作品展示制作指南.md)

文档以源码、测试与实验记录为依据。2026-10-04 本地确定性测试基线为 `1213 passed, 2 deselected`；真实模型案例与离线测试分别记录。实验记录中的 `tmp/` 路径表示本地留样，公开案例数据另见上方展示入口。

文档和示例不得包含真实 API Key、Cookie、访问令牌或其他凭据。

# 动态模式路由与三策略实测（2026-11-18）

## 已实现

新研究默认自动分析任务并进入三个独立策略之一。判断执行依赖与实质独立方向，不按问题长度或模式名称关键词简单分流：

1. 后续动作依赖前一步结果：Plan-and-Execute。
2. 无此类依赖，但有多个可独立取材、最终汇总的方向：Multi-Agent。
3. 其余有限查询、文档解释、单方向任务：Workflow。

一次路由模型调用计入同一运行的模型次数、输入预算和截止时间；不增加原有额度。显式指定模式跳过分类。分类结果无效或普通模型请求失败时回退 Workflow；取消和预算存储失败向上传播。路由决定写入 checkpoint 和持久化事件，恢复同一运行不会重新分类。新 auto 会话后续请求仍可根据新问题重新选择。

`auto` 与三种可执行 ResearchMode 分开建模，避免把 auto 注入工具预算或运行策略注册。前端默认 auto，显示实际策略与简短原因，保留三个手动选项。API 的 mode 表示请求选择，selected_mode/routing_reason 从持久化路由事件投影；不增加 SQL 列。Local JSON 重载、SQL/Worker 事件路径和旧显式模式均通过验证。

生产默认 `DEEPTRACE_RESEARCH_ORCHESTRATOR=strategies`，装配现有三个独立子图；legacy 是兼容别名，controller 保留显式对照。旧中断运行应保持原 orchestrator 恢复；本轮没有把旧 checkpoint 自动迁移到新编排。

## 同题三模式真实运行

题目：依据 Python 官方文档，对比 asyncio.gather 与 TaskGroup 在异常传播、其他子任务取消和适用场景上的区别，用表格总结并明确 Python 版本条件。

模型 qwen3.8-max-0902，真实 Tavily 和网页抓取；Local、lexical、独立运行目录和线程。同题各一次、按顺序执行，未冻结搜索结果，不是统计显著性实验。每次上限仍为20次模型调用、100000输入Token、600秒研究窗口。

三次显式模式运行使用原 legacy 配置，即现 strategies 的兼容别名，在默认切换及事件补齐前开始；其调用数不包含自动分类调用，不能作为路由开销的直接对照。

| 模式 | 状态 | 秒 | 回答字符 | 来源链接 | 模型调用 | 总Token |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| workflow | completed | 136.39 | 2556 | 5 | 6 | 40675 |
| plan_execute | completed | 127.26 | 2451 | 5 | 6 | 40562 |
| multi_agent | completed | 162.06 | 2675 | 3 | 10 | 57457 |

三次均有回答和引用。Multi-Agent 本题进行了额外调研/核验，耗时与用量更高，不能因为用了多个研究员就声称质量更好。Plan-and-Execute 本次较快，也不能据一次运行推出普遍优势。来源链接多为同一 Python 官方文档的不同语言和版本，并非相互独立的事实来源。

人工复核仍发现输出质量问题：Plan-and-Execute 从“3.7文档中已经出现”推成“最低版本3.7”，这个推断缺少依据；部分回答混淆 TaskGroup 内部唤醒取消与外部取消，或把取消描述为回退；代码片段仍可能含占位协程。没有以 completed 冒充逐句事实正确，也没有改写原始答案。本轮没有完成独立模型评分或跨领域成功率评测。

同题原始工件：`.local-artifacts/strategy-comparison-fd7626ec`；两个旧统一内核入口的先行补测：`.local-artifacts/mode-comparison-3376aff9`。对用户的导出仅为回答正文，位于 `output/三模式回答/`；此前请求的单独回答为 `output/回答结果.md`。

## 自动路由生产路径实测

| 输入特点 | 实际模式 | 结果 | 秒 | 回答字符 | 来源链接 |
| --- | --- | --- | ---: | ---: | ---: |
| 有限的 Python API 文档比较 | workflow | completed | 104.25 | 1564 | 1 |
| 先诊断、再据此修复并验证 | plan_execute | partial / max_replans_reached | 260.92 | 2555 | 1 |
| Python / Java / Go 三方向独立调查 | multi_agent | partial / max_follow_ups_reached | 510.02 | 3890 | 7 |

第一个通过真实 Chromium/HTTP API 操作，后两者通过真实 FastAPI 生命周期、生产 Local Runtime 和真实外部服务执行，未替换模型、搜索或抓取。第二项18次调用、75310总Token；第三项16次调用、108009总Token（总Token包含输出，不等于100000输入准入预算），最后的回答审查因输入预算被拒绝，保留带引用的部分草稿。

这些结果验证了三条路由可到达及有界退出，不能称为三类复杂任务全部成功。三方向任务首次被错误选为 Workflow：分类理由识别了独立方向，但“范围明确优先”的规则覆盖了它。随后增加失败回归，删除冗余 bounded_task 标志，改为依赖优先、独立方向其次，重跑命中 Multi-Agent。失败运行 `.local-artifacts/auto-routing-353b65d7` 保留；未改写成成功。

最终两特征分类协议另用真实模型独立验证三道类型题，三次均为 automatic、各一次模型调用并命中预期模式；这是分类器验证，不是额外三次完整研究。工件 `.local-artifacts/routing-profiles-bbb38e31` 保存原始模型回复和摘要。上表 Workflow/Plan-and-Execute 完整运行发生在规则优先级修复前，均已正确命中；最终协议由分类器三题及修复后的 Multi-Agent 完整运行验证。

自动 Workflow 工件 `.local-artifacts/auto-demo-20261118`；依赖任务 `.local-artifacts/auto-routing-a832fd73`；修复后三方向任务 `.local-artifacts/auto-routing-f2d430a9`。详情 API 只返回最近200条事件，验收从原始持久化记录核对早期路由事件，避免把事件截断误判成没有路由。

## 回归与页面检查

- 后端完整确定性测试：1773 passed，1 deselected，33个既有 LangSmith SDK/测试警告；126.75秒。
- 前端：59项测试、lint、TypeScript与生产构建通过。
- Compose 示例配置解析通过；本轮没有构建或运行 Docker 镜像。
- 回归覆盖自动默认值、三类选择、手动覆盖、格式/请求失败回退、取消、预算存储失败、共享预算扣费、checkpoint 恢复、Local/SQL 事件重载、旧模式兼容和三策略实际阶段事件。
- 浏览器检查默认自动选项、真实选中模式/原因及服务重启后的历史显示通过；未捕获JavaScript异常为0。
- 原回答正文导出与原文件 SHA-256 相同，没有加入指标、日志、截图或录屏。

代码与工件在本地，本轮没有推送GitHub或发布公网服务。

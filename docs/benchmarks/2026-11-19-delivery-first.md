# 减法实施与实测记录

2026-11-19。当前行为见[架构说明](../architecture/delivery-first-runtime.md)，实施依据见[已授权方案](../architecture/2026-11-19-delivery-first-research.md)。

## 实测方法

使用真实 `deepseek-v4.1-flash` 模型和原有 `benchmark_frozen_efficiency.py`，通过 Harness、ApplicationService、实际阅读工具、EvidenceStore 和检查点运行。搜索与抓取采用固定官方原文，**不是本轮重新联网搜索**。没有向模型提供金标准答案。

前后来源 URL 与正文 SHA-256 一致，模型相同；旧结果来自本地既有运行，新结果各采样一次，不能当独立准确率或稳定延迟基准。HTTP 的 Workflow 使用最后一次长度复核基线，另两个模式使用此前章节补全基线；它们不是同一批旧运行，不能混成一次统一旧实验。

## 耗时与模型成本

调用包括规划、选材、写作与修订的真实 provider attempts；token 来自提供方 usage，五次新运行的 usage 都完整。耗时单位秒，输入 token 不含输出 token。

| 题目 / 模式 | 模型调用：旧→新 | 输入 token：旧→新 | 新输出 token | 耗时：旧→新 | 新报告 |
|---|---:|---:|---:|---:|---|
| HTTP / Workflow | 6→3 | 31,105→12,733 | 4,339 | 48.63→27.47 | [正文](2026-11-19-delivery-first/answers/http-workflow.md) |
| HTTP / Plan-and-Execute | 5→3 | 24,175→18,057 | 5,309 | 43.31→33.77 | [正文](2026-11-19-delivery-first/answers/http-plan-execute.md) |
| HTTP / Multi-Agent | 4→3 | 19,041→16,924 | 4,490 | 42.82→28.48 | [正文](2026-11-19-delivery-first/answers/http-multi-agent.md) |
| Python 3.11 / Plan-and-Execute | 9→3 | 24,278→11,915 | 4,687 | 49.08→26.19 | [正文](2026-11-19-delivery-first/answers/python-plan-execute.md) |
| 跨语言 / Multi-Agent | 10→8 | 37,794→14,798 | 4,232 | 46.17→25.84 | [正文](2026-11-19-delivery-first/answers/cross-language-multi-agent.md) |

五次新运行都交付非空、有来源引用的报告，状态为 `completed`；新研究没有 coverage verdict，不能据此声称所有事实核实通过。HTTP 三种模式没有 evaluator/replanner 调用；跨语言仍有选材调用，因此并非所有问题固定三次模型请求。自动路由开启时还会有一次计费分类调用；本表按手动指定模式比较。

精确 usage、前后状态、来源正文 hash 和引用编号到 URL 的对应关系见 [comparison.json](2026-11-19-delivery-first/comparison.json)。正文为原始回答直接导出，没有人工修成金标准。

## 内容检查与剩余问题

- HTTP：三份新报告均给出 GET/POST 分支、Retry-After 两种格式、30 秒/最多三次尝试的代码与限制；POST 未获去重且不能证明未生效时不直接重发，发送绑定剩余预算，最后一次失败不额外等待。没有复现旧回答“业务接受重复风险即可放行 POST”的问题。仍应逐条复核 RFC 措辞与实现细节，不能仅凭状态判通过。
- Python：报告包含 `gather` 默认异常传播、不自动取消兄弟任务、`TaskGroup` 和手动取消并等待两种修复，区分 Python 3.11 与未核实的其他版本。没有再因“TaskGroup 事实未 covered”退回整份回答。
- 跨语言：报告比较了 asyncio、Java 虚拟线程和 Go，清楚标注未知。最终样本仍没有有效取到 Go Context 文章：授权池里有这篇原文，但收集实际只读取了 Go 1.26 发布说明；因此 Go 调度/取消部分仍不充分。Java 取消材料较前一试次更完整。这是取材质量波动，不能包装成完整研究通过。
- 样本此前用于开发定位，数量也小；未进行独立盲测。调用和输入成本改善已观测到，通用交付率与事实质量尚未由大样本证明。

## 测试迁移

旧测试中有 84 个函数验证已经删除的独立策略图、逐轮覆盖门禁、reread/recovery 重规划及旧 controller 状态。它们被明确删除，**没有通过 skip 或全目录排除把失败藏起来**；逐项清单与替代测试位置见 [retired-test-contracts.json](2026-11-19-delivery-first/retired-test-contracts.json)。历史核验、引用、金额预算、工具授权、总预算、工具账本等仍有意义的测试继续运行。

迁移后的集成测试使用真实批量阅读执行器，检查生产装配、两种响应形式、同一任务重启恢复、三模式共同交付与依据充分性分离。原来“原始阅读直接写成已验证记忆事实”的断言改为不自动提升；记忆检索和已验证事实的幂等存储测试继续保留。

新增回归集中在：

- `tests/research/test_delivery_first_runtime.py`：三种调度差异、一次规划无 evaluator、分支失败隔离、可选规划字段损坏仍保留查询、预算到限仍交接、权限/两种取消/预算存储故障传播、SQLite 重启与新 run 清空旧材料。
- `tests/responses/test_delivery_first.py`：已读尾部条款不重裁、普通题一次写作、审查失败保留正文、旧版完成语义不重标、过期版本/hash/正文篡改不得引用。
- `tests/integration/test_controller_runtime.py`：生产装配实际调用数、可选审查失效、整个应用重启恢复、旧版中断任务拒绝由新算法隐式恢复。

全量后端离线验证命令：

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -m 'not real' -q
```

验证结果在实施清单中记录。唯一排除的是原有真实外部 API 测试标记 `real`，本轮真实模型验收另按上表实际执行。保留现有 LangSmith 第三方弃用提示，不为本轮减法改依赖。

## 基线与边界

修改前实际工作区的 451 个代码、测试、锁文件及脚本已复制到本地 `.local-artifacts/delivery-first-baseline-20261119/`，含文件 SHA-256 与 HEAD 信息，未复制 `.env` 或密钥。它不是只包含已提交内容的 tag。

历史核验函数仍供离线测试/历史读取使用，本轮主要删除生产运行职责和重复图工厂，未声称历史模块文件已全部清空。旧未结束运行不能直接迁移到新图；新运行的来源权限、总预算、usage、工具幂等账本和取消恢复保留。后续若继续减文件，应依据剩余离线依赖删除，不重新启用生产全量核验循环。

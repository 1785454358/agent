# 回答质量优化与实测

本轮按固定评测、写作展示、证据反馈、模型对照依次实施。所有实验与失败阶段保存在本地 `.local-notes/answer-quality-2026-10-23/`，没有覆盖旧运行。

## 改动

- 复用 research-v1 六类开发题，每类固定一题。新增独立写作探针，逐项评审核心需求，同时评审解释、可读性、证据支持与引用。评分错误保留为未知，不当作零分。原始问题与固定原文进入 Writer，参考答案、成功要求只进入评审。
- 普通回答默认上限 2000 字符；比较或至少三个封存要点的任务可用 4000 字符；明确详细要求或六个要点的任务可用 8000 字符。篇幅是上限，简单题不要求写长。调用者设置的更小上限及自定义策略继续生效。
- 将写作策略从图节点中独立，要求结论、依据、条件与适用取舍。支持 Markdown 标题、列表、表格与代码；普通回答的最终审查沿用同一篇幅和原文，并收到研究要点清单，补齐原文已经支持的漏答。
- 前端使用固定版本 react-markdown 10.1.0 和 remark-gfm 4.0.1，忽略原始 HTML、禁止远程图片加载、过滤危险链接。新增表格横向滚动与代码样式。引用处理跳过行内代码与围栏代码，避免把 `items[1]` 改成来源编号。
- 批量整理原文时，先轮流接纳各来源的完整阅读组，再放入追加阅读；相同 n 引用去重，窗口仍不超过 6000 token。省略有明确计数，隐藏的引用仍不能提交发现。
- 修复混合语言版本题的选段缺陷：JavaScript 的驼峰词被当作唯一目标实体时，会排除同页 Python 版本要求。现在为问题明确提及的语言保留完整范围及版本条件，仍使用原文坐标和原字符预算。
- 补查输入区分发现、抓取、阅读、窗口省略与校验拒绝，提供对应恢复提示。诊断不增加事实需求，也不把本次没读到解释为全网不存在。
- 最终审查只要引入未知引用，就拒绝该版本；同时存在合法引用也不能掩盖未知引用对应的新断言。
- 原有真实评测入口统一使用生产模型装配，修复思考参数、JSON 选项和角色超时未对齐的问题。实验身份记录 thinking 与单次传输尝试。

## 固定材料对照

请求模型为 deepseek-v4.1-flash，供应商返回 deepseek-v4-1-flash-261017。每组六道开发题各采样一次，共享固定原始文档；文档选段由当前实现决定。参考要求不进入生成。评审使用同一配置的 disabled 模型，未告知实验组名称。

| 评分 | 改前 baseline | 最终 final |
| --- | ---: | ---: |
| 逐题需求覆盖比例的平均值 | 83.3% | 100% |
| 解释深度 / 5 | 4.00 | 4.17 |
| 可读性 / 5 | 4.67 | 5.00 |
| 证据支持 / 5 | 4.17 | 4.17 |
| 引用准确性 / 5 | 4.33 | 4.17 |

六题最终写作总耗时 14.372 秒，改前 14.145 秒；不是联网研究完整耗时。六题中没有生成或评审错误，每组 12 次供应商调用，生成与评审各六次。

覆盖与表达有改善，引用评分没有稳定提升。评审仍指出部分建议或综合判断的支持范围需要更明确。第一轮仅改写作策略的 candidate 覆盖反而从 83.3% 降至 77.8%，其记录也保留；在修复原文选段与补充验证建议后，candidate-v2 和 final 两轮均为 100%。这些题已经用于开发调优，不能作为留出集成绩。

探针跳过搜索、研究分支及最终事实审查，测量的是固定文档下的写作与材料装配。生产事实审查的要点交接、长度和未知引用拒绝通过独立回归验证；联网路径另做冒烟。六题均为同一出版体系的技术文档，不代表年度科研综述、任意开放题或竞品对比结果。评审为单模型自评，没有人工裁决或统计显著性结论。

## 思考模式对照

candidate-v2 的 disabled 与 thinking-enabled 使用相同固定题、相同阶段写作策略和固定 disabled 评审。

| 项目 | disabled | enabled |
| --- | ---: | ---: |
| 需求覆盖评分 | 100% | 100% |
| 解释深度 / 5 | 4.33 | 4.17 |
| 可读性 / 5 | 5.00 | 5.00 |
| 证据支持 / 5 | 4.33 | 4.50 |
| 引用准确性 / 5 | 4.33 | 4.50 |
| 六题写作耗时合计 | 15.234 秒 | 35.330 秒 |
| 写作总 token，含输入输出 | 18,254 | 22,787 |

单次采样不显示全面收益，耗时约 2.32 倍；因此保留本地原有 disabled 设置。追加的 comparison-dev-01 实际用量探针确认 enabled 返回 1711 个 reasoning token，final 同题 disabled 返回 0。追加探针有独立目录和计量，不混入六题评分。

另对规划与核验各固定一份实际模型输入，原样重放 disabled/enabled，共四次调用：

| 角色 | disabled 耗时 | enabled 耗时 | enabled reasoning token | 协议结果 |
| --- | ---: | ---: | ---: | --- |
| planner | 5.695 秒 | 35.541 秒 | 6510 | 两者均可解析研究需求与分支简报 |
| evaluator | 3.097 秒 | 20.503 秒 | 3207 | 两者均通过原有响应 schema，均自行判断该样本 r1 covered |

Planner 使用 10 月 11 日保存的量子研究规划输入，Evaluator 使用本轮生产冒烟的实际可见材料；每一角色内部两次输入哈希相同。该探针没有执行搜索、引用宿主准入或最终回答，covered 是模型声明，不是独立证据支持结论；规划语义也没有独立评分。它只证明本次开关实际生效、协议可解析及耗时变化，不能推导规划或核验质量不受益。

现有供应商模型目录接口返回 404，未据此猜测其他可用模型。本轮只完成同模型思考开关对照；CLI 支持明确传入其他已开通模型 ID，尚没有跨模型质量结论。未记录价格配置，实际费用保持未知。

## 复现

在 backend 目录执行，真实调用会使用本地已有模型凭据。每个输出目录必须是新目录。

```powershell
uv run --no-sync pytest tests/eval/test_answer_quality.py tests/responses tests/harness/test_synthesis_window.py tests/strategies/test_gap_diagnostics.py -q

uv run --no-sync python -m deeptrace.eval.writer_benchmark --out ../.local-notes/quality-disabled --thinking disabled --max-calls 24
uv run --no-sync python -m deeptrace.eval.writer_benchmark --out ../.local-notes/quality-enabled --thinking enabled --max-calls 24 --baseline ../.local-notes/quality-disabled/results.json
```

`results.json` 保存完整答案、实际可见原文、生成与评审消息、逐项理由、配置、代码身份、供应商返回模型、用量和配对评分。默认六题，可用 `--task comparison-dev-01` 运行单题，用 `--model` 指定已开通模型。固定语料的既有三策略端到端评测仍可通过 `python -m deeptrace.eval --benchmark ...` 运行；本探针不替代它。

## 验证与原始记录

- 最后全量后端离线：1482 passed、2 deselected，70.93 秒。全量测试出现 3 条 aiosqlite 后台线程向已关闭事件循环发送结果的警告，保留于 offline-pytest-final-verified.log；前一轮 1481 项全量无警告。没有隐藏或忽略这些警告，本轮未调整数据库连接生命周期。
- 真实联网生产 Workflow 冒烟：1 passed，包含真实搜索、抓取、模型、引用及最终回答审查，未放宽成功断言。
- 前端：54 tests passed；构建与 ESLint 通过。
- 改动 Python 文件 Ruff、git diff --check 通过。
- 生产 npm 依赖审计 0 个漏洞；完整开发依赖审计仍报告原有工具链的 8 个漏洞。本轮未升级既有包版本，新增包没有引入生产漏洞；未将工具链主版本升级混入本轮。
- 浏览器使用本地 Playwright Chromium 检查 1280px 和 390px：标题、表格、代码及引用正常，页面宽度不溢出，无页面错误。截图是用于视觉检查的人工示例，不是研究质量样本。

本地记录：

- [改前](../../.local-notes/answer-quality-2026-10-23/baseline/results.json)、[第一轮回退样本](../../.local-notes/answer-quality-2026-10-23/candidate/results.json)、[选段修复后](../../.local-notes/answer-quality-2026-10-23/candidate-v2/results.json)、[最终](../../.local-notes/answer-quality-2026-10-23/final/results.json)。
- [思考模式对照](../../.local-notes/answer-quality-2026-10-23/thinking-enabled/results.json)、[思考用量探针](../../.local-notes/answer-quality-2026-10-23/thinking-usage-check/results.json)。
- [规划与核验固定输入对照](../../.local-notes/answer-quality-2026-10-23/role-thinking-probes.json)。
- [桌面截图](../../.local-notes/answer-quality-2026-10-23/report-desktop.png)、[窄屏截图](../../.local-notes/answer-quality-2026-10-23/report-mobile.png)。

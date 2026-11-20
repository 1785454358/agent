# 新对话真实验收（2026-11-18）

目标是从空白工作台输入问题，展示真实研究进度、带引用的回答和来源，作为项目 Demo 或录屏。没有使用固定展示数据代替真实运行。

## 结论

更新模型配置后，两次真实新对话均跑通。修复了缺少阶段事件和内部诊断被展示为研究缺口的问题；最终录屏来自修复后的真实浏览器运行，没有使用固定展示数据。最初的失败记录保留在下方，不能与后续成功记录混为一次运行。

## 最终成功运行与录屏

| 问题 | Run ID | 状态 | 耗时 | 回答字符 | 来源链接 | 模型调用 | Token |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| checkpoint、thread_id 与中断恢复 | `a7cc416db0d7` | completed | 88.22 秒，含截图停留 | 1610 | 5 | 6 | 32443 |
| gather 与 TaskGroup 对比 | `f5c5038602ff` | completed | 109.14 秒，从提交到检测到终态 | 2382 | 4 | 6 | 35708 |

使用 `qwen3.8-max-0902` 和独立 Local 运行目录、lexical 记忆。两次浏览器均无未捕获 JavaScript 异常。第二次运行使用修复后代码，记录六个研究阶段，完成来源抓取、原文阅读、证据评估、回答和审查。

第二次的 4 条来源链接均来自 Python 官方文档，包含不同版本和语言页面，不代表 4 个独立事实来源。`completed` 表示当前覆盖和响应协议通过，不能替代答案事实正确性评测：人工复核发现最低版本的“所有 Python 3.x”表述过宽，代码示例也包含未定义协程占位符。第一次 checkpoint 回答也将异常恢复与 `interrupt()` 恢复混写。原始答案与视频均未人工改写；本轮解决了链路和展示问题，未声称已修复全部模型回答质量问题。

最终本地工件位于 `.local-artifacts/demo-20261118-final/`：

- `new-conversation.mp4`：130 秒完整录屏，含提交、真实等待、结果和来源展示；1440×1000，浏览器已验证可播放。
- `new-conversation-2x.mp4`：上述完整录屏的 2 倍速版本。
- `new-conversation.webm`：浏览器原始录制。
- `01-new-conversation.png`、`02-result.png`：新对话与完整结果截图。
- `result.json`、`summary.json`、`answer.md`：原始结果、供应商用量与回答。

可重复录制（先构建前端并启动真实 API，在 `backend` 执行）：

```powershell
uv run --no-sync python scripts/record_demo.py --base-url http://127.0.0.1:8001
```

脚本通过真实页面的“新研究”与“开始研究”创建独立 thread，支持 `--question`、`--mode`、`--timeout`、`--output`，输出目录不得已存在。它保存视频和终态工件，只有 completed、实质回答、有效编号引用、非空来源且无浏览器异常才返回成功；这些条件不等于逐句事实审查。

## 测试环境与步骤

- 使用已有 `backend/.env` 中的模型、搜索凭据，未输出或修改 API Key。
- 模型为 `qwen3.8-27b`，通过阿里云北京区域兼容接口访问。
- 为新对话启动独立 Local API，运行数据位于 `tmp/demo-acceptance-20261118`，使用 lexical 记忆；未删除用户历史记录。
- Python Playwright 使用真实 Chromium 打开工作台，在页面输入问题并点击“开始研究”，通过生产 `/researches` 接口创建任务。
- 问题：LangGraph 中 checkpoint、thread_id 和中断恢复是什么关系？请给一个最小恢复流程，并解释恢复时哪些步骤可能重新执行。
- 记录真实页面、API 终态、事件、回答和供应商用量；浏览器没有未捕获 JavaScript 错误。

## 最初失败结果（更新模型配置之前）

| 项目 | 结果 |
| --- | --- |
| Run ID | `81bfaa9ba28b` |
| 模式 | Workflow / controller |
| 状态 | `partial` |
| 退出原因 | `insufficient_evidence` |
| 从提交到浏览器记录结束 | 27.50 秒（包含终态等待和截图停留） |
| 回答 | 31 字符，只有未完成提示 |
| 引用来源 | 0 |
| 模型尝试 | 2；均未取得供应商 usage |
| 事件 | 11 |
| 浏览器异常 | 0 |

该次模型请求记录为 `model_request_failed`；搜索三次尝试出现 SSL 错误。随后对同一模型配置进行独立最小请求，得到确定的 HTTP 403，供应商结构化 `code/type` 均为 `insufficient_quota`，说明免费额度耗尽，要求在管理控制台恢复可用额度。额度错误不是修改研究提示词可以解决的问题。

同一搜索配置随后独立请求成功返回 3 条结果，表明先前 SSL 故障具有间歇性，尚无证据将其归因于搜索 Key 无效。没有关闭 TLS 校验。

另一次使用既有运行目录的请求 `215a1c10b801`，先在已有记忆的 BGE-M3 计算阶段等待，之后也遇到 `model_quota_exhausted`。前者属于历史数据路径的准备延迟，不能用它代替新对话的失败根因。

## 已完成的展示修复

1. 模型请求失败后，规划器使用原问题继续搜索；最终页面只显示“部分完成”和通用无来源提示，供应商故障藏在原始事件里。
2. Session Graph 在开始处理时发出 `run.started`，实际回答生成前后发出 `writing.started/completed`；controller 补齐真实规划、核验及补查轮次事件，复用已有 best-effort 事件接口，不改变研究决策或模型调用次数。
3. Sources 只过滤明确以 `diagnostic:` 标记的内部诊断，保留真正的研究缺口和所有来源；原始 API 结果继续保存诊断。
4. 增加真实浏览器新对话录制脚本与成功条件校验；Docker 测试阶段复制 scripts，以便容器内也能运行其确定性校验测试。

按用户要求没有修改额度提示、记忆模块或研究策略。

## 基础验证

- 修改前完整后端验证：1745 passed、1 deselected、33 warnings。
- 修改后完整后端验证：1751 passed、1 deselected、34 warnings，114.75 秒；增加最后一项观察器隔离测试后，针对相关 application/research/recording 测试再跑 39 项，全部通过。警告包括既有 LangSmith SDK 警告和一次 aiosqlite 线程退出时事件循环已关闭；对应 ledger 测试单独重跑通过，未声称已解决线程清理问题。
- `cd frontend; npm run lint`：通过。
- `cd frontend; npm test`：12 个文件、56 项通过。
- `cd frontend; npm run build`：通过。
- `GET /health` 和工作台根页面均返回 HTTP 200。

## 交付状态

- GitHub 仓库公开可访问：<https://github.com/1785454358/agent>。
- GitHub 仓库返回 `has_pages=false`，`https://1785454358.github.io/agent/` 返回 404；没有可用的 GitHub Pages Demo。
- 当前本地工作区存在大量此前未提交的修改，测试结果只描述本地版本；本轮没有提交、推送或发布。
- 固定数据 Showcase 已存在，但不符合本次“真实新对话展示”的验收目标。

本地诊断工件保存在 `.local-artifacts/demo-20261118/`：`summary.json`、`result.json`、`answer.md`、`01-new-conversation.png`、`02-result.png` 和 `new-conversation.webm`。工件位于 Git 忽略目录，没有自动上传。

后续发布需要将经过复核的源码和录屏上传到选定托管服务。本轮没有把本机地址或本地文件描述成公网 Demo。

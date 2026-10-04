# 离线 CI 与长文证据送达诊断

本轮完成评分 CI 配置、离线边界与评分输入限额修复，并定位长文回答阶段的证据覆盖问题。**没有新增真实研究/裁判调用，没有修复生产长文选段，也没有取得新的质量提升数字。**

## 1. CI 已配置，运行验证仍分层

沿用现有 GitHub Actions 与 Docker build job，新增独立 `evaluation` job：

- 只以 `backend/evaluation` 为 build context，安装现有 `requirements.lock`，不安装生产项目或降级生产 SDK。
- 显式 COPY 评分脚本、数据、测试和锁文件，不复制生产配置、历史实验或凭据；不传 secret/build args，不 push 镜像。
- 依赖安装、公开 tokenizer 缓存下载允许联网；评分测试用 `RUN --network=none`。生产 test stage 同样预热 tokenizer，再 `uv run --no-sync pytest -m "not real"`，避免测试时补依赖。
- 后端 test stage 复制 evaluation 文件用于源码身份与配置检查；发布 stage 未增加 Ragas。根 build context 排除独立虚拟环境、tmp 和 .dbg。
- 原来只保护 quality 测试文件的 HTTP guard 移到评分 suite 的 conftest，同步/异步客户端 send 都在到达 transport 前拒绝。Docker 的网络隔离提供另一层限制，配置依据见 [Docker RUN 网络文档](https://docs.docker.com/reference/dockerfile/#run---networknone)。

本机 Docker Linux daemon 未启动，read-only readiness 检查失败；没有擅自启动服务、拉取大镜像、推送代码或触发 GitHub。因此现在是**配置和本地测试已验证，Linux 打包与远端 CI 未验证**，不能写“GitHub CI 已通过”。

新增配置测试检查隔离 context、无 secret 注入、显式文件集合和禁网测试步骤；这些是配置契约，不冒充 Docker 构建执行。

联网透明说明：HTTP guard 的第一次 RED 检查曾对 example.org 发出两次普通 GET，未触及模型 API；之后改用本地 MockTransport 重现 RED，再加 suite guard，后续检查不需要对外请求。没有付费 Provider 调用，也没有把“无模型调用”说成整个工作过程零网络。

## 2. 评分限额错误已修复

原来统一用 answer + question + gold + contexts 的总字符数判断 100,000 上限，即使该指标不用某字段也会被它禁用。例如事实 F1 根本不接收 contexts，却可能因长证据被标 N/A。

现在按实际传给 Ragas 的字段检查：

| 指标 | 纳入大小判断的输入 |
| --- | --- |
| Faithfulness | question、answer、实际选用 contexts |
| FactualCorrectness F1 | answer、gold |
| AgentGoalAccuracy | question、answer、gold |

**仍不静默裁剪输入、仍保留 100,000 字符上限。** 被指标实际使用的内容过大仍为 N/A；这也不承诺在任意模型 token 窗口内一定可评分。真实 judge 请求另有预算、超时与 prompt 大小限制。

用原生 Ragas 实现和受控外部 LLM 返回验证：大而未使用的 evidence/gold 不再屏蔽相关指标，真正超限的 evidence 仍不能进入 Faithfulness。不是 stub 分数或新真实 API 结果。

adapter 更新为 `quality-v2-metric-specific-input-limits`，源码哈希也进入缓存身份；旧真实评分文件未重写，不能拿新 scorer 原地冒充旧评分身份续跑。

## 3. 长文诊断：抓到不等于送达

新增 `deeptrace.eval.context_audit`，只用开发集、冻结原文与 ScriptedResearchModel，经正常 ApplicationResearchService / Harness / ToolGateway / Evidence Store / response 路径运行。

先固定三题，再查看输出：

1. `single_hop-dev-01`：checkpoint 和 thread_id。
2. `multi_hop-dev-02`：interrupt 恢复及副作用幂等。
3. `version_boundary-dev-02`：Python <3.11 async streaming。

每题 Workflow / Baseline 各一次，**6 个 scripted 运行，不是 6 个真实质量样本**。全部应用终态 completed，27 次脚本逻辑模型调用、21 次工具调用。脚本 telemetry 的 Provider 次数为空，不把 null 硬改成实测 0；从固定模型/本地适配器确认此诊断不调用 Provider。

分析在执行结束之后读取 scoring-side 来源片段，未把 gold、引用定位或片段标注交给模型、检索、记忆或 checkpoint。

对每个运行的每处预先定义片段，检查原文是否抓取、实际正文/哈希是否完整、是否进入 research outcome、是否逐字完整出现在 responder 输入：

| 送达阶段 | 片段 × 运行条数 |
| --- | ---: |
| 未抓取 | 2 |
| 已存储但未选用 | 0 |
| 已存储且选用，完整片段未见于回答模型输入 | 8 |
| 完整片段可见 | 0 |
| 缺少 responder，不能判断 | 0 |

这 10 条是片段-运行检查，不是 10 道题。零完整片段可见不等于零事实正确率：部分引用、转述和 researcher findings 也可能提供信息，本审计不做语义判定，不生成 Faithfulness 或 task-success 分数。

实际例子：

- `multi_hop-dev-02` 两个系统都没有抓取 checkpointers 来源，属于检索覆盖问题，不能归因存储丢失。
- streaming 来源完整存储并选用，但 2056–2062 行的 Python 版本限制没有送入 responder；这属于源文到回答上下文的覆盖问题。
- 合成长文回归在尾部放唯一标记，实际 Evidence Store 保留它，而 responder 看不到；同样的标记放短文中则正常送达。

根因追踪落在 `responses/graph.py::_source_block`：它无条件采用 `body[:limit]`，answer/brief/report 的每来源上限分别为 3,000 / 6,000 / 20,000 字符，之后还会进行 token 分配。**提高迭代/请求预算并不能让这个固定前缀自动包含后文。**

本轮不按参考答案位置补资料，不改预算，也不宣称已解决这一生产问题。评分侧 Faithfulness 接收完整选用证据，与回答模型的局部上下文不是一回事，不能由裁判看得到全文反推 Agent 当时也看到了。

## 4. 证据与复现

最终留样：manifest：`../../tmp/context-delivery-verified-20261002/manifest.json`（本地实验留样）、完整答案/证据/模型输入：`../../tmp/context-delivery-verified-20261002/records.json`（本地实验留样）、逐片段送达诊断：`../../tmp/context-delivery-verified-20261002/delivery.json`（本地实验留样）。

实验身份：`22209e0c38131f2f8a97f12fd767d71a71e3fc1d0cf637586a56b3f3c1cdd61e`。

records SHA-256：`fd6da4422cee07746303340f4c7424c011b6b91413df47dee054306fdbf19bbc`。

delivery SHA-256：`df5e50c25eb798c58b06f8b6c00c007d6d1307190a2583c2185bf2d46bedeb3d`。

177 份 manifest 中的源码、依赖与数据文件已复制到 source_snapshot 并逐文件核对哈希，不含 .env。该数量不代表包含工作区所有文件或整个 CI 定义；CI 配置还在当前工作区，未提交/远端执行。实现途中还有一组 6 次探索性诊断，保留在 `tmp/context-delivery-20261002`，不冒充新的独立题或与最终快照合并。

从 backend 执行（诊断输出必须是新目录，不支持覆盖/自动续跑）：

```powershell
.venv/Scripts/python.exe -m deeptrace.eval.context_audit --out ../tmp/context-delivery-new
.venv/Scripts/python.exe -m pytest -q -m "not real"
.venv-ragas/Scripts/python.exe -m pytest evaluation/tests -q
```

需要 Docker 服务后才可另行验证打包：

```powershell
docker build -f backend/evaluation/Dockerfile backend/evaluation
docker build --target test -f backend/Dockerfile .
```

Docker 命令从项目根执行；依赖安装会联网，完整后端镜像可能较大，本轮没有执行它们。

最终验证：**714 项项目测试通过 / 2 real tests excluded，34 项独立评分测试通过**；本轮源码 Ruff E/F/I/UP/B/SIM/C4（排除既存 C420）、测试 F/I 和格式检查通过。TDD 包括输入限额的真实框架 RED/GREEN、短/长文正常应用回归及损坏/重复/缺失轨迹拒绝；systematic-debugging 用于分层定位，代码审查纠正了打包路径与 Windows fixture 换行问题。

旧正式研究、评分、记忆记录的完整哈希与前轮相同。真实研究仍为之前 1 道开发配对题，正式累计 30 次研究 Provider 尝试 + 16 次裁判尝试；本轮新增付费尝试 0。此前旧 CLI 的未知用量事件仍单独披露，不并入这些正式数字。

## 5. 下一项修复建议，尚未实施

推荐在**共用回答上下文边界**加入有界的“按用户问题选段”：原文确定性分段，以用户问题匹配段落，保留必要标题/相邻段，记录来源位置和被省略范围，再沿用现有字数/token 上限。Baseline 与 Harness 都用同一个选择器，不使用 gold、预期来源或评分片段，不引入向量库/新模型调用。

另外两个选项：只扩大前缀上限改动最少但仍可能遗漏尾部并增加成本；引入 embedding/reranker 更灵活但增加依赖和实验变量，不适合当前简化目标。

验收重点是尾部相关事实能进入实际 responder、短文不退化、引用与来源行号一致、两系统同规则、token 安全网仍有效、参考改变不影响选段。不据此承诺真实模型质量提升。

这一生产行为变更需用户确认后再写实现计划并进行 TDD；当前报告仅提出修复方向。完整真实矩阵、公开任务实时执行、人工盲评与真实语义记忆收益仍未完成。

后续记录：用户已确认该方向，共用按问题选段器现已实现。上述结果保留为改动前基线；实现、复测和剩余限制见 [按问题选段报告](query-excerpts-20261002.md)，不回写或覆盖这组原始实验。

# 按问题选段：实现与证据送达复测

## 结果

已将共用 responder 的固定前缀摘录替换为确定性的问题相关选段。Baseline 和 Harness 使用同一个入口；没有新增模型调用、依赖、服务或扩大预算。尾部事实、短文保持、中文问题、单个超长段落、参考答案隔离、来源定位与 token 裁剪都有回归测试。

同一组 **3 道预选 dev 题 × 两系统，共 6 次脚本运行**，10 次参考片段-运行检查如下：

| 字面片段送达阶段 | 改动前 | 改动后 |
| --- | ---: | ---: |
| 完整出现在 responder 输入中 | 0 | 2 |
| 已保存并选用，但完整片段未出现 | 8 | 6 |
| 来源未抓取 | 2 | 2 |

另外两类（已保存未选用、没有 responder 输入）均为 0。新增可见的是 interrupts 原文 1352–1354 行，在两个系统中均完整出现；来源缺失仍为 multi_hop-dev-02 的 checkpointers。所有 6 次脚本运行 completed，共 27 次脚本模型调用、21 次受控工具调用；**不是 6 次真实 API 实测或答案正确率**。缺少 Provider 遥测保留为 null，不冒充实测 0 次。

2/10 不是质量得分；余下 6 次不出现完整引用，也不证明相关事实完全没有送达。指标要求整段逐字存在，部分文本或研究发现可能已包含事实。这轮没有运行新裁判，不推断真实模型质量、显著性或相对商业 DeepResearch 收益。

## 简化实现

[共享选段器](../../backend/src/deeptrace/responses/excerpts.py) 的输入只有原文、用户问题和现有每来源字符上限，算法标记 `query-windows-v1`：

1. 短文原样返回；长文按空行分段，单段超过 900 字符时用步长 750 的重叠窗口扫描整个已存正文，不再限定文档开头。
2. 问题前 4096 字符抽取英文/数字词项和中文双字词项，过滤常见英文虚词；按命中词项的文内稀有度排序，平分按原文位置。仅为轻量词项匹配，不是 embedding/reranker，也不称为标准 BM25。
3. 候选保留前后最多 120 字符的局部上下文，合并重叠范围，在预算内选择并按原文顺序展示。标题和否定/版本限定在附近时会保留，但不是完整章节或语义保证。边界可能切开句子/代码，明确提示片段边界不完整。
4. 无可用命中或命中范围无法放入预算时回退前缀。原文行号、字符位置、省略提示均计入现有摘录上限：answer 3000、brief 6000、report 20000。极小限额装不下位置标签时，位置仍由事件记录。

保留现有来源标题、URL、证据 ID 与 `[n]` 引用映射；不读 gold、评分引用或期望 URL 来挑片段。EvidenceStore 正文和内容哈希不变，图状态不保存全文。选段不承诺覆盖每一个问题要求，也无法替代检索覆盖。

`response.excerpts` 记录原始字符范围（Python 字符下标，零起点、右端不含）、一基行号、被省略字符范围和选段策略，不记录全文。`pre_token_ranges` 明确表示 token 分配**之前**的范围；每次生成/纠正分别记录 `full / truncated / dropped`，不能把选中当成已经完整送达。事件存储失败不影响回答。实际模型输入是送达判定的最终证据。

现有 token allocator 仍会裁剪/丢弃弹性来源，固定指令过长时仍可能 pinned overflow；本轮没有改变这套行为。完整抓取、保存、选段、token 分配、事实正确性是不同层次。

## 真实抓取的额外边界

[AsyncWebFetcher](../../backend/src/deeptrace/tools/scraper/fetcher.py) 默认 `max_page_chars=20000`，进入 RawDocument 的正文已经是截取后的文本。回答层不能找回这一步已丢掉的尾部。本轮离线语料送达的是冻结完整官方文档，不能把 48505 字符附近片段的成功送达直接宣称为真实网页抓取能力。抓取截断的可观测性和策略仍是单独待处理的问题，这里没有悄悄提高抓取上限。

## 留样、身份与复现

最终输出：实验 manifest：`../../tmp/context-delivery-query-excerpts-verified-20261002/manifest.json`（本地实验留样）、原始答案/完整证据/实际模型输入：`../../tmp/context-delivery-query-excerpts-verified-20261002/records.json`（本地实验留样）、逐片段送达检查：`../../tmp/context-delivery-query-excerpts-verified-20261002/delivery.json`（本地实验留样）。

- 实验身份：`a8d928c9bd271c1f46c8f71aeb2e02adca1a8944e6b0031d97877355e43cb0c8`。
- records SHA-256：`56c3e0cdc6e86080a799516c6dc3817e9731179ac92b7b4af90ed1554a58d784`。
- delivery SHA-256：`21e3d1f0dfc44bf577a2a253b54446dc01ab2161a271e9113626847fa4bf3b5b`。
- manifest 列出的 178 份源码、依赖和数据文件已复制到 source_snapshot，逐文件核对哈希；不含 .env，不声称包含全工作区/CI 定义。

与 [改动前报告](ci-long-context-20261002.md) 使用相同题目、冻结资料、策略、脚本模型和预算，仅生产实现/源码身份改变。首轮选段探索输出保留在 `tmp/context-delivery-query-excerpts-20261002`，不与最终 6 次运行合并冒充更多独立题。开发题已用于诊断，不包装为未见测试集结论。

从 backend 执行，输出必须为新空目录：

```powershell
.venv/Scripts/python.exe -m deeptrace.eval.context_audit --out ../tmp/context-delivery-next
.venv/Scripts/python.exe -m pytest -q -m "not real"
.venv-ragas/Scripts/python.exe -m pytest evaluation/tests -q
```

回归覆盖 23 项选段/响应测试和两系统实际轨迹隔离测试；原无匹配尾部丢失测试继续保留，避免错误承诺“任何尾部都能进入模型”。最终项目全套 **738 passed / 2 real deselected**，独立评分环境 **34 passed**。源码 Ruff E/F/I/UP/B/SIM/C4（排除既存 C420）、相关测试 F/I、格式检查及 diff whitespace 检查通过。

代码自审覆盖正确性、边界、简洁性、依赖、数据隔离和性能：采用独立纯函数模块，避免继续堆叠响应图逻辑；行号用预计算换行位置二分定位，避免在每个候选上重复扫描全文。未做独立第二模型审查或 Docker 构建。

旧真实研究、评分和记忆留样文件哈希保持不变，本轮新增付费调用 0。完整真实矩阵、人工 gold/盲评、公开实时任务及 Docker/远程 CI 通过仍未完成。

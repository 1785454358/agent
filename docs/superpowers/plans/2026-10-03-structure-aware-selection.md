# Structure-Aware Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 相同额度内保留结构块，分别考虑封存答案要点，改善原文送达。

**Architecture:** 共享 evidence_views 生成有界原文候选；评估器通过 optional focus_queries 提供最多六项要点。保持 supports 优先、原文坐标和所有门禁。

**Tech Stack:** Python stdlib、pytest、LangGraph；隔离 Ragas 0.4.3 原生评分。

**Spec:** ../specs/2026-10-03-structure-aware-selection-design.md，用户书面审阅后回复“可以”。

## Global Constraints

- 生产仅 tools/evidence_views.py 和 strategies/evidence_evaluation.py；不加依赖/服务/schema/模型，不修改 quote 匹配、答案提示或评分。
- 每来源评估 3000 字符、最多 8 来源；完整 SourceExcerpt 渲染与既有工具 JSON/token 限额均受保护。候选段数 min(16,max(1,limit//600))。
- 短文原样；900 内完整段落；长段按句/行边界；超长不可切单位允许有界不完整回退；原文空白/标点/Unicode 不改。
- 已验收 supports 优先，旧调用/显式 start 范围/旧持久化契约保持；掉落和隐藏段不能支持，事件失败隔离。
- 无可用 subagent/executing-plans 技能，沿已用内联方式执行、五轴自审，不再询问执行方式。
- 既有大量 dirty 工作保留，不整体提交。验证/付费期间冻结源与 HEAD，以 manifest 185 文件哈希快照留样；新测试另存。

### Task 1: 结构块与均衡 selector

**Files:** Modify backend/src/deeptrace/tools/evidence_views.py；Create backend/tests/tools/test_structure_selection.py。

**Interfaces:** 保留现有返回 SourceExcerpt / tuple[EvidencePassage,...]。三个 select_* 入口加 keyword-only `focus_queries: list[str] | None = None`，原参数不改。

- [x] RED 写行为回归：独立字面事实，选段包含完整否定/版本限定、不吞相邻段落片段、长段在句/行结束；竞争场景两项各有事实、重复要点不浪费范围；短文/超长文本/小额度/坐标/确定性。

```python
body = "Unrelated.\n\n" * 400 + "## Recovery\n\nResume does not replay writes.\n\n"
excerpt = select_source_excerpt(body, "replay writes", 600)
assert "Resume does not replay writes." in excerpt.text
assert len(excerpt.text) <= 600
assert all(body[r.start:r.end] in excerpt.text for r in excerpt.ranges)
```

- [x] backend 运行 `.venv/Scripts/python.exe -X utf8 -m pytest tests/tools/test_structure_selection.py -q --tb=short`，确认真实行为缺失而非错误夹具。
- [x] GREEN 替换原候选构造/排序选择，复用 `_terms/_merge/_render`；只增加小型结构候选助手，不增加配置对象或调度层。

```python
# ranked 含当前要点匹配候选；试放整块，序列化长度是真正字额。
proposed = _merge([*selected, (start, end)])
if len(proposed) <= min(16, max(1, limit // 600)):
    if len(_render(body, proposed, newlines).text) <= limit:
        selected = proposed
```

- [x] focused 第一轮各尝试最佳 fit，一候选多项复用；原问题填剩余；邻近完整标题最后试放。旧 supports 布局不改，参数传至剩余 query 选段。
- [x] 新旧 tests/tools/test_evidence_views.py、test_evidence_read.py 和 tests/responses/test_excerpts.py、test_supported_findings.py 通过；范围坐标只按 body 原样验证。

### Task 2: 真实评估入口与旧轨迹回放

**Files:** Modify backend/src/deeptrace/strategies/evidence_evaluation.py；Create backend/tests/strategies/test_structure_evaluation.py；Create docs/evaluation/structure-selection-validation-20261003.md。

**Interfaces:** assemble_evaluation_view 的公开接口/预算/JSON 不改，只传固定要点。

- [x] RED 通过真实 assemble_evaluation_view 构造竞争正文，断言各字面事实进入可见 passages；三模式真实 evaluator 仅替换外部模型，验证两个事实、原问题、宿主支持与 checkpoint 不变。
- [x] GREEN 移除拼接要点作为唯一 query，传原 question 与 focus_queries。

```python
passages = select_supported_passages(
    record, body, supports, question=question, limit=3000,
    focus_queries=[item.description for item in requirements],
)
```

- [x] 回放旧批 corpus/question/requirements；检查 super-step/thread_id 字面段落送达与原坐标，不向 selector 提供 gold。结果只称离线送达，不冒充重运行质量。
- [x] 定向三模式/工具预览/Answer/Report/支持/授权/记忆/恢复回归；backend Ruff check + format --check 仅两个生产文件与新测试。对照旧 manifest 仅两生产文件变化；五轴审查及简短性能检查。

### Task 3: 冻结回归与唯一真实复测

**Files:** 新增登记的三个 tmp 目录；更新验证报告、docs/README.md、本计划/规格流程。

- [x] 冻结 source_identity/HEAD 后 backend 完整 `.venv/Scripts/python.exe -X utf8 -m pytest -m 'not real' -q --tb=short`、隔离 `.venv-ragas/Scripts/python.exe -X utf8 -m pytest evaluation/tests -q --tb=short`；期间不改源码/提交。
- [x] 付费前登记：三题、三模式、唯一9运行；用 load_questions/load_corpus DTO `_content_hash` 验证旧 analysis-card；输出目录不存在，凭据只查是否存在。
- [x] backend 启动唯一研究批次：

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval --model real --modes plan_execute,workflow,multi_agent --repeats 1 --response-mode answer --response-max-chars 2000 --max-model-calls 40 --max-tool-calls 24 --max-provider-attempts 80 --max-batch-model-calls 360 --max-batch-provider-attempts 720 --agent-iterations 12 --max-output-tokens 4096 --run-timeout 360 --dataset ../tmp/evidence-loop-real-20261002-assets/questions.jsonl --corpus ../tmp/evidence-loop-real-20261002-assets/corpus.jsonl --run-prefix structure-selection-real-answer-20261003 --out ../tmp/structure-selection-real-answer-20261003
```

- [x] 按 manifest.source_files 原生 Copy-Item 保存 source_snapshot；验证解析后的源/目标在工作区/批次范围、逐份 SHA256 相同；不复制 .env，新测试另存/hash。保留完整失败和 partial，不重跑或扩预算。
- [x] 原生评分一次，严格身份统计一次：

```powershell
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/structure-selection-real-answer-20261003/quality_eval.json --out ../tmp/structure-selection-real-answer-quality-20261003 --max-provider-attempts 144 --env-file .env
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval.compare_cli --input ../tmp/structure-selection-real-answer-20261003/quality_eval.json --scores ../tmp/structure-selection-real-answer-quality-20261003/quality_scores.json --metadata ../tmp/evidence-loop-real-20261002-assets/analysis-card.json --out ../tmp/structure-selection-real-answer-comparison-20261003
```

- [x] 核对 source/HEAD/snapshot/judge 不变，记录逐题完成状态、答案/缺口、角色调用、范围/visibility、quote 失败、Provider/Token、NA与均值覆盖；旧新只作 dev 诊断，无新 baseline n=0/delta/CI=null，无联网 E2E、独立人工校准/总体提升声明。
- [x] 报告、索引和流程标记结束；只交付已批准改动，剩余引用/错误缺口/裁判问题单列，不混改。

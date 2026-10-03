# Grounded Research Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> Session fallback: those two execution skills are unavailable. Execute inline with the available test-driven-development, systematic-debugging and code-review-and-quality skills; no new thread or worktree is required. Read the approved spec and each applicable skill before execution.

**Goal:** Improve key-fact acquisition and lossless grounded finding handoff across all three research modes without replacing the Harness.

**Architecture:** Extend read_evidence with exact page lookup; add one local record_findings tool using host-issued, branch-scoped short references. Transfer candidate Finding / EvidenceSupport through existing branch outcomes; the shared evaluator alone accepts claims and judges coverage, and the existing Writer consumes only accepted findings.

**Tech Stack:** Python, Pydantic, LangChain messages, LangGraph, pytest, current ToolGateway/EvidenceStore, isolated Ragas 0.4.3. No new packages or services.

**Spec:** [2026-10-03-grounded-research-handoff-design.md](../specs/2026-10-03-grounded-research-handoff-design.md), user approved on 2026-10-03 after design commit c568dca.

## Global Constraints

- Preserve Harness, three modes, tenant/URL/evidence authorization, checkpoint, recovery, stop priority, memory admission and public response formats; evidence_contract_version=3 remains unchanged.
- P&E is the primary mode; Workflow and Multi-Agent are tested too. Answer is the primary quality output; Report is independently regressed.
- read_evidence: find 1–200 characters; strict nonnegative after; query/start/find exclusive; limit 1–3000 characters; preserve Python raw character coordinates.
- record_findings: 1–5 drafts/call; claim 1–1000 characters; 1–3 distinct refs; confidence 0–1; 20 findings/branch; 128 stable read refs/branch; quote units at most500 characters. All-or-nothing validation per record call.
- Candidate findings are not accepted facts or coverage. Do not bypass semantic assessment, generate support from summaries, mint unseen text, or write candidates to long-term memory.
- Evaluator limits stay 8 sources / 3000 characters per source / 128 quote units / existing token allocator; accepted cores precede candidate cores and optional context. Claims with incomplete final supports are omitted atomically.
- Local records count in Agent executed_steps, not Gateway calls. Report Gateway, record, todo and total Agent tool counts separately; no hidden quota increases.
- Per run: 40 logical model calls / 80 Provider attempts / 24 Gateway tool entries / 12 branch iterations / 360 seconds. Research max output4096 tokens, Answer2000 characters, temperature0, doubao-seed-2.0-lite, long-term memory disabled.
- Dev batch: 9 runs, 360 logical / 720 Provider research, scoring144 Provider. Live batch: 3 runs, 120 logical / 240 Provider research, scoring48 Provider. Two batches, once each, no selected reruns/rejudging/gold edits.
- Do not change the original scorer, Ragas judge configuration, previous artifacts or dev gold. No new baseline: strict pairs n=0 and delta/CI=null; previous-score contrast is descriptive, not causal uplift.
- Workspace is dirty. Before implementation save task-start source hashes/snapshots; keep unrelated changes. Commit this plan and self-owned new files only when staged contents are checked. Do not stage all overlapping production files or pre-existing untracked files merely to make HEAD look complete; reproducibility uses the entire frozen source snapshot, not HEAD alone.
- Shell examples run from D:/Dev/Projects/agent_new/backend unless labeled root. Use apply_patch to create/edit source, tests, scripts and docs. Commands below are instructions, not already executed validations.

## File map and interfaces

| Files | Responsibility |
| --- | --- |
| tools/evidence_read.py | Existing authorization and bounded preview, plus exact find/after |
| harness/research_findings.py (new) | Bounded draft validation, numbered actual-read preview, host resolution and stable finding IDs |
| harness/agent_state.py, agent_tools.py, agent_executor.py, checkpoint.py; domain/research.py | Branch-local registry, transactional note state, tool wiring, finalize and recovery |
| harness/policies/agent_context.py, harness/prompts.py | Elastic candidate context and targeted reading/recording instructions |
| tools/evidence_units.py, strategies/evaluation_materials.py, evidence_evaluation.py | Relevant read fallback, support-priority handoff and final atomic visibility |
| strategies/planning.py | Reuse sealed requirements as the research brief; make necessary answer obligations explicit |
| eval/env.py, runner.py, trajectory.py, experiment.py; eval/live.py (new) | Same evaluator runtime with injectable live adapters, honest identity and local-tool telemetry |
| New focused tests under tools, harness, strategies, integration, eval | Each boundary's RED/GREEN tests; no known dev keyword in production logic |
| docs/evaluation/grounded-handoff-validation-20261003.md (new) | Preregistration, raw results, visibility/cost audits and limitations |

Source paths in the map are relative to backend/src/deeptrace; docs paths are relative to the workspace root. New tests are specified below. Do not move all existing helper modules or redesign three-mode orchestration.

## Task 1: Exact lookup through the existing authorized reader

**Files:** Modify src/deeptrace/tools/evidence_read.py; test tests/tools/test_evidence_read.py. Consumes the existing ReadEvidenceArguments, _record, _fit_preview and make_evidence_passage. Produces find/after selectors and selection.found/next_start; no new network tool.

- [ ] Append this meaningful failing Gateway test using that test file's existing helpers; add parametrized negative cases for find+query/start, after without find, boolean/negative after, empty/201-character find and find longer than limit.

```python
@pytest.mark.asyncio
async def test_find_returns_raw_match_and_can_advance_without_prefix_fallback():
    fixture = build_gateway_fixture()
    body = "标题🙂\n" + "背景。" * 600 + "API_x(v)\n条件甲。\nAPI_x(w)"
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft(body))
    grants = EvidenceAuthorization(frozenset([record.id]))
    first = await _read(fixture, record.id, grants=grants,
                        arguments={"find": "API_x", "limit": 200})
    assert first.ok
    payload = json.loads(first.preview)
    assert payload["selection"]["found"] is True
    assert payload["selection"]["next_start"] == body.index("API_x") + 5
    assert any("API_x(v)" in p["text"] for p in payload["passages"])
    for p in payload["passages"]:
        assert p["text"] == body[p["start"]:p["end"]]
    missing = await _read(fixture, record.id, grants=grants, call_id="missing",
                          arguments={"find": "not-in-page"})
    assert missing.ok
    empty = json.loads(missing.preview)
    assert empty["passages"] == []
    assert empty["selection"]["found"] is False
    assert empty["selection"]["next_start"] is None
```

- [ ] Run `.venv/Scripts/python.exe -m pytest tests/tools/test_evidence_read.py -q`; expect an assertion failure at first.ok because find is not accepted. Do not count an import failure as the mechanism RED.
- [ ] Add find/after to ReadEvidenceArguments, with after default None; only find mode converts None to0. Preserve strict start/limit validation and add selector checks. The core lookup is:

```python
position = body.find(arguments.find, arguments.after or 0)
found = position >= 0
next_start = position + len(arguments.find) if found else None
if found:
    before = min(120, (arguments.limit - len(arguments.find)) // 2)
    first = max(0, position - before)
    stop = min(len(body), first + arguments.limit)
    passages = (make_evidence_passage(record, body, first, stop),)
else:
    passages = ()
```

Integrate this inside read() after authorization. Add optional selection fields to _fit_preview and keep JSON complete at4000 characters. The actual find preview must retain the match even for escape-heavy content; if bounded metadata cannot fit it, fail explicitly rather than claim a successful visible match. Query/range callers receive their existing metadata shape.

- [ ] Expand GREEN tests: advance with next_start, end-of-body/after beyond body, Unicode raw coordinates, escaping, revoked grant/historical source/replayed read. Run the whole existing reader test file and tests/tools/test_registry.py.
- [ ] Review and record the task result in this plan; only stage the plan, not the existing dirty reader/test files wholesale.

## Task 2: Small bounded reference/record helper, with no strategy dependency

**Files:** Create src/deeptrace/harness/research_findings.py and tests/harness/test_research_findings.py. Consumes ReadEvidenceAnchor, EvidencePassage, split_quote_units, Finding, EvidenceSupport, ResearchTopicInput and HarnessContext. Produces:

- `RecordFindingDraft`: claim, refs, confidence, extra=forbid; `RecordFindingsArguments`: findings list.
- `number_read_preview(preview: str, references: dict[str, ReadEvidenceAnchor]) -> tuple[str, dict[str, ReadEvidenceAnchor], list[str]]`: pure complete-JSON projection and stable registry, no mutable input effects.
- `resolve_recorded_findings(arguments: RecordFindingsArguments, *, task: ResearchTopicInput, references: dict[str, ReadEvidenceAnchor], existing: list[Finding], context: HarnessContext) -> list[Finding]`: async, returns the complete new list or raises ValueError/validation failure; no state mutation or coverage action.

- [ ] Write tests before the helper. For a validated preview matching the payload shape in tests/harness/test_read_anchors.py, assert every displayed ref maps to its exact raw range, repeated numbering reuses refs, registry has no entries for omitted units, and the serialized preview is <=4000 characters. Test128 capacity, invalid preview, model-only messages and preserved input dictionaries. Establish the new module's declarations only after tests exist; missing imports alone do not count as evidence of the behavioral RED.
- [ ] Define bounded drafts, explicitly forbid duplicate refs and validate stable registry keys against `^n[1-9][0-9]{0,2}$`. The draft validation core is:

```python
class RecordFindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str = Field(min_length=1, max_length=1000)
    refs: list[str] = Field(min_length=1, max_length=3)
    confidence: float = Field(ge=0, le=1)

    @field_validator("refs")
    @classmethod
    def distinct_refs(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate_read_reference")
        if any(re.fullmatch(r"n[1-9][0-9]{0,2}", value) is None for value in values):
            raise ValueError("invalid_read_reference")
        return values

class RecordFindingsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[RecordFindingDraft] = Field(min_length=1, max_length=5)
```

- [ ] Implement numbering: parse only the actual successful read preview; validate its root and passage metadata using capture_read_anchors; instantiate EvidencePassage from the displayed passage dictionaries; split using split_quote_units without accepted supports; mint/reuse n refs in an independent working dictionary. Render the numbered units and selection metadata, remove whole units from the end until JSON fits; register only survivors. At capacity allow existing refs, omit new units with read_reference_capacity. Do not register historical previews; do not truncate the already numbered JSON with string slicing.
- [ ] Implement record resolution: allowed IDs = task.authorized_evidence_ids plus the branch-owned evidence IDs supplied by the caller in Task3; check each ref's ACTIVE record and current version/hash/body slice, with quote length1..500. Build EvidenceSupport from raw text, derive evidence_ids from supports and Finding ID from SHA256 of `[run_id, thread_id, caller_id, query, claim, sorted support identities]`; resolve all drafts first, deduplicate by host ID, then enforce20 capacity and return. Any unknown/refused source, stale version, bad hash/range or batch overflow raises a validation error and leaves existing unchanged. Do not treat confidence as acceptance.

The deterministic ID payload must use json.dumps(identity_payload, ensure_ascii=False, separators=(",", ":")); support identity is `[evidence_id, version, content_hash, start, end]`. Prefix IDs with `research-`; no model-provided IDs. Do not accept Finding.model_copy objects without revalidation. The resolution core, after constructing a revalidated support list, is:

```python
support_keys = sorted([s.evidence_id, s.version, s.content_hash, s.start, s.end]
                      for s in supports)
identity_payload = [task.run_id, task.thread_id, task.caller_id, task.query,
                    draft.claim, support_keys]
encoded = json.dumps(identity_payload, ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
identity = "research-" + hashlib.sha256(encoded).hexdigest()[:32]
finding = Finding(id=identity, claim=draft.claim, confidence=draft.confidence,
                  evidence_ids=list(dict.fromkeys(s.evidence_id for s in supports)),
                  supports=supports)
if identity not in {item.id for item in working_findings}:
    working_findings.append(finding)
if len(working_findings) > 20:
    raise ValueError("research_finding_capacity")
```

`working_findings` is a copy of existing, never the original list. Return it only after every draft has resolved successfully.

- [ ] Run `.venv/Scripts/python.exe -m pytest tests/harness/test_research_findings.py tests/harness/test_read_anchors.py -q`. Include mixed valid/invalid batch atomic rejection,20 capacity, repeated claim/reference order, foreign tenant, source revocation and no-network recording. Review then commit only the newly created helper/test plus plan after staged-content checks.

## Task 3: Wire the local tool, durable state, context and honest counts

**Files:** Modify domain/research.py, harness/agent_state.py, agent_tools.py, agent_executor.py, checkpoint.py, policies/agent_context.py. Create tests/harness/test_record_findings_loop.py. Consumes both Task2 helpers. Produces state.research_refs, state.research_findings and state.research_finding_diagnostics; outcome.research_findings and outcome.research_finding_diagnostics default to empty, bounded at20/100. The registry stays internal to the branch, not public model arguments.

- [ ] Use build_gateway_fixture, ResearchTopicInput and build_research_agent_graph for a scripted Reader: first call read_evidence on an authorized generic source; on the returned numbered preview call record_findings with its displayed n ref. Compile with max_iterations=2, assert the outcome retains one raw-supported candidate and its stop reason remains iteration_limit, executed_steps=2, Gateway calls=1, no global coverage added. Parametrize all modes. This is the unknown-tool/state-loss RED, not an import-only test.

The scripted response for the second turn must take the actual label, not invent one:

```python
payload = json.loads(returned_read.content)
preview = json.loads(payload["preview"])
ref = preview["passages"][0]["ref"]
return AIMessage(content="", tool_calls=[{
    "id": "record-1", "name": "record_findings",
    "args": {"findings": [{"claim": "The operation requires its context key.",
                            "refs": [ref], "confidence": 0.8}]},
}])
```

- [ ] Register the internal schema alongside write_todos in RESEARCH_TOOLS, not ToolName/ToolRegistry. Fix the read argument-defaulting block in agent_tools.invoke to inject task.query only when query/start/find are all absent. Add the new plain dict/list state fields and defaulted outcome fields; copy candidates in finalize for all stop reasons. Anchors/refs are host state, not derived from arbitrary model messages. Concrete wiring excerpts are:

```python
if all(args.get(key) is None for key in ("query", "start", "find")):
    args["query"] = task.query

# Added AgentExecutorState entries:
research_refs: dict[str, ReadEvidenceAnchor]
research_findings: list[Finding]
research_finding_diagnostics: list[str]

# Added ResearchTopicOutcome model fields:
research_findings: list[Finding] = Field(default_factory=list, max_length=20)
research_finding_diagnostics: list[str] = Field(default_factory=list, max_length=100)

# In finalize's existing ResearchTopicOutcome constructor:
# research_findings=state.get("research_findings") or []
# research_finding_diagnostics=state.get("research_finding_diagnostics") or []
```

- [ ] In execute_batch preserve read Gateway concurrency, but project successful read results and assign n refs in call-index order before final ToolMessages. Local record/todo writes run serially; their reference authorization is a snapshot at the beginning of the batch, so a read in that same batch cannot satisfy record arguments. Use `task.model_copy(update={"authorized_evidence_ids": stable_union_of_branch_owned_and_parent_ids})` only inside the host call; do not accept model-issued grants. Record updates replace the local working finding list atomically; a batch failure leaves it unchanged. Unknown/invalid refs are recoverable validation errors, not successful observations or fatal tool errors.
- [ ] Follow the existing stop guard before each local action; do not override cancelled/budget_exhausted. Return state changes, ToolMessages and executed_steps from one existing node update; keep checkpoint transaction boundaries, not a separate note persistence service. Register any new checkpoint DTO only if it is actually stored; plain n->ReadEvidenceAnchor dict reuses the existing serializer allowlist. Emit bounded `agent.local_tool` telemetry (tool, call ID, caller/branch, ok/error, counts), never source instructions; telemetry failure must not determine runtime success.
- [ ] Add elastic candidate content only after preserving the pinned task and complete latest tool exchange. Introduce `prepare_messages_with_diagnostics(state, tools, budget) -> tuple[list[AnyMessage], list[str]]`; keep prepare_messages as a compatibility wrapper returning element0. Include candidate claim and source identifiers as explicitly unaccepted background using existing message_tokens accounting. call_model consumes the new helper and returns omission diagnostics with its existing node updates, not by mutating the durable transcript or recomputing a second message view in prepare_context. Never pin all20 claims ahead of user constraints.
- [ ] GREEN tests cover checkpoint roundtrip of state and outcome, old v3 defaults, existing v1/v2 restrictions, simultaneous reads, duplicate/replayed records, same-batch future ref rejection, local-write ordering, stop before local action, revoked sources and no memory writes. Run `.venv/Scripts/python.exe -m pytest tests/harness/test_record_findings_loop.py tests/harness/test_evidence_reading.py tests/harness/test_read_anchors.py tests/harness/test_agent_invariants.py tests/integration/test_recovery.py -q`. Review and update plan without staging overlapping dirty production files wholesale.

## Task 4: Replace chronological handoff with grounded candidate material

**Files:** Modify tools/evidence_units.py, strategies/evaluation_materials.py and evidence_evaluation.py. Create tests/strategies/test_candidate_materials.py and tests/integration/test_grounded_handoff_modes.py. Consumes Finding/EvidenceSupport and outcome.research_findings. Produces optional `research_findings: list[Finding] | None = None` parameter on assemble_reference_evaluation_view; EVIDENCE_VIEW_JSON gains candidate_findings with claim/confidence/support p refs, only when all supports are visible. Existing callers and final reference map remain compatible.

- [ ] Build a generic source with an irrelevant early4000-character anchor and a late short required fact. Record the late fact as a candidate; keep accepted findings empty. Through the real three-mode evaluator nodes, capture the actual model prompt, assert the late quote and candidate claim survive and reference raw source coordinates. A helper-only view test is insufficient. Use Runtime, ScriptedModelGateway, ResearchTopicOutcome, ResearchRequirement and node mapping as in tests/integration/test_support_budget_consumers.py.

For a direct material assertion, use this exact interface after fixture seeding:

```python
view = await assemble_reference_evaluation_view(
    fixture.context, question="Explain the operation and its prerequisite.",
    requirements=[ResearchRequirement(id="r1", description="Operation and prerequisite")],
    evidence_ids=[record.id], findings=[], research_findings=[candidate],
    read_anchors=[early_anchor],
)
payload = json.loads(view.prompt.split("EVIDENCE_VIEW_JSON:\n", 1)[1])
assert payload["candidate_findings"][0]["claim"] == candidate.claim
assert all(view.references[s["ref"]].text == original.quote
           for s, original in zip(payload["candidate_findings"][0]["supports"],
                                  candidate.supports, strict=True))
```

- [ ] Observe the RED without new auto-accepted findings. Implement source ordering by accepted/candidate support priority, then stable existing source order. Validate supports against actual authorized source IDs and current bodies. Feed accepted cores before candidate cores into existing supported_ranges; reserve necessary union before optional context. Extend select_read_passages with optional candidate supports, preserving old keyword callers. Replace chronological anchor spending with requirement-based selection among validated read units; use the existing tokenizer/ranking primitive, not a second semantic ranker. With no candidates use the same relevance-based read fallback; never claim unread fallback units were read. Emit exact units for every retained candidate support, including nested/overlapping support ranges; do not rely on split_quote_units' non-overlapping protected-range rule to retain all of them. Deduplicate by passage identity, charging raw range union and actual serialized token usage separately.
- [ ] Render candidate groups atomically: a candidate appears only when every validated support has its exact raw-text range in final visible units. Build p refs after character/unit allocation; render candidate claims and support mappings from that same map. Recount actual serialized prompt including candidate claims and remove lowest-priority whole units/groups until within budget. If removal makes any candidate incomplete, omit the entire claim, mark candidate_material_omitted and render again. Do not leak a claim in pinned metadata after its supports are dropped.

Inside evaluation_materials define `visible_candidate_payloads(candidates: list[Finding], references: dict[str, EvidencePassage]) -> list[dict]` and call it from every render pass. After source/coordinate validation its atomic mapping core is:

```python
rows = []
for candidate in candidates:
    mapped = []
    for support in candidate.supports:
        ref = next((ref for ref, unit in references.items()
                    if (unit.evidence_id, unit.version, unit.content_hash,
                        unit.start, unit.end, unit.text) ==
                       (support.evidence_id, support.version, support.content_hash,
                        support.start, support.end, support.quote)), None)
        if ref is None:
            break
        mapped.append({"ref": ref})
    if candidate.supports and len(mapped) == len(candidate.supports):
        rows.append({"claim": candidate.claim, "confidence": candidate.confidence,
                     "supports": mapped})
return rows
```

- [ ] Collect candidates from both topic_outcomes and researcher_outcomes in run_evidence_evaluation; pass them to the view, but keep `normalize_reference_findings(assessment.findings, view.references)` as the only path into global findings. Include outcome diagnostics in existing diagnostic_gaps. The evaluator can reject an unsupported candidate or output a narrower supported claim; branch notes must never directly satisfy coverage.
- [ ] GREEN tests: accepted-first, overlapping quotes/true overflow, ninth source competition, all supports visible or no claim, token overflow/no hidden p ref, absent candidates/old outcome defaults, foreign source/hash mismatch, conflicting candidates, and stale source between recording and evaluation. Run `.venv/Scripts/python.exe -m pytest tests/strategies/test_candidate_materials.py tests/integration/test_grounded_handoff_modes.py tests/strategies/test_reference_materials.py tests/strategies/test_reference_evaluation.py tests/tools/test_evidence_units.py tests/tools/test_support_budget.py tests/integration/test_support_budget_consumers.py -q`. Review and commit only newly created tests plus plan after checking staged contents.

## Task 5: Complete answer obligations and targeted supplement behavior

**Files:** Modify strategies/planning.py, shared evidence_evaluation.py instruction and harness/prompts.py/tool descriptions. Create tests/strategies/test_grounded_research_contract.py; extend tests/integration/test_grounded_handoff_modes.py. Consumes existing requirements/target IDs/gaps; produces shared prompt behavior, no new planner DTO or routing service.

- [ ] Capture actual planner prompts for all modes with run_planner/PLANNERS from tests/strategies/test_minimal_planning_contract.py. Check shared wording explicitly requires operations, necessary inputs, conditions and replay risks when the user's question needs them; comparison questions retain requested dimensions, not mandatory procedural fields. Ensure task and constraints stay present and requirements do not become a generic topic label.

The focused contract assertion is:

```python
for rule in ("必要输入", "适用条件", "完整回答原问题", "不臆造"):
    assert rule in delivered_planner_prompt
assert "record_findings" in delivered_researcher_prompt
assert "候选" in delivered_evaluator_prompt
assert "子义务" in delivered_evaluator_prompt
```

Obtain delivered prompts through real nodes; do not equate this test with semantic success. Use a generic operation whose accepted source requires both an action and a context parameter; script evaluator to reject a candidate missing the parameter, assert actual routing selects the missing target and permits read of the existing authorized source before acquiring another URL.

- [ ] Run focused tests and observe missing-contract/incorrect-handoff assertions. Add concise shared instructions: branch queries are self-contained subquestions; read known sources for concrete missing obligations; use find for actual source terms; record meaningful progress in batches; a no-hit result is not proof of absence. Preserve prior minimal query/planning/todo rules, no duplicate todos without progress.
- [ ] Evaluator prompt requires checking every obligation in each requirement against actual visible original text, not candidate confidence or citation validity. If partially answered, report a specific missing action/input/condition rather than mark coarse topic covered. Keep semantic judgment model-based and existing structural covered checks unchanged. Writer receives no candidate bypass; preserve its existing honest gap explanation.
- [ ] GREEN tests for a supported complete answer, partial procedure with valid citations, conflicts, invalid target IDs, legal mixed supplement goals, no-progress termination and all three modes' recovery. Run `.venv/Scripts/python.exe -m pytest tests/strategies/test_grounded_research_contract.py tests/integration/test_grounded_handoff_modes.py tests/strategies/test_minimal_planning_contract.py tests/strategies/test_gap_target_contract.py tests/harness/test_todo_progress_contract.py tests/responses/test_evidence_gap_causes.py tests/responses/test_supported_findings.py -q`. Record limitations: scripted semantic decisions are wiring tests, not measured accuracy.

## Task 6: Reuse the existing evaluator for actual live tools and local-tool accounting

**Files:** Modify eval/env.py, runner.py, trajectory.py and experiment.py; create eval/live.py, tests/eval/test_live_environment.py and tests/eval/test_local_tool_accounting.py. Do not modify evaluation/ragas_quality.py or metric/quality-input semantics. This task is verification plumbing, not a second research architecture.

**Interfaces:**

- build_eval_context accepts `corpus: Corpus | None` plus paired optional `search`/`fetcher` objects; default frozen behavior unchanged. Both adapters are required for corpus=None; prohibit mixed adapters and fault injection on live mode. Search supplies async search(query), fetcher supplies async fetch(url).
- run_matrix accepts `corpus: Corpus | None` and optional `environment_factory`; absent factory retains build_eval_context. Supplied factory gets the existing model/run/limits/memory/response kwargs and returns EvalEnvironment. Reject corpus=None without an explicit live factory.
- build_manifest accepts corpus=None only with an explicit non-secret live_retrieval identity. Live corpus_sha256=null, tools_backend=live_web, retrieval config recorded; frozen default output fields/meaning unchanged. Live documents are snapshotted by existing _capture_evidence, not preloaded gold documents.
- `python -m deeptrace.eval.live --dataset PATH --out PATH --run-prefix NAME` runs exactly one question, three modes once, fixed approved live limits. It uses Settings.from_env, build_real_model_factory, run_matrix, ExperimentStore, original quality_eval schema and isolated scorer. No --resume, implicit corpus, baseline, unlimited run or new dependency.

- [ ] Write RED tests: fake adapter objects must be used instead of CorpusSearch/CorpusFetcher; no adapters with corpus=None is rejected; one adapter is rejected; fake live traffic still passes real Gateway grants/budget/ledger, raw source snapshot and model telemetry. Check no EvalQuestion.gold_answer/gold_urls enter model or search inputs. Existing CLI and scripted corpus tests must stay offline.
- [ ] Add minimal dependency injection, factoring only the adapter-selection block out of build_eval_context. For live use actual UTC clock; for frozen retain FIXED_NOW. The live factory's adapter code is:

```python
class LiveSearch:
    def __init__(self, settings):
        self.context = ToolContext(tavily=TavilyClient(api_key=settings.tavily_api_key))

    async def search(self, query):
        return await asyncio.to_thread(search_web, self.context, query)

fetcher = AsyncWebFetcher(
    min_chars=settings.min_extracted_chars,
    min_tokens=settings.min_extracted_tokens,
    max_page_chars=settings.max_page_chars,
    allow_benchmark_dns_proxy=settings.allow_benchmark_dns_proxy,
)
```

The setting names above were verified in application/assembly.py and config/settings.py. Do not silently use another extractor, increase max_page_chars, weaken SSRF/DNS policy or bootstrap browser installation. Own the fetcher in the live CLI's async lifetime and always call await fetcher.aclose() in finally, including failed runs.

- [ ] In RecordingEventSink route agent.local_tool into a bounded TrajectoryRecorder local-tool collection; snapshot it even if the terminal tool has no following model turn. RunRecord.tool_calls remains Gateway calls. Add counts under usage.agent_tools without overwriting Provider usage: gateway, record_findings, write_todos and total Agent-requested calls. Count skipped/failed attempts separately from committed notes; mark missing observations unknown rather than success or zero. Test that stop-after-record captures local success and that an event sink failure never changes runtime outcome.
- [ ] Implement live CLI preflight before creating paid models: one question, explicit credentials present (boolean check only), modes fixed, memory off, outputs absent, approved ceilings and source/retrieval identity present. Use original quality export `{schema_version:2, identity_sha256, manifest, samples:[{record, reference}]}`; gold is attached only after research. Refuse a non-live backend and document live corpus irreproducibility despite retained raw pages. Do not output env secrets.
- [ ] GREEN commands: `.venv/Scripts/python.exe -m pytest tests/eval/test_live_environment.py tests/eval/test_local_tool_accounting.py tests/eval/test_real_factory.py tests/eval/test_trajectory.py tests/eval/test_experiment.py tests/eval/test_experiment_runner.py tests/eval/test_experiment_cli.py tests/eval/test_no_oracle_leakage.py -q`; `.venv/Scripts/python.exe -m deeptrace.eval.live --help` must not make network calls. Existing regression paths were checked with rg --files tests/eval.

## Task 7: Full regression, review and preregistration

**Files:** Create docs/evaluation/grounded-handoff-validation-20261003.md and tmp/grounded-handoff-preflight.py; update only this plan. Existing tmp audit helpers are references, not proof that new multi-stage note flows work.

- [ ] Run full regression from backend, without invoking real markers:

```powershell
.venv/Scripts/python.exe -m pytest -m "not real"
.venv-ragas/Scripts/python.exe -m pytest evaluation/tests -q
```

Use the existing Ruff invocation route (uvx ruff if absent in the venv) on this task's changed source/tests; do not upgrade project or scorer dependencies. Review with code-review-and-quality across correctness, readability, architecture, security and performance. Resolve blockers with systematic-debugging and fresh RED tests, not test weakening.

- [ ] Verify Answer and Report actual Writer inputs still contain only global accepted claims and full supports; old v2/v3 completed outputs work, old prohibited continuation remains prohibited, no empty-support fake completion. Reuse tests/integration/test_support_budget_consumers.py and add candidate-not-accepted Writer regression to test_grounded_handoff_modes.py.
- [ ] Create the validation report with old P&E F1=.563333/Faithfulness=1/Goal=.333333 as descriptive reference, not new baseline. Register config, dataset/corpus/scorer hashes, HEAD plus dirty source identity, provider attempt caps, prices available/unknown and limitations before research. Create fresh source/test snapshots with the preflight script after verifying all output paths absent; exclude .env, credentials, caches and old runs.
- [ ] Register live-assets/questions.jsonl in tmp/grounded-handoff-live-assets-20261003 with one public official-documentation question about Python3.11 asyncio.TaskGroup versus gather under ordinary child-task failures: cancellation of sibling tasks, exception propagation and required CancelledError handling. Verify reference claims against https://docs.python.org/3.11/library/asyncio-task.html before writing gold. Freeze question/reference/URLs before paid execution; no copy of reference answer into production hints or tests. This is a new live diagnostic topic, not an independently held-out benchmark.
- [ ] Preflight script uses Path.is_dir/is_file checks, existing experiment.source_identity and hashlib for copied-file validation; prints only identities and availability, never credentials. Inspect actual Settings field names and registered CLI arguments. Verify unchanged Ragas judge/scorer configuration. If a directory already exists or settings cannot match registration, report and stop that experiment; no implicit renamed rerun or different model.
- [ ] Mark implementation tasks complete only after their tests pass, and record actual RED/GREEN counts, review type and any missing human review. Freeze source before paid calls; no production edits during either registered batch.

## Task 8: Once-only registered real verification and evidence-based handoff

**Files:** Unique tmp outputs below; the validation report and this plan. Requires Task7 complete; no new source edits. All commands from backend. Per-command exit1 with retained partials is a result, not permission to rerun.

- [ ] Research the frozen-dev matrix exactly once:

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval --model real --modes plan_execute,workflow,multi_agent --repeats 1 --response-mode answer --response-max-chars 2000 --max-model-calls 40 --max-tool-calls 24 --max-provider-attempts 80 --max-batch-model-calls 360 --max-batch-provider-attempts 720 --agent-iterations 12 --max-output-tokens 4096 --run-timeout 360 --dataset ../tmp/evidence-loop-real-20261002-assets/questions.jsonl --corpus ../tmp/evidence-loop-real-20261002-assets/corpus.jsonl --run-prefix grounded-handoff-real-answer-20261003 --out ../tmp/grounded-handoff-real-answer-20261003
```

- [ ] Score it once and run strict comparison without adding baseline pairs:

```powershell
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/grounded-handoff-real-answer-20261003/quality_eval.json --out ../tmp/grounded-handoff-real-answer-20261003-quality --max-provider-attempts 144 --env-file .env
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval.compare_cli --input ../tmp/grounded-handoff-real-answer-20261003/quality_eval.json --scores ../tmp/grounded-handoff-real-answer-20261003-quality/quality_scores.json --metadata ../tmp/evidence-loop-real-20261002-assets/analysis-card.json --out ../tmp/grounded-handoff-real-answer-20261003-comparison
```

- [ ] Run actual live search/fetch/read/model chain exactly once (CLI enforces Task6's fixed limits), then score once:

```powershell
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval.live --dataset ../tmp/grounded-handoff-live-assets-20261003/questions.jsonl --run-prefix grounded-handoff-live-answer-20261003 --out ../tmp/grounded-handoff-live-answer-20261003
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/grounded-handoff-live-answer-20261003/quality_eval.json --out ../tmp/grounded-handoff-live-answer-20261003-quality --max-provider-attempts 48 --env-file .env
```

If live search/fetch fails, preserve all records and label live validation not passed. Do not fall back to local corpus, inject gold URLs as prior fetch grants or relax fetch security. Stop/back off on quota/rate-limit failures; do not create new output directories to repeat the batch.

- [ ] Audit each stage from actual per-call frames, not a union of everything ever read: Gateway raw result, actual numbered researcher tool preview, successful local note, actual evaluator candidate/support input, normalized global accepted finding, actual final Writer input and output citation. Handle multiple evaluator calls and branches explicitly; the older single-frame support-budget audit assumption is insufficient. Validate coordinates/hash/quote, scoped references, atomic omission and termination reasons. Audit the unchanged frozen source after both batches.
- [ ] Report all9 dev and3 live statuses including partial/failed, scores with valid denominators/NA/error, primary P&E and both secondary modes, Provider/input-output tokens, Gateway versus local counts, known/unknown cost, visibility failures and actual end-to-end operations. Do not aggregate live/frozen scores, mix Answer/Report, impute missing judge values, or relabel partial with nonempty text as completed.
- [ ] Manually inspect live answers against preregistered official reference obligations and every cited page; label this agent review, not independent human blind review. Faithfulness=1 and successful structured references are not completeness guarantees. State exactly which mode passed obligations; no production-readiness claim based on one live question.
- [ ] Update validation report and task checkboxes with observed evidence; if quality does not improve, say so and distinguish acquisition, note omission, semantic assessment and judge disagreement. Commit only new documentation/self-owned task artifacts with verified staged files; hand off result, remaining failures and runnable source snapshot identity.

## Plan self-review and execution handoff

- [x] Spec coverage mapped to Tasks1–8: acquisition, bounded references, records/transaction boundaries/context, final handoff, completion obligations, counts/live plumbing, compatibility/full tests, two registered experiments.
- [x] Interfaces and defaults explicit; no harness→strategy dependency, model-issued grants, local notes→global coverage bypass or new state service.
- [x] Boundary tests and real commands supplied; unknown/source/gold/price distinctions retained. Runtime code never hardcodes the known dev's missing API.
- [x] Task-start and paid-run snapshots required; existing dirty files not swept into commits. The written plan is not evidence that tests or APIs have run.
- [ ] Execution method selected. Preferred fallback here: inline TDD with the available skills, checkpointing progress between tasks; the unavailable execution skills must not be claimed as used.

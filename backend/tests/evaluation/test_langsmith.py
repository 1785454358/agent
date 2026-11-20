import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langsmith import Client, aevaluate, tracing_context
from langsmith.run_helpers import get_current_run_tree
from langsmith.run_trees import RunTree
from langsmith.schemas import Example

from deeptrace.evaluation.datasets import load_examples, sync_dataset
from deeptrace.evaluation.evaluators import execution_completed, evidence_sufficient, tool_success_rate
from deeptrace.evaluation.runner import make_target
from deeptrace.observability.langsmith import application_inputs, application_outputs


@pytest.mark.parametrize("mode", ["workflow", "auto"])
def test_application_trace_excludes_runtime_objects_and_credentials(mode):
    from deeptrace.application.research import ApplicationResearchRequest
    request = ApplicationResearchRequest(question="question", run_id="run", thread_id="thread", mode=mode)
    assert application_inputs({"self": object(), "context": "secret", "request": request}) == {
        "question": "question", "run_id": "run", "thread_id": "thread", "mode": mode
    }


@pytest.mark.asyncio
async def test_runtime_shutdown_flushes_sdk_queue(monkeypatch):
    from deeptrace.application.assembly import HarnessRuntimeBundle
    import langsmith.run_trees
    calls = []
    monkeypatch.setattr(langsmith.run_trees, "get_cached_client",
        lambda: SimpleNamespace(flush=lambda **kwargs: calls.append(kwargs)))
    bundle = HarnessRuntimeBundle(object(), lambda run_id: None, [], lambda run_id: None)
    with tracing_context(enabled=True):
        await bundle.aclose()
    assert calls == [{"timeout": 10}]


def test_dataset_rejects_duplicate_ids_before_writing(tmp_path):
    record = {"inputs": {"question": "q"}, "outputs": {"answer": "a"}, "metadata": {"id": "one"}}
    path = tmp_path / "data.jsonl"
    path.write_text("\n".join([json.dumps(record)] * 2))
    with pytest.raises(ValueError, match="duplicate"):
        load_examples(path)


def test_sync_is_idempotent_and_preserves_unrelated_examples():
    class Client:
        def __init__(self):
            self.rows = {}
            self.created = 0
        def has_dataset(self, **kwargs): return True
        def read_dataset(self, **kwargs): return SimpleNamespace(id=uuid4())
        def list_examples(self, **kwargs): return list(self.rows.values())
        def create_examples(self, **kwargs):
            for row in kwargs["examples"]:
                self.rows[str(row["id"])] = SimpleNamespace(**row)
                self.created += 1
        def update_example(self, identity, **kwargs):
            self.rows[str(identity)] = SimpleNamespace(id=identity, **kwargs)
    client = Client()
    record = {"inputs": {"question": "q"}, "outputs": {"answer": "a"}, "metadata": {"id": "one"}}
    sync_dataset(client, "test", [record])
    record["outputs"]["answer"] = "updated"
    sync_dataset(client, "test", [record])
    assert client.created == 1
    assert next(iter(client.rows.values())).outputs == {"answer": "updated"}


@pytest.mark.asyncio
async def test_native_sdk_evaluation_keeps_partial_distinct_from_success():
    import requests
    from requests.adapters import BaseAdapter
    class OfflineAdapter(BaseAdapter):
        def send(self, request, **kwargs):
            response = requests.Response()
            response.status_code = 200
            response._content = b'{}'
            response.request = request
            response.url = request.url
            return response
        def close(self): pass
    session = requests.Session()
    client = Client(api_key="offline-test", session=session, auto_batch_tracing=False)
    session.mount("https://", OfflineAdapter())
    async def target(inputs):
        return {"status": "partial", "research_sufficiency": "insufficient", "tool_calls": 2, "tool_successes": 1}
    example = Example(id=uuid4(), dataset_id=uuid4(), inputs={"question": "q"}, outputs={"answer": "reference"})
    results = await aevaluate(target, data=[example], evaluators=[execution_completed, evidence_sufficient, tool_success_rate], upload_results=False, client=client)
    rows = [row async for row in results]
    scores = {item.key: item.score for item in rows[0]["evaluation_results"]["results"]}
    assert scores == {"execution_completed": 0, "evidence_sufficient": 0, "tool_success_rate": 0.5}
    client.close()


@pytest.mark.asyncio
async def test_target_isolates_identity_hides_references_and_releases_on_cancellation():
    import asyncio
    from deeptrace.harness.context import HarnessContext
    calls, released = [], []
    async def invoke(request, *, config, context):
        calls.append((request, config, context))
        assert context.memory_store is context.memory_retriever is None
        raise asyncio.CancelledError()
    context = HarnessContext("user", "workspace", object(), object(), object(), object(), object(), memory_store=object())
    bundle = SimpleNamespace(service=SimpleNamespace(invoke=invoke), context_factory=lambda run_id: context, release_run=released.append)
    target = make_target(bundle, "workflow")
    for _ in range(2):
        with pytest.raises(asyncio.CancelledError):
            await target({"question": "q", "answer": "must never reach runtime"})
    assert calls[0][0].run_id != calls[1][0].run_id
    assert calls[0][0].thread_id != calls[1][0].thread_id
    assert len(released) == 2
    assert calls[0][0].question == "q"


@pytest.mark.asyncio
async def test_application_span_uses_sdk_parent_without_serializing_context():
    from deeptrace.application.research import ResearchApplicationService, ApplicationResearchRequest
    class Graph:
        async def ainvoke(self, state, **kwargs):
            tree = get_current_run_tree()
            assert tree.parent_run_id == parent.id
            raise ValueError("graph failed")
    parent = RunTree(name="experiment", run_type="chain", inputs={})
    request = ApplicationResearchRequest(run_id="r", thread_id="t", question="q", mode="workflow")
    with tracing_context(parent=parent, enabled="local"):
        with pytest.raises(ValueError, match="graph failed"):
            await ResearchApplicationService(Graph()).invoke(request, config={"configurable": {"thread_id": "t"}}, context=object())
    child = parent.child_runs[0]
    assert child.inputs["question"] == "q"
    assert "context" not in child.inputs
    assert child.error


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("enforce", [False, True])
async def test_experiment_closes_runtime_and_reports_target_errors(monkeypatch, failed, enforce):
    from unittest.mock import AsyncMock
    from deeptrace.evaluation import __main__ as cli
    from deeptrace.application import assembly
    from deeptrace.config import Settings
    settings = Settings("private-key", "https://provider.invalid", "model", "private-search", memory_retrieval="lexical")
    monkeypatch.setattr(Settings, "from_env", lambda: settings)
    bundle = SimpleNamespace(aclose=AsyncMock())
    monkeypatch.setattr(assembly, "build_harness_runtime", lambda *a, **k: bundle)
    class Results:
        experiment_name, url = "test", "https://smith.langchain.com/test"
        async def __aiter__(self):
            yield {"run": SimpleNamespace(error="failure" if failed else None, outputs={"status": "failed" if failed else "partial"}),
                   "evaluation_results":{"results":[SimpleNamespace(key='task_accepted_v4',score=0)]}}
    async def evaluate(target, **kwargs):
        assert "private-key" not in json.dumps(kwargs["metadata"])
        assert kwargs["max_concurrency"] == 1
        assert [e.metadata["id"] for e in kwargs["data"]] == ["answerable-dev-01"]
        return Results()
    monkeypatch.setattr(cli, "aevaluate", evaluate)
    client = SimpleNamespace(list_examples=lambda **kwargs: [
        SimpleNamespace(metadata={"id": "negative-test-01"}),
        SimpleNamespace(metadata={"id": "answerable-dev-01"})])
    args = cli.parser().parse_args(["run", "--max-examples", "1"] + (['--require-acceptance','--judge'] if enforce else []))
    if failed or enforce:
        with pytest.raises(RuntimeError, match="failed|acceptance"):
            await cli.run_experiment(args, client)
    else:
        await cli.run_experiment(args, client)
    bundle.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_case_selection_is_stable_and_can_reproduce_negative_case(monkeypatch):
    from deeptrace.evaluation import __main__ as cli
    from deeptrace.config import Settings
    examples = [SimpleNamespace(metadata={"id": identity}) for identity in ["negative-test-01", "answerable-dev-01"]]
    def list_examples(**kwargs):
        assert kwargs.get("limit") is None
        assert kwargs["metadata"] == {"id": "negative-test-01"}
        return [e for e in examples if not kwargs.get("metadata") or e.metadata == kwargs["metadata"]]
    def settings():
        # Selection happens before runtime construction or model credentials.
        raise RuntimeError("selected")
    monkeypatch.setattr(Settings, "from_env", settings)
    client = SimpleNamespace(list_examples=list_examples)
    args = cli.parser().parse_args(["run", "--case-id", "negative-test-01", "--max-examples", "1"])
    with pytest.raises(RuntimeError, match="selected"):
        await cli.run_experiment(args, client)


@pytest.mark.asyncio
@pytest.mark.parametrize("environment,override,expected", [
    ("legacy", "controller", "controller"),
    ("controller", "legacy", "legacy"),
    ("controller", None, "controller"),
    ("legacy", None, "legacy"),
])
async def test_experiment_records_and_assembles_the_selected_orchestrator(
    monkeypatch, environment, override, expected,
):
    from unittest.mock import AsyncMock
    from deeptrace.application import assembly
    from deeptrace.config import Settings
    from deeptrace.evaluation import __main__ as cli
    settings = Settings("test", "https://provider.invalid", "model", "test",
                        memory_retrieval="lexical", research_orchestrator=environment)
    monkeypatch.setattr(Settings, "from_env", lambda: settings)
    assembled, experiments = [], []
    bundle = SimpleNamespace(aclose=AsyncMock())

    def build_runtime(settings, **kwargs):
        assembled.append(settings.research_orchestrator)
        return bundle

    class Results:
        experiment_name, url = "test", "https://smith.langchain.com/test"

        async def __aiter__(self):
            for row in ():
                yield row

    async def evaluate(target, **kwargs):
        experiments.append(kwargs)
        return Results()

    monkeypatch.setattr(assembly, "build_harness_runtime", build_runtime)
    monkeypatch.setattr(cli, "aevaluate", evaluate)
    client = SimpleNamespace(list_examples=lambda **kwargs: [SimpleNamespace(
        metadata={"id": "one"}, inputs={"question": "q"})])
    arguments = ["run", "--dataset-version", "fixed-version"]
    if override is not None:
        arguments += ["--orchestrator", override]
    args = cli.parser().parse_args(arguments)
    await cli.run_experiment(args, client)
    assert assembled == [expected]
    assert experiments[0]["metadata"]["research_orchestrator"] == expected
    assert experiments[0]["metadata"]["dataset_version"] == "fixed-version"
    assert experiments[0]["experiment_prefix"] == f"deeptrace-{expected}-workflow"


def test_experiment_rejects_an_unknown_orchestrator():
    from deeptrace.evaluation import __main__ as cli
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["run", "--orchestrator", "unknown"])


@pytest.mark.asyncio
async def test_target_rejects_corrupted_corpus_before_dispatch_and_releases():
    released = []
    bundle = SimpleNamespace(context_factory=lambda run_id: object(), release_run=released.append)
    with pytest.raises(ValueError, match="hash"):
        await make_target(bundle, "workflow")({"question": "q", "documents": [
            {"url": "https://example.com/doc", "title": "doc", "body": "tampered", "sha256": "bad"}]})
    assert len(released) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('scope,grounded,accepted', [(True,0.9,True),(False,0.9,False),(True,0.4,False)])
async def test_acceptance_requires_grounded_answer_and_scope_even_for_high_correctness(scope, grounded, accepted):
    from deeptrace.evaluation.evaluators import answer_correctness
    class Model:
        def with_structured_output(self, schema):
            self.schema = schema
            return self
        async def ainvoke(self, messages):
            return SimpleNamespace(score=0.9, groundedness=grounded, reason='test')
    result = await answer_correctness(Model())({'question':'q'},
        {'answer':'bounded refusal', 'status':'partial', 'source_scope_ok':scope,
         'budget_compliant':True, 'evidence_excerpts':[]}, {'answer':'reference'})
    scores = {item['key']:item['score'] for item in result['results']}
    assert scores['task_accepted'] == accepted

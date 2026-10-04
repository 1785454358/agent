import copy
import hashlib
import json

import pytest

from deeptrace.domain import ResearchMode
from deeptrace.eval.assets import load_benchmark
from deeptrace.eval.runner import run_matrix
from deeptrace.eval.scripted import ScriptedResearchModel
from tests.eval.test_assets import bundle_fixture, save


async def sample(tmp_path, *, long=False):
    path, payload = bundle_fixture(tmp_path)
    marker = "CHECKPOINT_TAIL_MARKER_917."
    body = (
        "Checkpoint saves graph state.\n"
        + ("unrelated padding text.\n" * 2000 if long else "")
        + marker
    )
    (tmp_path / "dev.mdx").write_text(body, encoding="utf-8", newline="\n")
    payload["sources"][0]["sha256"] = hashlib.sha256(body.encode()).hexdigest()
    ref = payload["tasks"][0]["references"][0]
    ref.update(
        quote=marker, start_line=2002 if long else 2, end_line=2002 if long else 2
    )
    save(path, payload)
    assets = load_benchmark(path, split="dev")
    records = await run_matrix(
        assets.questions,
        assets.corpus,
        model_factory=ScriptedResearchModel,
        modes=(ResearchMode.WORKFLOW,),
        include_baseline=True,
    )
    return assets, next(r for r in records if r.mode == "baseline"), marker


@pytest.mark.asyncio
async def test_actual_tail_is_retained_in_evidence_but_loss_is_reported(tmp_path):
    from deeptrace.eval import context_audit

    assets, record, marker = await sample(tmp_path, long=True)
    assert marker in record.evidence[0]["body"]
    result = context_audit.analyze_delivery(assets, [record])
    assert result["counts"]["selected_not_visible"] == 1
    assert result["counts"]["visible"] == 0
    assert result["rows"][0]["stored"] is True
    assert marker not in json.dumps(
        record.trajectory["model_messages"], ensure_ascii=False
    )


@pytest.mark.asyncio
async def test_actual_short_span_is_visible_to_responder(tmp_path):
    from deeptrace.eval import context_audit

    assets, record, marker = await sample(tmp_path)
    result = context_audit.analyze_delivery(assets, [record])
    assert result["counts"]["visible"] == 1
    assert result["rows"][0]["responder_turns_with_span"] == [0]
    assert marker in str(record.trajectory["model_messages"])


@pytest.mark.asyncio
async def test_missing_fetch_and_nonselection_are_not_excerpt_loss(tmp_path):
    from deeptrace.eval import context_audit

    assets, record, _ = await sample(tmp_path)
    absent = record.model_copy(deep=True)
    absent.evidence = []
    assert (
        context_audit.analyze_delivery(assets, [absent])["counts"]["not_fetched"] == 1
    )
    unselected = record.model_copy(deep=True)
    unselected.evidence[0]["selected_for_outcome"] = False
    assert (
        context_audit.analyze_delivery(assets, [unselected])["counts"][
            "stored_not_selected"
        ]
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["body", "question", "trace", "artifact", "duplicate"]
)
async def test_audit_refuses_unverifiable_records(tmp_path, mutation):
    from deeptrace.eval import context_audit

    assets, record, _ = await sample(tmp_path)
    changed = copy.deepcopy(record)
    if mutation == "body":
        changed.evidence[0]["body"] += "changed"
    elif mutation == "question":
        changed.question = "different input"
    elif mutation == "trace":
        changed.trajectory.pop("model_messages")
    elif mutation == "artifact":
        changed.artifact_errors = ["read_failed"]
    records = [changed, changed] if mutation == "duplicate" else [changed]
    with pytest.raises(ValueError):
        context_audit.analyze_delivery(assets, records)


def test_context_audit_cli_rejects_test_ids_before_output(tmp_path):
    from deeptrace.eval import context_audit

    with pytest.raises(SystemExit) as exc:
        context_audit.main(
            ["--question-id", "single_hop-test-01", "--out", str(tmp_path / "run")]
        )
    assert exc.value.code == 2
    assert not (tmp_path / "run").exists()


def test_context_audit_cli_saves_raw_records_and_refuses_overwrite(tmp_path):
    from deeptrace.eval import context_audit

    path, _ = bundle_fixture(tmp_path)
    out = tmp_path / "run"
    args = ["--bundle", str(path), "--question-id", "dev", "--out", str(out)]
    assert context_audit.main(args) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))[
        "manifest"
    ]
    assert manifest["diagnostic"]["question_ids"] == ["dev"]
    assert manifest["model"]["kind"] == "scripted"
    audit = json.loads((out / "delivery.json").read_text(encoding="utf-8"))
    assert audit["runs"] == 2
    assert audit["counts"]["visible"] == 2
    raw = (out / "records.json").read_bytes()
    with pytest.raises(SystemExit) as exc:
        context_audit.main(args)
    assert exc.value.code == 2
    assert (out / "records.json").read_bytes() == raw

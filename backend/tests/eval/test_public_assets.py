import json
import shutil

import pytest

from deeptrace.eval import public_assets


def test_original_public_tasks_preserved_without_reference_answers():
    subset = public_assets.load_public_selection(public_assets.default_selection_path())
    assert [q["id"] for q in subset.tasks] == [17, 19, 20, 66, 68]
    assert (
        subset.tasks[1]["prompt"]
        == "prometheus 的高流失率会造成什么影响，有什么系统的方案可以解决？各家云厂商有没有现有方案？"
    )
    assert (
        subset.tasks[2]["prompt"]
        == "研究下Anthropic最新发布的Streamable HTTP的工程中的具体实现方案"
    )
    assert [q["language"] for q in subset.tasks] == ["zh", "zh", "zh", "en", "en"]
    assert all(set(q) == {"id", "topic", "language", "prompt"} for q in subset.tasks)
    assert subset.manifest.live_execution_supported is False
    assert subset.manifest.reference_answers_available is False


@pytest.mark.parametrize(
    "mutation",
    ["raw", "license", "order", "quota", "duplicate", "reference_claim", "path"],
)
def test_public_selection_rejects_corruption_or_misleading_claims(tmp_path, mutation):
    path = public_assets.default_selection_path()
    shutil.copytree(path.parent, tmp_path / "public")
    local = tmp_path / "public/selection.json"
    payload = json.loads(local.read_text(encoding="utf-8"))
    if mutation == "raw":
        (local.parent / payload["query_path"]).write_text("{}")
    elif mutation == "license":
        payload["license_sha256"] = "0" * 64
    elif mutation == "order":
        payload["selected_ids"].reverse()
    elif mutation == "quota":
        payload["selected_ids"] = [17, 19, 20, 66, 69]
    elif mutation == "duplicate":
        payload["candidates"].append(payload["candidates"][0])
    elif mutation == "reference_claim":
        payload["reference_answers_available"] = True
    else:
        payload["query_path"] = "../outside.jsonl"
    local.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        public_assets.load_public_selection(local)


def test_public_audit_cannot_be_mistaken_for_official_score(tmp_path):
    assert public_assets.main(["--out", str(tmp_path)]) == 0
    audit = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
    assert audit["tasks"] == 5
    assert audit["factual_metric_applicability"] == "not_applicable_no_references"
    assert audit["official_scoring"] is False
    assert audit["executed"] is False
    assert "quality_scores" not in audit

"""Catch corrupt source provenance and scoring-side leakage before execution."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from deeptrace.eval import assets


def test_frozen_upstream_bytes_are_not_rewritten_by_git_checkout():
    root = Path(__file__).resolve().parents[3]
    if not shutil.which("git") or not (root / ".git").exists():
        pytest.skip("checkout byte-preservation check requires Git worktree")
    paths = [
        "backend/src/deeptrace/eval/data/benchmarks/research-v1/upstream/langgraph-checkpointers.mdx",
        "backend/src/deeptrace/eval/data/benchmarks/research-v1/LICENSE.txt",
        "backend/src/deeptrace/eval/data/public/drb-v1/upstream/query.jsonl",
        "backend/src/deeptrace/eval/data/public/drb-v1/LICENSE.txt",
    ]
    result = subprocess.run(
        ["git", "check-attr", "text", "--", *paths],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert all(line.endswith(": text: unset") for line in result.stdout.splitlines())


def bundle_fixture(tmp_path):
    (tmp_path / "LICENSE.txt").write_text(
        "MIT License\nCopyright Example\n", encoding="utf-8"
    )
    rows = []
    for split, body in (
        ("dev", "Checkpoints save graph state."),
        ("test", "Tools can inject runtime context."),
    ):
        path = tmp_path / f"{split}.mdx"
        path.write_text(body, encoding="utf-8")
        rows.append(
            dict(
                id=split,
                path=f"{split}.mdx",
                url=f"https://github.com/example/docs/blob/{'a' * 40}/{split}.mdx",
                title=split,
                publisher="Example",
                repo="example/docs",
                commit="a" * 40,
                upstream_path=f"{split}.mdx",
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                source_group=split,
                license="MIT",
                license_path="LICENSE.txt",
                license_sha256=hashlib.sha256(
                    (tmp_path / "LICENSE.txt").read_bytes()
                ).hexdigest(),
                retrieved_at="2026-10-02T00:00:00Z",
            )
        )
    tasks = [
        dict(
            id=split,
            split=split,
            category="single_hop",
            question="How is state saved?"
            if split == "dev"
            else "What do tools inject?",
            gold_answer="gold_canary_14a",
            success_requirements=["score_only_requirement"],
            uncertainty_policy="state unsupported claims",
            hops=1,
            source_ids=[split],
            references=[
                dict(
                    claim="gold_canary_14a",
                    kind="fact",
                    source_id=split,
                    start_line=1,
                    end_line=1,
                    quote=body,
                )
            ],
            review=dict(
                source_verified=True,
                human_reviewed=False,
                reviewer_kind="agent_source_check",
                reviewed_at="2026-10-02T00:00:00Z",
                note="Source checked, not human gold.",
            ),
        )
        for split, body in (
            ("dev", "Checkpoints save graph state."),
            ("test", "Tools can inject runtime context."),
        )
    ]
    payload = dict(
        schema_version=1,
        dataset="fixture",
        data_kind="real_source",
        sources=rows,
        tasks=tasks,
        expected_counts={"single_hop": {"dev": 1, "test": 1}},
        limitations=["Fixture, not benchmark evidence."],
    )
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, payload


def save(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_projection_keeps_original_body_and_excludes_annotations(tmp_path):
    path, _ = bundle_fixture(tmp_path)
    result = assets.load_benchmark(path, split="dev")
    assert result.questions[0].question == "How is state saved?"
    assert result.corpus.documents()[0].body == "Checkpoints save graph state."
    assert result.corpus.documents()[0].tags == []
    assert "gold_canary_14a" not in str(result.corpus.documents())
    assert "score_only_requirement" not in str(result.corpus.documents())
    card = result.analysis_card()
    assert card["questions"]["dev"]["split"] == "dev"
    assert result.review_counts == {
        "source_verified": 2,
        "human_reviewed": 0,
        "tasks": 2,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "changed_source",
        "bad_quote",
        "escape",
        "duplicate",
        "split_leak",
        "counts",
        "license_hash",
        "unknown_field",
        "unverified",
        "human_claim",
        "url_pin",
        "range",
        "naive_time",
    ],
)
def test_invalid_bundle_is_rejected_before_projection(tmp_path, mutation):
    path, payload = bundle_fixture(tmp_path)
    if mutation == "changed_source":
        (tmp_path / "dev.mdx").write_text("modified")
    elif mutation == "bad_quote":
        payload["tasks"][0]["references"][0]["quote"] = "not in source"
    elif mutation == "escape":
        payload["sources"][0]["path"] = "../outside.mdx"
    elif mutation == "duplicate":
        payload["tasks"][1]["id"] = "dev"
    elif mutation == "split_leak":
        payload["sources"][1]["source_group"] = "dev"
    elif mutation == "counts":
        payload["expected_counts"]["single_hop"]["dev"] = 2
    elif mutation == "license_hash":
        payload["sources"][0]["license_sha256"] = "0" * 64
    elif mutation == "unverified":
        payload["tasks"][0]["review"]["source_verified"] = False
    elif mutation == "human_claim":
        payload["tasks"][0]["review"]["human_reviewed"] = True
    elif mutation == "url_pin":
        payload["sources"][0]["url"] = (
            "https://github.com/example/docs/blob/main/dev.mdx"
        )
    elif mutation == "range":
        payload["tasks"][0]["references"][0]["end_line"] = 100
    elif mutation == "naive_time":
        payload["sources"][0]["retrieved_at"] = "2026-10-02T00:00:00"
    else:
        payload["sources"][0]["gold_answer"] = "injection"
    save(path, payload)
    with pytest.raises(ValueError):
        assets.load_benchmark(path, split="dev")


def test_real_bundle_counts_source_checks_and_no_human_gold():
    path = assets.default_benchmark_path()
    dev, test = (assets.load_benchmark(path, split=s) for s in ("dev", "test"))
    assert len(dev.questions) == 12
    assert len(test.questions) == 18
    assert dev.bundle.expected_counts == {
        category: {"dev": 2, "test": 3}
        for category in (
            "single_hop",
            "multi_hop",
            "comparison",
            "version_boundary",
            "conflicting_evidence",
            "insufficient_evidence",
        )
    }
    assert dev.review_counts == {
        "source_verified": 30,
        "human_reviewed": 0,
        "tasks": 30,
    }
    assert len(dev.corpus.documents()) >= 3
    assert len(test.corpus.documents()) >= 3
    assert {d.url for d in dev.corpus.documents()}.isdisjoint(
        {d.url for d in test.corpus.documents()}
    )
    assert all(
        ref.kind == "scope_boundary"
        for q in dev.bundle.tasks
        if q.category == "insufficient_evidence"
        for ref in q.references
    )


def test_audit_cli_outputs_only_cards_and_validation_not_model_scores(tmp_path):
    path, _ = bundle_fixture(tmp_path)
    out = tmp_path / "audit"
    assert assets.main(["--bundle", str(path), "--out", str(out)]) == 0
    report = json.loads((out / "audit.json").read_text(encoding="utf-8"))
    assert report["source_verified"] == 2
    assert report["human_reviewed"] == 0
    assert "quality_scores" not in report
    assert (out / "analysis-test.json").exists()

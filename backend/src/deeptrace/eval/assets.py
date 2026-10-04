"""Validate frozen provenance and project a scoring-side bundle into runtime data."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeptrace.eval.artifacts import atomic_json
from deeptrace.eval.dataset import CorpusDocument, EvalQuestion
from deeptrace.eval.env import Corpus
from deeptrace.eval.trajectory import _content_hash


class AssetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _timestamp(value: str) -> str:
    if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("timezone-aware provenance time required")
    return value


class SourceAsset(AssetModel):
    id: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=1000)
    title: str = Field(min_length=1, max_length=300)
    publisher: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    upstream_path: str = Field(min_length=1, max_length=300)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_group: str = Field(min_length=1, max_length=100)
    license: Literal["MIT", "Apache-2.0"]
    license_path: str = Field(min_length=1, max_length=300)
    license_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: str

    @field_validator("retrieved_at")
    @classmethod
    def valid_time(cls, value):
        return _timestamp(value)


class ReferenceSpan(AssetModel):
    claim: str = Field(min_length=1, max_length=4000)
    kind: Literal["fact", "scope_boundary"] = "fact"
    source_id: str = Field(min_length=1, max_length=100)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=20000)


class SourceReview(AssetModel):
    source_verified: bool
    human_reviewed: bool = False
    reviewer_kind: Literal["agent_source_check", "human_source_review"]
    reviewed_at: str
    note: str = Field(min_length=1, max_length=4000)

    @field_validator("reviewed_at")
    @classmethod
    def valid_time(cls, value):
        return _timestamp(value)


class GovernedQuestion(AssetModel):
    id: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    split: Literal["dev", "test"]
    question: str = Field(min_length=1, max_length=10000)
    gold_answer: str = Field(min_length=1, max_length=10000)
    success_requirements: list[str] = Field(min_length=1, max_length=20)
    uncertainty_policy: str = Field(min_length=1, max_length=2000)
    hops: int = Field(ge=1, le=10)
    source_ids: list[str] = Field(min_length=1, max_length=20)
    references: list[ReferenceSpan] = Field(min_length=1, max_length=30)
    review: SourceReview


class BenchmarkBundle(AssetModel):
    schema_version: Literal[1]
    dataset: str = Field(min_length=1, max_length=100)
    data_kind: Literal["real_source"]
    sources: list[SourceAsset] = Field(min_length=1, max_length=100)
    tasks: list[GovernedQuestion] = Field(min_length=1, max_length=200)
    expected_counts: dict[str, dict[str, int]]
    limitations: list[str] = Field(min_length=1, max_length=30)


def default_benchmark_path() -> Path:
    return Path(__file__).parent / "data" / "benchmarks" / "research-v1" / "bundle.json"


def _verified_file(root: Path, relative: str, expected_hash: str) -> bytes:
    candidate = root / relative
    if (
        Path(relative).is_absolute()
        or candidate.is_symlink()
        or any(p.is_symlink() for p in candidate.parents)
    ):
        raise ValueError("asset path symlink or absolute path refused")
    try:
        candidate.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError("asset path escaped bundle") from exc
    if candidate.suffix not in {".mdx", ".md", ".txt", ".jsonl"}:
        raise ValueError("unsupported public source extension")
    if candidate.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("source exceeds 2 MiB")
    raw = candidate.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError("asset content hash mismatch")
    return raw


class BenchmarkAssets:
    """Validated references stay here; runtime receives only existing DTOs."""

    def __init__(self, bundle: BenchmarkBundle, texts: dict[str, str], *, split: str):
        self.bundle = bundle
        self.identity = _content_hash(bundle.model_dump(mode="json"))
        selected = [q for q in bundle.tasks if q.split == split]
        self.split = split
        sources = {s.id: s for s in bundle.sources}
        used = {source_id for q in selected for source_id in q.source_ids}
        self.questions = [
            EvalQuestion(
                id=q.id,
                question=q.question,
                gold_answer=q.gold_answer,
                gold_urls=[sources[s].url for s in q.source_ids],
                category=q.category,
                hops=q.hops,
            )
            for q in selected
        ]
        self.corpus = Corpus(
            [
                CorpusDocument(doc_id=s.id, url=s.url, title=s.title, body=texts[s.id])
                for s in bundle.sources
                if s.id in used
            ]
        )
        self.review_counts = {
            "tasks": len(bundle.tasks),
            "source_verified": sum(q.review.source_verified for q in bundle.tasks),
            "human_reviewed": sum(q.review.human_reviewed for q in bundle.tasks),
        }

    def analysis_card(self) -> dict:
        return {
            "dataset_sha256": _content_hash(
                [q.model_dump(mode="json") for q in self.questions]
            ),
            "corpus_sha256": _content_hash(
                [d.model_dump(mode="json") for d in self.corpus.documents()]
            ),
            "benchmark_identity": self.identity,
            "questions": {
                q.id: {
                    "dataset": self.bundle.dataset,
                    "split": self.split,
                    "data_kind": self.bundle.data_kind,
                    "category": q.category,
                }
                for q in self.questions
            },
        }


def load_benchmark(path: Path, *, split: str) -> BenchmarkAssets:
    if split not in {"dev", "test"}:
        raise ValueError("explicit dev/test split required")
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("bounded nonsymlink bundle required")
    bundle = BenchmarkBundle.model_validate_json(path.read_bytes())
    root = path.parent.resolve()
    sources = {s.id: s for s in bundle.sources}
    if len(sources) != len(bundle.sources) or len({q.id for q in bundle.tasks}) != len(
        bundle.tasks
    ):
        raise ValueError("duplicate asset IDs")
    if len({s.url for s in bundle.sources}) != len(bundle.sources):
        raise ValueError("duplicate source URL")
    texts = {}
    for source in bundle.sources:
        expected_url = f"https://github.com/{source.repo}/blob/{source.commit}/{source.upstream_path}"
        if source.url != expected_url:
            raise ValueError("source URL does not match pinned commit/path")
        raw = _verified_file(root, source.path, source.sha256)
        license_text = _verified_file(
            root, source.license_path, source.license_sha256
        ).decode("utf-8")
        marker = "MIT License" if source.license == "MIT" else "Apache License"
        if marker not in license_text:
            raise ValueError("license notice does not match declared license")
        texts[source.id] = raw.decode("utf-8")
    group_splits = defaultdict(set)
    counts = Counter()
    for question in bundle.tasks:
        if not question.review.source_verified or (
            question.review.human_reviewed
            != (question.review.reviewer_kind == "human_source_review")
        ):
            raise ValueError("unverified source or misrepresented human review")
        if len(question.source_ids) != len(set(question.source_ids)) or any(
            s not in sources for s in question.source_ids
        ):
            raise ValueError("invalid task source IDs")
        if set(question.source_ids) != {r.source_id for r in question.references}:
            raise ValueError("every task source must have a reference span")
        for source_id in question.source_ids:
            group_splits[sources[source_id].source_group].add(question.split)
        for reference in question.references:
            lines = texts[reference.source_id].splitlines()
            if not reference.start_line <= reference.end_line <= len(lines):
                raise ValueError("invalid source line range")
            span = "\n".join(lines[reference.start_line - 1 : reference.end_line])
            if span != reference.quote:
                raise ValueError("reference quote does not match exact source lines")
        counts[(question.category, question.split)] += 1
    if any(len(splits) != 1 for splits in group_splits.values()):
        raise ValueError("source group crosses development/test split")
    expected = Counter()
    for category, splits in bundle.expected_counts.items():
        if set(splits) != {"dev", "test"} or any(
            type(n) is not int or n < 1 for n in splits.values()
        ):
            raise ValueError("positive counts for both splits required")
        expected.update({(category, s): n for s, n in splits.items()})
    if counts != expected:
        raise ValueError("category/split counts do not match frozen allocation")
    return BenchmarkAssets(bundle, texts, split=split)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=default_benchmark_path())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        dev, test = (load_benchmark(args.bundle, split=s) for s in ("dev", "test"))
        output = args.out
        if (
            output.is_symlink()
            or any(p.is_symlink() for p in output.absolute().parents)
            or (output.exists() and any(output.iterdir()))
        ):
            raise ValueError("empty nonsymlink audit directory required")
        output.mkdir(parents=True, exist_ok=True)
        atomic_json(
            output / "audit.json",
            {
                "benchmark_identity": dev.identity,
                **dev.review_counts,
                "dev_tasks": len(dev.questions),
                "test_tasks": len(test.questions),
                "source_groups_disjoint": True,
                "references": sum(len(q.references) for q in dev.bundle.tasks),
                "limitations": dev.bundle.limitations,
            },
        )
        for data in (dev, test):
            atomic_json(output / f"analysis-{data.split}.json", data.analysis_card())
        return 0
    except (ValueError, OSError) as exc:
        parser.error(f"invalid benchmark assets: {type(exc).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())

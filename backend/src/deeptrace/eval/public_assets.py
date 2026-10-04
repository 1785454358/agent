"""Import original public questions only; not a live-web or official-score runner."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from deeptrace.eval.artifacts import atomic_json
from deeptrace.eval.assets import AssetModel, _timestamp, _verified_file
from deeptrace.eval.trajectory import _content_hash


class Candidate(AssetModel):
    id: int = Field(ge=1)
    eligible: bool
    reason: str = Field(min_length=1, max_length=2000)


class PublicSelection(AssetModel):
    schema_version: Literal[1]
    dataset: Literal["drb-v1-engineering-5"]
    repo: Literal["Ayanami0730/deep_research_bench"]
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    query_path: str
    upstream_path: Literal["data/prompt_data/query.jsonl"]
    query_url: str
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: Literal["Apache-2.0"]
    license_path: str
    license_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: str
    selection_rule: str = Field(min_length=1, max_length=4000)
    selected_ids: list[int] = Field(min_length=5, max_length=5)
    candidates: list[Candidate] = Field(min_length=5, max_length=100)
    live_execution_supported: Literal[False]
    reference_answers_available: Literal[False]
    official_scoring: Literal[False]
    limitations: list[str] = Field(min_length=1, max_length=30)

    @field_validator("retrieved_at")
    @classmethod
    def valid_time(cls, value):
        return _timestamp(value)


@dataclass(frozen=True)
class PublicSubset:
    manifest: PublicSelection
    tasks: list[dict]
    identity: str


def default_selection_path() -> Path:
    return Path(__file__).parent / "data/public/drb-v1/selection.json"


def load_public_selection(path: Path) -> PublicSubset:
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ValueError("bounded nonsymlink selection required")
    manifest = PublicSelection.model_validate_json(path.read_bytes())
    expected_url = f"https://github.com/{manifest.repo}/blob/{manifest.commit}/{manifest.upstream_path}"
    if manifest.query_url != expected_url:
        raise ValueError("query URL does not match pinned source")
    root = path.parent.resolve()
    raw = _verified_file(root, manifest.query_path, manifest.query_sha256)
    license_text = _verified_file(
        root, manifest.license_path, manifest.license_sha256
    ).decode("utf-8")
    if "Apache License" not in license_text:
        raise ValueError("Apache license notice required")
    rows = [
        json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()
    ]
    if len(rows) != 100:
        raise ValueError("expected the pinned 100-task query file")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "id",
            "topic",
            "language",
            "prompt",
        }:
            raise ValueError("original task shape required, without reference outputs")
        if type(row["id"]) is not int or row["language"] not in {"zh", "en"}:
            raise ValueError("invalid original task identity or language")
        if any(not isinstance(row[k], str) or not row[k] for k in ("topic", "prompt")):
            raise ValueError("nonempty original task text required")
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("duplicate original task IDs")
    eligible_topics = {"Software Development", "Software"}
    candidate_ids = [c.id for c in manifest.candidates]
    if len(candidate_ids) != len(set(candidate_ids)) or set(candidate_ids) != {
        r["id"] for r in rows if r["topic"] in eligible_topics
    }:
        raise ValueError(
            "eligibility review must cover all software candidates exactly once"
        )
    chosen = sorted(c.id for c in manifest.candidates if c.eligible)[:5]
    if manifest.selected_ids != chosen:
        raise ValueError("first-five eligible ID selection required")
    return PublicSubset(
        manifest,
        [by_id[i] for i in chosen],
        _content_hash(manifest.model_dump(mode="json")),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=default_selection_path())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        subset = load_public_selection(args.selection)
        out = args.out
        if (
            out.is_symlink()
            or any(p.is_symlink() for p in out.absolute().parents)
            or (out.exists() and any(out.iterdir()))
        ):
            raise ValueError("empty nonsymlink import directory required")
        out.mkdir(parents=True, exist_ok=True)
        atomic_json(out / "tasks.json", subset.tasks)
        atomic_json(
            out / "audit.json",
            {
                "identity_sha256": subset.identity,
                "tasks": len(subset.tasks),
                "selected_ids": subset.manifest.selected_ids,
                "executed": False,
                "official_scoring": False,
                "factual_metric_applicability": "not_applicable_no_references",
                "manifest": subset.manifest.model_dump(mode="json"),
            },
        )
        return 0
    except (ValueError, OSError) as exc:
        parser.error(f"invalid public assets: {type(exc).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())

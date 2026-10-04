"""Loading and validation of evaluation datasets and corpora."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, JsonValue

_DATA_DIR = Path(__file__).resolve().parent / "data"


def default_corpus_path() -> Path:
    return _DATA_DIR / "corpora" / "smoke.jsonl"


def default_dataset_path() -> Path:
    return _DATA_DIR / "datasets" / "smoke.jsonl"


class ReferenceToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    args: dict[str, JsonValue] = Field(default_factory=dict)


class EvalQuestion(BaseModel):
    """One evaluation item with a reference answer and gold evidence URLs."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    gold_answer: str = ""
    gold_urls: list[str] = Field(default_factory=list)
    category: str = "general"
    hops: int = Field(default=1, ge=1)
    reference_tool_calls: list[ReferenceToolCall] | None = None
    strict_tool_order: bool = False


class CorpusDocument(BaseModel):
    """A local document the offline search/fetch adapters serve."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str = ""
    tags: list[str] = Field(default_factory=list)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"evaluation asset not found: {path}")
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} is not valid JSON") from exc
            if not isinstance(payload, dict):
                raise TypeError(f"{path}:{line_number} must be a JSON object")
            rows.append(payload)
    return rows


def load_questions(path: Path | str) -> list[EvalQuestion]:
    questions = [EvalQuestion.model_validate(row) for row in _read_jsonl(Path(path))]
    _require_unique((item.id for item in questions), "question id", path)
    return questions


def load_corpus(path: Path | str) -> list[CorpusDocument]:
    documents = [CorpusDocument.model_validate(row) for row in _read_jsonl(Path(path))]
    _require_unique((item.doc_id for item in documents), "document id", path)
    _require_unique((item.url for item in documents), "document url", path)
    return documents


def _require_unique(values, label: str, path: Path) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{path} contains a duplicate {label}: {value}")
        seen.add(value)

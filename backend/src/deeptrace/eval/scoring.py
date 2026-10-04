"""Deterministic scoring for eval runs (no LLM judge)."""

from __future__ import annotations

from collections import Counter, defaultdict

from pydantic import BaseModel, ConfigDict, Field

from deeptrace.eval.dataset import EvalQuestion
from deeptrace.eval.runner import RunRecord
from deeptrace.tools.scraper.urls import normalize_url_before_fetch


def _normalize(url: str) -> str:
    try:
        return normalize_url_before_fetch(url)
    except ValueError:
        return url


class ModeScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    runs: int
    completed: int
    answered: int
    mean_gold_coverage: float
    mean_evidence_count: float
    citation_validity: float
    mean_executed_steps: float
    mean_tool_calls: float
    mean_model_calls: float
    mean_wall_ms: float
    mean_tool_retries: float = 0.0
    termination_reasons: dict[str, int] = Field(default_factory=dict)
    judge_runs: int = 0
    judge_attempted: int = 0
    judge_failures: int = 0
    mean_faithfulness: float | None = None
    mean_answer_correctness: float | None = None
    mean_source_coverage: float | None = None
    mean_citation_accuracy: float | None = None
    mean_coherence: float | None = None


class ScoreReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: int
    questions: int
    modes: list[ModeScore]


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _judge_mean(values: list[float]) -> float | None:
    return _mean(values) if values else None


def score_records(
    records: list[RunRecord], questions: list[EvalQuestion]
) -> ScoreReport:
    if not records:
        raise ValueError("records must not be empty")
    gold_by_question = {
        question.id: {_normalize(url) for url in question.gold_urls}
        for question in questions
    }

    grouped: dict[str, list[RunRecord]] = defaultdict(list)
    for record in records:
        grouped[record.mode].append(record)

    modes: list[ModeScore] = []
    for mode in sorted(grouped):
        rows = grouped[mode]
        coverages: list[float] = []
        evidence_counts: list[float] = []
        citation_valid: list[float] = []
        judged = [row for row in rows if row.judge is not None]
        for row in rows:
            gold = gold_by_question.get(row.question_id, set())
            fetched = {_normalize(url) for url in row.evidence_urls}
            coverages.append(len(fetched & gold) / len(gold) if gold else 0.0)
            evidence_counts.append(float(len(row.evidence_ids)))
            cited = set(row.cited_evidence_ids)
            citation_valid.append(
                1.0 if cited and cited <= set(row.evidence_ids) else 0.0
            )
        modes.append(
            ModeScore(
                mode=mode,
                runs=len(rows),
                completed=sum(1 for row in rows if row.status == "completed"),
                answered=sum(1 for row in rows if row.answered),
                mean_gold_coverage=_mean(coverages),
                mean_evidence_count=_mean(evidence_counts),
                citation_validity=_mean(citation_valid),
                mean_executed_steps=_mean([float(row.executed_steps) for row in rows]),
                mean_tool_calls=_mean([float(row.tool_calls) for row in rows]),
                mean_model_calls=_mean([float(row.model_calls) for row in rows]),
                mean_wall_ms=_mean([row.wall_ms for row in rows]),
                mean_tool_retries=_mean([float(row.tool_retries) for row in rows]),
                termination_reasons=dict(
                    sorted(Counter(row.termination_reason for row in rows).items())
                ),
                judge_runs=len(judged),
                judge_attempted=sum(row.judge_attempted for row in rows),
                judge_failures=sum(row.judge_error is not None for row in rows),
                mean_faithfulness=_judge_mean(
                    [float(r.judge.faithfulness) for r in judged]
                ),
                mean_answer_correctness=_judge_mean(
                    [float(r.judge.answer_correctness) for r in judged]
                ),
                mean_source_coverage=_judge_mean(
                    [float(r.judge.source_coverage) for r in judged]
                ),
                mean_citation_accuracy=_judge_mean(
                    [float(r.judge.citation_accuracy) for r in judged]
                ),
                mean_coherence=_judge_mean([float(r.judge.coherence) for r in judged]),
            )
        )

    return ScoreReport(runs=len(records), questions=len(questions), modes=modes)

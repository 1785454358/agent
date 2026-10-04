"""Offline, deterministic evaluation harness for the research strategies.

The package is intentionally self-contained: it reuses the production tool and
model boundaries, but swaps only the search/fetch adapters for a local corpus so
the whole matrix runs without any live API. See
``docs/evaluation/agent-benchmark-plan.md``.
"""

from deeptrace.eval.dataset import (
    CorpusDocument,
    EvalQuestion,
    default_corpus_path,
    default_dataset_path,
    load_corpus,
    load_questions,
)
from deeptrace.eval.env import (
    Corpus,
    EvalEnvironment,
    EvalFaults,
    build_eval_context,
)
from deeptrace.eval.report import render_markdown
from deeptrace.eval.runner import RunRecord, run_matrix
from deeptrace.eval.scoring import ModeScore, ScoreReport, score_records
from deeptrace.eval.scripted import ScriptedJudgeModel, ScriptedResearchModel

__all__ = [
    "Corpus",
    "CorpusDocument",
    "EvalEnvironment",
    "EvalFaults",
    "EvalQuestion",
    "ModeScore",
    "RunRecord",
    "ScoreReport",
    "ScriptedJudgeModel",
    "ScriptedResearchModel",
    "build_eval_context",
    "default_corpus_path",
    "default_dataset_path",
    "load_corpus",
    "load_questions",
    "render_markdown",
    "run_matrix",
    "score_records",
]

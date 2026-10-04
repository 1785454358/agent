import asyncio

import pytest

from deeptrace.domain import ResearchMode
from deeptrace.eval import (
    Corpus,
    CorpusDocument,
    EvalFaults,
    EvalQuestion,
    ScriptedResearchModel,
    run_matrix,
)

_GOLD = "https://corpus.example/alpha"
_DISTRACTOR = "https://corpus.example/beta"


def _single_doc_corpus() -> Corpus:
    return Corpus(
        [
            CorpusDocument(
                doc_id="doc-gold",
                url=_GOLD,
                title="alpha beta",
                body="alpha beta",
            )
        ]
    )


def _ranked_corpus() -> Corpus:
    return Corpus(
        [
            CorpusDocument(
                doc_id="doc-gold",
                url=_GOLD,
                title="alpha beta",
                body="alpha beta",
            ),
            CorpusDocument(
                doc_id="doc-distractor",
                url=_DISTRACTOR,
                title="alpha beta gamma",
                body="alpha beta gamma",
            ),
        ]
    )


def _question(gold_urls: list[str]) -> list[EvalQuestion]:
    return [
        EvalQuestion(
            id="q-fault",
            question="alpha beta gamma",
            gold_answer="alpha",
            gold_urls=gold_urls,
        )
    ]


def _run(corpus, question, faults, mode):
    return asyncio.run(
        run_matrix(
            question,
            corpus,
            model_factory=ScriptedResearchModel,
            modes=(mode,),
            run_prefix=f"test-faults-{mode.value}",
            faults=faults,
        )
    )


@pytest.mark.parametrize("mode", list(ResearchMode))
def test_transient_failure_is_retried_by_the_gateway(mode) -> None:
    records = _run(
        _single_doc_corpus(),
        _question([_GOLD]),
        EvalFaults(fetch={_GOLD: "transient_once"}),
        mode,
    )
    record = records[0]
    assert record.mode == mode.value
    assert record.termination_reason == "completed"
    assert _GOLD in record.evidence_urls
    assert record.tool_retries >= 1


@pytest.mark.parametrize("mode", list(ResearchMode))
def test_agent_recovers_from_empty_page_by_trying_next_source(mode) -> None:
    records = _run(
        _ranked_corpus(),
        _question([_GOLD]),
        EvalFaults(fetch={_DISTRACTOR: "empty"}),
        mode,
    )
    record = records[0]
    assert record.mode == mode.value
    assert record.termination_reason == "completed"
    assert _GOLD in record.evidence_urls
    # empty_page is agent-recoverable, so the gateway must not retry it
    assert record.tool_retries == 0


@pytest.mark.parametrize("mode", list(ResearchMode))
def test_hard_empty_page_yields_partial_without_crashing(mode) -> None:
    records = _run(
        _single_doc_corpus(),
        _question([_GOLD]),
        EvalFaults(fetch={_GOLD: "empty"}),
        mode,
    )
    record = records[0]
    assert record.mode == mode.value
    assert record.termination_reason == "no_sources"
    assert record.answered is False
    assert record.evidence_ids == []


@pytest.mark.parametrize("mode", list(ResearchMode))
def test_search_failure_yields_partial_without_crashing(mode) -> None:
    records = _run(
        _single_doc_corpus(),
        _question([_GOLD]),
        EvalFaults(search_queries=frozenset({"alpha beta gamma"})),
        mode,
    )
    record = records[0]
    assert record.mode == mode.value
    assert record.termination_reason == "no_sources"
    assert record.answered is False


@pytest.mark.parametrize("mode", list(ResearchMode))
def test_persistent_transient_failure_is_retried_then_gives_up(mode) -> None:
    records = _run(
        _single_doc_corpus(),
        _question([_GOLD]),
        EvalFaults(fetch={_GOLD: "transient_always"}),
        mode,
    )
    record = records[0]
    assert record.mode == mode.value
    assert record.tool_retries >= 1
    assert record.termination_reason == "no_sources"
    assert record.answered is False


@pytest.mark.parametrize("mode", list(ResearchMode))
def test_unhandled_failure_is_fatal_and_not_retried(mode) -> None:
    records = _run(
        _single_doc_corpus(),
        _question([_GOLD]),
        EvalFaults(fetch={_GOLD: "raise"}),
        mode,
    )
    record = records[0]
    assert record.mode == mode.value
    assert record.tool_retries == 0
    assert record.termination_reason == "tool_error"
    assert record.answered is False

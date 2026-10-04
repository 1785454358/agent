"""Frozen actual source excerpts, not the synthetic smoke fixtures."""

import hashlib
import json

from deeptrace.eval.dataset import default_corpus_path, load_corpus, load_questions
from deeptrace.eval.env import Corpus


def test_pilot_assets_have_disjoint_scoring_reference_and_real_provenance():
    root = default_corpus_path().parent.parent
    documents = load_corpus(root / "corpora/real-pilot-v1.jsonl")
    questions = load_questions(root / "datasets/real-pilot-v1.jsonl")
    card = json.loads((root / "real-pilot-v1-card.json").read_text(encoding="utf-8"))
    assert len(questions) == card["question_count"] == 1
    assert card["split"] == "dev_calibration"
    assert card["reviewer_kind"] != "human"
    assert card["source_license"] == "MIT"
    assert (
        "Copyright (c) 2024 LangChain, Inc."
        in (root / "langgraph-LICENSE.txt").read_text()
    )
    assert all(card["source_commit"] in d.url for d in documents)
    assert set(questions[0].gold_urls) == {d.url for d in documents}
    assert len(Corpus(documents).search(questions[0].question, limit=5)) == 2
    for document, provenance in zip(documents, card["documents"], strict=True):
        assert (
            provenance["body_sha256"]
            == hashlib.sha256(document.body.encode()).hexdigest()
        )

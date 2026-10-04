from deeptrace.eval import (
    default_corpus_path,
    default_dataset_path,
    load_corpus,
    load_questions,
)
from deeptrace.tools.scraper.urls import normalize_url_before_fetch


def test_smoke_dataset_is_consistent_with_corpus() -> None:
    questions = load_questions(default_dataset_path())
    documents = load_corpus(default_corpus_path())

    assert len(questions) >= 3
    assert len(documents) >= 3

    corpus_urls = {normalize_url_before_fetch(doc.url) for doc in documents}
    for question in questions:
        assert question.gold_urls
        for url in question.gold_urls:
            assert normalize_url_before_fetch(url) in corpus_urls

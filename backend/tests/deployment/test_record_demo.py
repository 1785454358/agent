import pytest

from scripts.record_demo import validate_result


def test_recording_accepts_a_completed_answer_with_numbered_sources():
    validate_result({"status": "completed", "answer": "A source-backed answer with enough content. [1]", "sources": ["https://example.com"]}, [])


@pytest.mark.parametrize("result,errors", [
    ({"status": "partial", "answer": "A source-backed answer with enough content. [1]", "sources": ["https://example.com"]}, []),
    ({"status": "completed", "answer": " ", "sources": ["https://example.com"]}, []),
    ({"status": "completed", "answer": "An answer with no supporting sources or citations.", "sources": []}, []),
    ({"status": "completed", "answer": "An answer with a nonexistent numbered source. [2]", "sources": ["https://example.com"]}, []),
    ({"status": "completed", "answer": "A source-backed answer with enough content. [1]", "sources": ["https://example.com"]}, ["TypeError"]),
])
def test_recording_cannot_pass_a_failed_or_unusable_demo(result, errors):
    with pytest.raises(ValueError):
        validate_result(result, errors)

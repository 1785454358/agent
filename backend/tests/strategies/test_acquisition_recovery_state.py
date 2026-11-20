from deeptrace.domain import ResearchTopicOutcome
from deeptrace.strategies.model_io import branch_context


def test_permanent_failure_is_carried_to_new_branch_without_marking_coverage():
    result = branch_context({'question':'Find original document', 'topic_outcomes':[
        ResearchTopicOutcome(query='first', attempted_urls=['https://example.com/v1/report.pdf'],
            errors=[{'stage':'fetch','target':'https://example.com/v1/report.pdf','code':'pdf_page_limit'}]),
    ]})
    assert result['blocked_acquisitions'] == {'https://example.com/v1/report.pdf':'pdf_page_limit'}


def test_transient_fetch_gets_one_new_attempt_then_stops_repeating():
    url = 'https://example.com/v1/report.html'
    outcomes = [ResearchTopicOutcome(query=f'query-{i}', attempted_urls=[url],
        errors=[{'stage':'fetch','target':url,'code':'http_failed'}]) for i in range(2)]
    assert branch_context({'question':'q','topic_outcomes':outcomes[:1]})['blocked_acquisitions'] == {}
    assert branch_context({'question':'q','topic_outcomes':outcomes})['blocked_acquisitions'] == {url:'http_failed'}

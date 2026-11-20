"""The report's factual table must preserve experimental scope mechanically."""

from deeptrace.responses.research_tables import render_research_table


def records():
    return [{"finding_id": "f1", "research_result": {"title": "Study A"}, "experiments": [{
        "model": {"value": "Model-Zero", "refs": ["[1]"]},
        "dataset": {"value": "Benchmark-A", "refs": ["[1]"]},
        "metric": {"value": "pass@1", "refs": ["[1]"]},
        "result": {"value": "71.0", "refs": ["[1]"]},
        "conditions": {"value": "throughout RL training", "refs": ["[1]"]}}]},
        {"finding_id": "f2", "research_result": {"title": "Study B"}, "experiments": [{
            "model": {"value": "Model-B", "refs": ["[2]"]},
            "dataset": {"value": "Benchmark-B", "refs": ["[2]"]},
            "result": {"value": "83.2", "refs": ["[2]"]}}]}]


def test_generated_table_cannot_relabel_training_result_or_invent_budget():
    draft = "机制分析。\n\n| 模型 | 得分 |\n|---|---|\n| Wrong model | 99.9 |\n\n适用条件分析。"
    report, rows = render_research_table(draft, records(), max_chars=5000)
    assert rows == 2
    assert "99.9" not in report and "Wrong model" not in report
    assert "Model-Zero" in report and "71.0" in report
    assert "throughout RL training" in report
    assert "本次未核实" in report
    assert "适用条件分析" in report


def test_canonical_table_does_not_overwrite_code_example_or_exceed_caller_cap():
    content = "```text\n| Code | Example |\n|---|---|\n| a | b |\n```\n\nAnalysis."
    report, rows = render_research_table(content, records(), max_chars=5000)
    assert rows == 2 and content in report
    limited, rows = render_research_table(content, records(), max_chars=len(content))
    assert limited == content and rows == 0


def test_research_records_do_not_replace_an_unrelated_latency_table():
    content = "| 阶段 | 耗时 |\n|---|---|\n| 检索 | 2秒 |\n\nAnalysis."
    report, rows = render_research_table(content, records(), max_chars=5000)
    assert rows == 2
    assert content in report

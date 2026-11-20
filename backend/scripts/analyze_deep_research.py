"""Summarize raw stage traces; terminal status is not an answer-quality score."""

import argparse
from collections import Counter
import json
from pathlib import Path

from langchain_core.messages import AIMessage
from deeptrace.strategies.evidence_references import parse_reference_evaluation
from deeptrace.strategies.model_io import payload_text
from deeptrace.strategies.workflow.models import ReferenceWorkflowEvaluation


def analyze(root):
    root = Path(root)
    stages = []
    for path in sorted(root.glob('model-*.json')):
        row = json.loads(path.read_text('utf8'))
        stage = {key: row.get(key) for key in ('index', 'role', 'started_seconds', 'seconds', 'usage', 'error_type')}
        if row['role'] == 'evaluator' and row.get('content'):
            try:
                assessment = parse_reference_evaluation(ReferenceWorkflowEvaluation,
                    payload_text(AIMessage(content=row['content'])))
                stage.update(schema_valid=True, findings=len(assessment.findings),
                             coverage={item.requirement_id: item.status for item in assessment.coverage.items})
            except Exception as exc:
                stage.update(schema_valid=False, schema_error_type=type(exc).__name__)
            prompt = str(row['messages'][-1]['content'])
            if 'EVIDENCE_VIEW_JSON:\n' in prompt:
                view = json.loads(prompt.split('EVIDENCE_VIEW_JSON:\n', 1)[1])
                stage['visible_sources'] = [{
                    'label': source['source'], 'url': source['url'], 'title': source['title'],
                    'visible_chars': sum(len(p['text']) for p in view['passages'] if p['source'] == source['source']),
                } for source in view['sources']]
        stages.append(stage)
    tool_counts, failures, fetches = Counter(), Counter(), []
    for path in sorted(root.glob('tool-*.json')):
        row = json.loads(path.read_text('utf8'))
        request, result = row['request'], row.get('result') or {}
        tool_counts[request['tool']] += 1
        if not result.get('ok'):
            failures[result.get('error_code') or row.get('error_type') or 'unfinished'] += 1
        if request['tool'] == 'fetch_page':
            fetches.append({'url': request['arguments']['url'], 'ok': result.get('ok'),
                            'error_code': result.get('error_code')})
    result = json.loads((root / 'result.json').read_text('utf8'))
    usage = json.loads((root / 'usage.json').read_text('utf8'))
    summary = {
        'status': result['status'], 'reason': result['termination_reason'],
        'answer_chars': len(result['response_outcome']['content']), 'cited_sources': len(result['sources']),
        'fetched_evidence_count': len(result['research_outcome']['evidence_ids']),
        'seconds': json.loads((root / 'timing.json').read_text('utf8'))['seconds'],
        'provider_attempts': usage['provider_attempts'], 'input_tokens': usage['input_tokens'],
        'output_tokens': usage['output_tokens'], 'usage_complete': usage['usage_complete'],
        'tool_counts': dict(tool_counts), 'tool_failures': dict(failures),
        'fetches': fetches, 'model_stages': stages,
        'final_coverage': result['research_outcome']['coverage'],
    }
    (root / 'analysis.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ('model_stages', 'fetches', 'final_coverage')}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('roots', nargs='+')
    for root in parser.parse_args().roots:
        analyze(root)

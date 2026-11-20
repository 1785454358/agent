"""A fixed eight-case, local configuration comparison with auditable raw outputs.

Run from backend: python -m deeptrace.evaluation.local_sample --output runs/eight --run
Without --run, only freeze the protocol; no provider request is made.
"""

import argparse
import asyncio
import hashlib
import json
import statistics
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from deeptrace.evaluation.datasets import load_examples

DATA = Path(__file__).parent / 'data'
CASE_IDS = (
    'single_hop-test-01', 'multi_hop-test-01', 'multi_hop-test-03', 'comparison-test-02',
    'version_boundary-test-02', 'conflicting_evidence-test-02',
    'conflicting_evidence-test-03', 'insufficient_evidence-test-01',
)
GROUPS = {'baseline': ('legacy', False), 'optimized': ('controller', True)}


def build_cases():
    records = {r['metadata']['id']:r for r in load_examples(DATA/'research-v1.jsonl')}
    documents = json.loads((DATA/'frozen-corpus.json').read_text(encoding='utf-8'))
    if any(hashlib.sha256(d['body'].encode()).hexdigest() != d['sha256'] for d in documents):
        raise ValueError('corpus hash mismatch')
    return [{**records[key], 'inputs':{'question':records[key]['inputs']['question'],
                                      'documents':documents}} for key in CASE_IDS]


def summarize(records, *, expected_cases=8):
    identities = [(r['case_id'],r['group']) for r in records]
    if len(set(identities)) != len(identities):
        raise ValueError('duplicate trial identity')
    groups = {}
    for group in GROUPS:
        trials = [r for r in records if r['group'] == group]
        complete_usage = bool(trials) and all((r.get('usage') or {}).get('usage_complete') is True
            and isinstance(r['usage'].get('input_tokens'), int) for r in trials)
        groups[group] = {
            'runs':len(trials), 'failed_runs':sum(r['status']=='failed' for r in trials),
            'mean_tool_calls':statistics.mean(r['tool_calls'] for r in trials) if trials else None,
            'mean_model_calls':statistics.mean(r['model_calls'] for r in trials) if trials else None,
            'mean_elapsed_seconds':statistics.mean(r['elapsed_seconds'] for r in trials) if trials else None,
            'mean_input_tokens':statistics.mean(r['usage']['input_tokens'] for r in trials) if complete_usage else None,
            'task_acceptance_rate':None, 'unsupported_fact_rate':None, 'citation_support_rate':None,
            'semantic_metrics_status':'requires claim-level review; execution status is not acceptance',
        }
    paired = set(r['case_id'] for r in records if r['group']=='baseline') & set(
        r['case_id'] for r in records if r['group']=='optimized')
    reduction = None
    a, b = (groups[k]['mean_input_tokens'] for k in GROUPS)
    if len(paired) == expected_cases and all(g['runs']==expected_cases for g in groups.values()) and a and b is not None:
        reduction = (a-b)/a
    return {'expected_cases':expected_cases, 'paired_cases':len(paired), 'groups':groups,
            'input_token_reduction':reduction,
            'retrieval_duplicate_rate':None,
            'retrieval_note':'Frozen corpus evaluation does not measure web-search duplication.'}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


def prepare(output, settings):
    cases = build_cases()
    save(output/'protocol.json', {
        'created_at':datetime.now(UTC).isoformat(), 'case_ids':list(CASE_IDS),
        'mode':'workflow', 'groups':{k:{'orchestrator':v[0],'fact_review':v[1]} for k,v in GROUPS.items()},
        'model':settings.openai_model, 'thinking':settings.model_thinking,
        'max_model_calls':settings.max_model_calls, 'max_input_tokens':settings.max_input_tokens,
        'research_max_seconds':settings.research_max_seconds,
        'source_target':settings.research_source_target, 'memory':'isolated/disabled',
        'scope':'configuration comparison, not historical before/after or full ablation',
        'corpus':[{k:d[k] for k in ('id','url','sha256','commit')} for d in cases[0]['inputs']['documents']],
        'code_sha256':{str(p.relative_to(Path(__file__).parents[1])):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(Path(__file__).parents[1].rglob('*.py'))},
    })
    save(output/'cases.json', [{**c,'inputs':{'question':c['inputs']['question']}} for c in cases])
    save(output/'summary.json',summarize([]))
    return cases


async def probe(settings, output):
    from deeptrace.application.assembly import build_harness_runtime
    from deeptrace.harness.prompts import task_messages
    bundle = build_harness_runtime(settings,runs_dir=output/'probe-runtime')
    result = {'at':datetime.now(UTC).isoformat(),'model':settings.openai_model}
    try:
        context = bundle.context_factory('probe-'+uuid4().hex[:10])
        await context.model_gateway.invoke(role='planner',messages=task_messages(
            instruction='Return only OK.',task='Confirm model service availability.'))
        result['available'] = True
    except Exception as exc:
        result.update(available=False,error_code=getattr(exc,'code',type(exc).__name__),
                      status_code=getattr(exc.__cause__,'status_code',None))
    finally:
        save(output/'preflight.json',result)
        await bundle.aclose()
    return result['available']


async def execute_case(bundle, case, group, output, settings):
    from deeptrace.application.research import ApplicationResearchRequest
    from deeptrace.evaluation.runner import _CountTools
    from deeptrace.observability.model_metrics import run_usage_payload
    from deeptrace.tools.evidence_store import EvidenceDraft
    root = output/group/case['metadata']['id']
    root.mkdir(parents=True,exist_ok=True)
    run_id = uuid4().hex
    events = []
    def event(kind, payload):
        events.append({'event_type':kind,'payload':payload})
    context = bundle.context_factory(run_id,on_event=event)
    identities = []
    for document in case['inputs']['documents']:
        evidence = await context.evidence_store.ingest(context.workspace_id,EvidenceDraft(
            canonical_url=document['url'],title=document['title'],body=document['body'],
            media_type='text/markdown',fetched_at=datetime.now(UTC),source_quality=1,
            metadata={'provided_source':True,'sha256':document['sha256']}))
        identities.append(evidence.id)
    tools = _CountTools(context.tool_gateway.with_source_scope(frozenset(identities)))
    context = replace(context,tool_gateway=tools,source_evidence_ids=tuple(identities),
                      memory_store=None,memory_retriever=None)
    started = time.perf_counter()
    record = {'case_id':case['metadata']['id'],'group':group,'run_id':run_id}
    try:
        result = await asyncio.wait_for(bundle.service.invoke(ApplicationResearchRequest(
            run_id=run_id,thread_id=run_id,question=case['inputs']['question'],mode='workflow'),
            config={'configurable':{'thread_id':run_id},'recursion_limit':80},context=context),
            timeout=settings.research_max_seconds+300)
        save(root/'result.json',result.model_dump(mode='json'))
        record.update(status=result.status,termination_reason=result.termination_reason)
        (root/'answer.md').write_text(result.response_outcome.content if result.response_outcome else '',encoding='utf-8')
        source_records = await context.evidence_store.get_many(context.workspace_id,
            result.research_outcome.evidence_ids if result.research_outcome else [])
        save(root/'sources.json',[{**r.model_dump(mode='json'),
            'body':await context.evidence_store.read_body(context.workspace_id,r.id)} for r in source_records])
    except Exception as exc:
        record.update(status='failed',error_code=getattr(exc,'code',type(exc).__name__))
    finally:
        record.update(elapsed_seconds=time.perf_counter()-started,tool_calls=tools.calls,
                      model_calls=context.model_gateway.used_calls,usage=run_usage_payload(context),
                      service_blocker=context.model_gateway.unavailable_reason)
        save(root/'metrics.json',record)
        save(root/'events.json',events)
        bundle.release_run(run_id)
    return record


async def main(args):
    from deeptrace.config import Settings
    from deeptrace.application.assembly import build_harness_runtime
    from langsmith import tracing_context
    settings = replace(Settings.from_env(),runtime_mode='local',mysql_dsn='',redis_url='',memory_retrieval='lexical')
    output = args.output.resolve()
    if (output/'protocol.json').exists():
        raise ValueError('Choose a fresh output directory; previous trials must not be overwritten')
    cases = prepare(output,settings)
    if not args.run:
        print(f'Prepared 8 cases, no provider calls: {output}')
        return 0
    # Local artifacts are authoritative; do not require a hosted tracing account.
    with tracing_context(enabled=False):
        if not await probe(settings,output):
            save(output/'status.json',{'status':'blocked','reason':'provider_unavailable','executed_cases':0})
            print(f'BLOCKED: see {output / "preflight.json"}')
            return 2
        bundles = {key:build_harness_runtime(replace(settings,research_orchestrator=mode,
            response_fact_review=review),runs_dir=output/key/'runtime') for key,(mode,review) in GROUPS.items()}
        records = []
        try:
            for index,case in enumerate(cases):
                for group in (tuple(GROUPS) if index%2==0 else tuple(reversed(GROUPS))):
                    record = await execute_case(bundles[group],case,group,output,settings)
                    records.append(record)
                    save(output/'runs.json',records)
                    save(output/'summary.json',summarize(records))
                    print(json.dumps({k:record[k] for k in ('case_id','group','status','elapsed_seconds')},ensure_ascii=False),flush=True)
                    if record.get('service_blocker'):
                        save(output/'status.json',{'status':'blocked','reason':record['service_blocker'],'executed_runs':len(records)})
                        return 2
            save(output/'status.json',{'status':'awaiting_semantic_review','executed_runs':len(records)})
        finally:
            for bundle in bundles.values():
                await bundle.aclose()
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--run',action='store_true')
    raise SystemExit(asyncio.run(main(parser.parse_args())))

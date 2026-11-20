"""Real response-stage replay with frozen research and its remaining budget."""

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import time
import uuid

from deeptrace.application.assembly import build_harness_runtime
from deeptrace.config import Settings
from deeptrace.domain import ResearchOutcome, ResponseInput, ResponseMode
from deeptrace.harness.model_budget import RunBudgetModelGateway
from deeptrace.harness.token_budget import TokenBudgetConfig
from deeptrace.responses.graph import build_report_graph
from deeptrace.tools.evidence_store import EvidenceDraft


def save(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf8')


async def replay(source, recover_fields=False):
    source = Path(source)
    protocol = json.loads((source/'protocol.json').read_text('utf8'))
    result = json.loads((source/'result.json').read_text('utf8'))
    calls = [json.loads(p.read_text('utf8')) for p in sorted(source.glob('model-*.json'))]
    writer = next(row for row in calls if row['role'] == 'responder')
    preceding = [row for row in calls if row['index'] < writer['index'] and row.get('usage')]
    research_input_tokens = sum(row['usage']['input_tokens'] for row in preceding)
    remaining_input = protocol['max_input_tokens'] - research_input_tokens
    remaining_calls = protocol['max_model_calls'] - len(preceding)
    remaining_seconds = max(1, protocol['research_max_seconds'] - writer['started_seconds'])
    root = Path('runs')/(('field-recovery-replay-20261117-' if recover_fields else 'scholarly-response-replay-20261117-')+uuid.uuid4().hex[:6])
    root.mkdir(parents=True)
    settings = replace(Settings.from_env(), runtime_mode='local', mysql_dsn='', redis_url='', memory_retrieval='lexical')
    save(root/'protocol.json', {
        'source_run': str(source), 'question': protocol['question'], 'model': settings.openai_model,
        'source_run_model': protocol['model'], 'same_model': settings.openai_model == protocol['model'],
        'scope': 'frozen originals: bounded field reread and reevaluation, then response; no search' if recover_fields
                 else 'response-stage replay; no new research or search',
        'research_input_tokens': research_input_tokens, 'research_provider_calls': len(preceding),
        'remaining_input_tokens': remaining_input, 'remaining_model_calls': remaining_calls,
        'remaining_research_seconds': remaining_seconds, 'finishing_seconds': 120,
        'source_manifest_sha256': hashlib.sha256((source/'sources.json').read_bytes()).hexdigest(),
        'code_hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(Path('src/deeptrace').rglob('*.py'))},
    })
    bundle = build_harness_runtime(settings, runs_dir=root/'state')
    events = []
    replay_run_id = 'response-'+uuid.uuid4().hex[:12]
    context = bundle.context_factory(replay_run_id, lambda kind, details:
        events.append({'type': kind, 'details': details}))
    gateway = RunBudgetModelGateway(context.model_gateway.inner,
        max_calls=remaining_calls, max_input_tokens=remaining_input,
        finishing_input_reserve=min(20000, remaining_input-1), max_seconds=remaining_seconds,
        event_sink=context.event_sink)
    count = 0
    class RecordingModel:
        def __getattr__(self, name):
            return getattr(gateway, name)
        async def invoke(self, **kwargs):
            nonlocal count
            count += 1
            row = {'messages': [m.model_dump(mode='json') for m in kwargs['messages']]}
            path = root/f'model-{count:02d}.json'
            save(path, row)
            try:
                response = await gateway.invoke(**kwargs)
                row.update(content=response.content, usage=response.usage_metadata)
                return response
            except BaseException as exc:
                row.update(error_type=type(exc).__name__, error_code=getattr(exc, 'code', None))
                raise
            finally:
                save(path, row)
    context = replace(context, model_gateway=RecordingModel())
    started = time.monotonic()
    print('artifacts:', root.resolve(), flush=True)
    try:
        for original in json.loads((source/'sources.json').read_text('utf8')):
            record = await context.evidence_store.ingest(context.workspace_id, EvidenceDraft(
                canonical_url=original['canonical_url'], title=original['title'], body=original['body'],
                media_type=original['media_type'], fetched_at=datetime.fromisoformat(original['fetched_at']),
                source_quality=original['source_quality'], metadata=original['metadata'],
                published_at=datetime.fromisoformat(original['published_at']) if original['published_at'] else None))
            assert (record.id, record.version, record.content_hash) == (
                original['id'], original['version'], original['content_hash'])
        research = ResearchOutcome.model_validate(result['research_outcome'])
        if recover_fields:
            from langgraph.runtime import Runtime
            from deeptrace.domain import ResearchTopicOutcome
            from deeptrace.domain.evidence_anchor import ReadEvidenceAnchor
            from deeptrace.research.field_recovery import plan_field_reads, field_reread_node
            from deeptrace.research.quality import evaluate_node
            from deeptrace.strategies.evidence_evaluation import seal_requirements
            from validate_deep_research import ClientClock
            context = replace(context, clock=ClientClock())
            requirements,_ = seal_requirements(protocol['question'],research.requirements)
            original = ResearchTopicOutcome(query='frozen-accepted-reading', evidence_ids=research.evidence_ids,
                read_anchors=[ReadEvidenceAnchor(**s.model_dump(exclude={'quote'})) for f in research.findings for s in f.supports])
            recovery_state = {'run_id':replay_run_id,'thread_id':replay_run_id,'question':protocol['question'],
                'current_date':'2026-11-17','timezone':'Asia/Shanghai','evidence_contract_version':3,
                'mode':research.mode.value,'requirements':requirements,'coverage':research.coverage,
                'findings':research.findings,'evidence_ids':research.evidence_ids,'source_eligibility':research.source_eligibility,
                'research_brief':{'source_policy':'research_results','publication_years':[2024,2025]},
                'topic_outcomes':[original], 'queries':[], 'field_checks':[], 'field_reread_count':0}
            for phase in range(2):
                planned = await plan_field_reads(recovery_state,context)
                if not planned['reread_actions']:
                    break
                # A field read targets the still-unverified parameter dimension.
                targets={t for a in planned['reread_actions'] for t in a.target_requirement_ids}
                recovery_state['coverage']=recovery_state['coverage'].model_copy(update={'items':[
                    i.model_copy(update={'status':'missing'}) if i.requirement_id in targets else i
                    for i in recovery_state['coverage'].items]})
                read = await field_reread_node(recovery_state,Runtime(context=context))
                previous = recovery_state['topic_outcomes']
                recovery_state.update(read)
                recovery_state['topic_outcomes']=[*previous,*read.get('topic_outcomes',[])]
                evaluated=await evaluate_node(recovery_state,Runtime(context=context))
                recovery_state.update(evaluated)
                save(root/f'recovery-{phase+1}.json', recovery_state)
                print('field phase',phase+1,'checks',len(recovery_state['field_checks']),
                    'experiments',sum(len(f.experiments) for f in recovery_state['findings']),flush=True)
            research=research.model_copy(update={'requirements':requirements,
                'coverage':recovery_state['coverage'],'findings':recovery_state['findings'],
                'field_checks':recovery_state['field_checks'],'source_eligibility':recovery_state['source_eligibility'],
                'termination_reason':'completed' if recovery_state.get('verification') and recovery_state['verification'].coverage_complete
                else 'insufficient_evidence'})
            save(root/'research-outcome.json',research.model_dump(mode='json'))
        payload = ResponseInput(question=protocol['question'], response_mode=ResponseMode.REPORT,
            research_outcome=research, active_evidence_ids=research.evidence_ids,
            verified_finding_ids=[f.id for f in research.findings])
        state = await build_report_graph(TokenBudgetConfig(context_tokens=settings.model_context_tokens,
            output_reserve_tokens=settings.openai_max_tokens or 4096, safety_tokens=settings.context_safety_tokens)
        ).ainvoke({'response_input': payload}, context=context)
        outcome = state['outcome']
        save(root/'result.json', outcome.model_dump(mode='json'))
        references = []
        for citation in outcome.citations:
            record = await context.evidence_store.get(context.workspace_id, citation.evidence_id)
            references.append(f'{citation.marker} [{record.title}]({record.canonical_url})')
        (root/'answer.md').write_text(outcome.content+'\n\n## 资料来源\n\n'+'\n\n'.join(references), encoding='utf8')
        print('reason',outcome.partial_reason, 'chars',len(outcome.content),'sources',len(outcome.citations),
              'calls', gateway.used_calls, 'input', gateway.used_input_tokens,
              'seconds',round(time.monotonic()-started,2),flush=True)
    except BaseException as exc:
        save(root/'error.json', {'type': type(exc).__name__, 'code': getattr(exc, 'code', None)})
        raise
    finally:
        save(root/'events.json', events)
        save(root/'usage.json', gateway.usage_payload())
        save(root/'timing.json', {'seconds': time.monotonic()-started})
        await bundle.aclose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_run')
    parser.add_argument('--recover-fields',action='store_true')
    args=parser.parse_args()
    asyncio.run(replay(args.source_run,args.recover_fields))

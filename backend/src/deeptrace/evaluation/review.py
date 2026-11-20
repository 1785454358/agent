"""Re-evaluate existing LangSmith runs against the writer's actual context."""
import asyncio
from langsmith.utils import LangSmithConnectionError, LangSmithRateLimitError


def align_citations(materials, sources):
    mapping = '\n'.join(f'Final answer [{i}] -> {url}' for i,url in enumerate(sources,1))
    return ('Citation mapping after final answer compaction:\n'+mapping+
        '\nThe original writer labels below predate compaction; compare citations by source URL, not by equal label number.\n'+materials)


def writer_materials(runs):
    header = '以下是本轮已加载的全部资料（编号即引用标记，禁止引用未列出的来源）：\n\n'
    selected = ''
    for run in sorted(runs, key=lambda item: item.start_time):
        for group in (run.inputs or {}).get('messages', []):
            for message in group if isinstance(group, list) else [group]:
                text = message.get('kwargs', message).get('content', '')
                if isinstance(text, str) and header in text:
                    selected = text.split(header, 1)[1].split('\n只输出 JSON：', 1)[0].strip()
    return selected


def trace_grounded_evaluator(client, model):
    from .evaluators import answer_correctness
    grade = answer_correctness(model)

    async def evaluate(run, example):
        if run.reference_example_id != example.id:
            raise ValueError('Run and reference example do not match')
        await asyncio.to_thread(client.flush, timeout=10)
        materials = ''
        for attempt in range(2):
            try:
                runs = await asyncio.to_thread(lambda: list(client.list_runs(
                    project_id=getattr(run, 'session_id', None),
                    trace_id=run.trace_id, run_type='llm',
                    select=['id','name','run_type','start_time','inputs'])))
                materials = writer_materials(runs)
                if materials or attempt:
                    break
            except (LangSmithConnectionError, LangSmithRateLimitError):
                if attempt:
                    raise
            await asyncio.sleep(0.5)
        if not materials:
            return {'results': [
                {'key':'task_accepted_v4','score':False,'comment':'No actual writer evidence found in native trace'},
                {'key':'answer_groundedness_v4','score':None,'comment':'Writer evidence unavailable; review required'}]}
        materials = align_citations(materials, (run.outputs or {}).get('sources', []))
        outputs = {**(run.outputs or {}), 'evidence_excerpts':[{'quote':materials}]}
        feedback = await grade(example.inputs, outputs, example.outputs)
        items = feedback.get('results', [feedback])
        return {'results':[{**item, 'key':item['key']+'_v4'} for item in items]}
    return evaluate

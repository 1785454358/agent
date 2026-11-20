"""Archive measured runs and a separately audited, predefined-rubric assessment."""
import copy
import hashlib
import json
import shutil
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[2]
OUT=PROJECT/'docs/benchmarks/2026-11-16-eight-case-live'
OUT.mkdir(parents=True,exist_ok=True)

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

runs=read(ROOT/'runs.json')
cases=read(ROOT/'cases.json')
assert len(runs)==16 and len({(r['case_id'],r['group']) for r in runs})==16
assert all(r['usage']['usage_complete'] for r in runs)

assessments=[]
for case in cases:
    key=case['metadata']['id']
    folder='judging-retry-v2' if key in ('multi_hop-test-03','comparison-test-02') else 'judging'
    original=read(ROOT/folder/key/'grade.json')
    mapping=read(ROOT/folder/key/'mapping.json')
    for label,group in mapping.items():
        value=copy.deepcopy(original[label])
        adjustments=[]
        if key=='insufficient_evidence-test-01':
            # Both are generic failure messages, not an explanation that the
            # requested ranking cannot be inferred from the supplied guide.
            requirement=next(c for c in value['criteria'] if c['id']=='R1')
            adjustments.append({'criterion':'R1','before':requirement['status'],'after':'missing',
                'reason':'The answer is only a generic source-list fallback; silence is not an explicit answer about inferability.'})
            requirement['status']='missing'
            requirement['reason']=adjustments[-1]['reason']
        result=read(ROOT/group/key/'result.json')
        answer=(result.get('response_outcome') or {}).get('content','')
        substantive=bool(answer) and not answer.startswith('本次研究未能生成有引用支持的完整内容')
        covered=sum(c['status']=='covered' for c in value['criteria'])
        assessments.append({'case_id':key,'group':group,'grade_source':folder,
            'criteria':value['criteria'],'covered':covered,'total':len(value['criteria']),
            'rubric_accepted':substantive and covered==len(value['criteria']),
            'has_substantive_answer':substantive,'execution_status':result['status'],
            'adjustments':adjustments,
            'raw_citation_relations':{'supported':sum(ci['status']=='supported' for c in value['claims'] for ci in c['citations']),
                                      'total':sum(len(c['citations']) for c in value['claims'])}})

summary={'sample_questions':8,'runs':16,'mode':'workflow','model':read(ROOT/'protocol.json')['model'],
    'scope':'Eight previously used frozen-document development cases, once per configuration; no causal ablation or significance claim.',
    'groups':{},'semantic_method':'Blinded same-model paired judging, plus root-assistant review; no independent human annotation.',
    'unsupported_fact_rate':None,'citation_support_rate':None,
    'unpublished_metric_reason':'Review inconsistency: a strict-provider boundary criterion was incorrect while its related extracted claim was called supported; duplicate/compound claim units and overly literal citation judgments remain. Raw model grades retained, not promoted to reliable hallucination statistics.',
    'web_search_duplicate_rate':None,'web_search_note':'Frozen corpus; no live web-search task.'}
for group in ('baseline','optimized'):
    rr=[r for r in runs if r['group']==group];aa=[a for a in assessments if a['group']==group]
    n=len(aa);accepted=sum(a['rubric_accepted'] for a in aa)
    summary['groups'][group]={
        'accepted':accepted,'questions':n,'rubric_acceptance_rate':accepted/n,
        'criteria_covered':sum(a['covered'] for a in aa),'criteria_total':sum(a['total'] for a in aa),
        'criteria_pass_rate':sum(a['covered'] for a in aa)/sum(a['total'] for a in aa),
        'completed':sum(r['status']=='completed' for r in rr),'partial':sum(r['status']=='partial' for r in rr),
        'failed':sum(r['status']=='failed' for r in rr),
        'input_tokens':sum(r['usage']['input_tokens'] for r in rr),
        'output_tokens':sum(r['usage']['output_tokens'] for r in rr),
        'mean_input_tokens':statistics.mean(r['usage']['input_tokens'] for r in rr),
        'input_tokens_per_accepted_result':sum(r['usage']['input_tokens'] for r in rr)/accepted if accepted else None,
        'mean_total_tokens':statistics.mean(r['usage']['input_tokens']+r['usage']['output_tokens'] for r in rr),
        'mean_model_calls':statistics.mean(r['model_calls'] for r in rr),
        'mean_tool_calls':statistics.mean(r['tool_calls'] for r in rr),
        'mean_seconds':statistics.mean(r['elapsed_seconds'] for r in rr),
        'raw_model_citation_supports':sum(a['raw_citation_relations']['supported'] for a in aa),
        'raw_model_citation_relations':sum(a['raw_citation_relations']['total'] for a in aa),
    }
a,b=(summary['groups'][g] for g in ('baseline','optimized'))
summary['changes']={'acceptance_percentage_points':100*(b['rubric_acceptance_rate']-a['rubric_acceptance_rate']),
    'criteria_percentage_points':100*(b['criteria_pass_rate']-a['criteria_pass_rate']),
    **{key+'_relative_increase':b[key]/a[key]-1 for key in ('mean_input_tokens','mean_total_tokens','mean_model_calls','mean_tool_calls','mean_seconds')}}
summary['exploratory_metric']={
    'definition':'All system input tokens, including nonpassing tasks, divided by number of reference-rubric passing results.',
    'post_hoc':True,'input_tokens_per_accepted_result_reduction':1-b['input_tokens_per_accepted_result']/a['input_tokens_per_accepted_result'],
    'warning':'Not average per-task token reduction; highly sensitive to two vs five passing tasks in this small sample.'}
judge_usage=[read(p) for folder in ('judging','judging-retry-v2') for p in (ROOT/folder).glob('*/usage.json')]
summary['judge_overhead']={'provider_attempts':sum(u['provider_attempts'] for u in judge_usage),
    'input_tokens':sum(u['input_tokens'] for u in judge_usage),'output_tokens':sum(u['output_tokens'] for u in judge_usage),
    'included_in_system_per_task_cost':False,'includes_failed_formatting_attempts':True}
save(OUT/'metrics.json',summary)
save(OUT/'assessments.json',assessments)

for name in ('protocol.json','preflight.json','cases.json','runs.json','summary.json','status.json','judge.py','judge_retry_v2.py','report.py'):
    shutil.copyfile(ROOT/name,OUT/name)
for r in runs:
    src=ROOT/r['group']/r['case_id'];dest=OUT/r['group']/r['case_id'];dest.mkdir(parents=True,exist_ok=True)
    for filename in ('answer.md','result.json','metrics.json','events.json','sources.json'):
        shutil.copyfile(src/filename,dest/filename)
for folder in ('judging','judging-retry-v2'):
    for src in (ROOT/folder).rglob('*'):
        if src.is_file():
            dest=OUT/folder/src.relative_to(ROOT/folder);dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dest)
save(OUT/'artifact-manifest.json',{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ('artifact-manifest.json','README.md')})
print(json.dumps(summary,ensure_ascii=False,indent=2))

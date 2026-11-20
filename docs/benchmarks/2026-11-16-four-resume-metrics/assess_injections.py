"""Record root-assistant adjudication of unambiguous synthetic error cases."""
import hashlib
import json
import shutil
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[3]
ROOT=PROJECT/'docs/benchmarks/2026-11-16-four-resume-metrics'
OUT=ROOT/'evidence-injection'
cases=json.loads((OUT/'cases.json').read_text(encoding='utf-8'))
reasons={
 'latency_metric_scope':'p95改为300ms，保留p50=120ms及单机非SLA限定。',
 'strict_capability_scope':'strict限定为仅A，明确B不支持；保留A/B都支持JSON。',
 'minimum_version':'strict最低版本改为2.4，保留Python 3.11及以上。',
 'opening_exception':'周一改为闭馆；保留提前7天预约。',
 'object_field_scope':'messages改归run_state；tenant_id仍归runtime_context。',
 'invented_improvement':'撤回已证明20%收益，说明不能得出具体比例；保留支持批处理。否定引述20%不是继续主张该收益。',
 'wrong_citation':'10探针额度改引[1]；SSO付费继续引[2]，两条事实保留。',
 'free_paid_boundary':'免费历史改为7天；保留付费可延长至30天。',
}
records=[]
for case in cases:
 path=OUT/case['id']
 review=json.loads((path/'review.json').read_text(encoding='utf-8'))
 usage=json.loads((path/'usage.json').read_text(encoding='utf-8'))
 assert usage['usage_complete'] and usage['provider_attempts']==1
 records.append({'case_id':case['id'],'injected_error':case['known_error'],
  'correct_control':case['correct_control'],'known_error_corrected':True,'correct_control_retained':True,
  'whole_answer_deleted':False,'reason':reasons[case['id']],
  'reviewed_content':review['content'],'unanswered_points':review['unanswered_points']})
usage=[json.loads((OUT/c['id']/'usage.json').read_text(encoding='utf-8')) for c in cases]
summary={'cases':8,'injected_known_faults':8,'known_faults_corrected':8,'correct_control_points':8,
 'correct_control_points_retained':8,'whole_answer_deletions':0,
 'provider_attempts':sum(u['provider_attempts'] for u in usage),
 'input_tokens':sum(u['input_tokens'] for u in usage),'output_tokens':sum(u['output_tokens'] for u in usage),
 'method':'Live production review_answer on synthetic evidence and deliberately corrupted drafts; root-assistant assessment against predeclared facts, not independent human annotation.',
 'limitations':['Not naturally generated hallucination rate.','Not end-to-end retrieval success rate.',
               'Small, intentionally simple controlled cases; not universal 100% error correction.',
               'No independent human annotation or significance claim.']}
(OUT/'assessments.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'measurements.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
for name in ('supplement.py','evidence_injection.py','assess_injections.py'):
 shutil.copyfile(Path(__file__).parent/name,ROOT/name)
(ROOT/'artifact-manifest.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
 for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name not in ('artifact-manifest.json','README.md')},indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))

"""Measure separate engineering guarantees without inventing semantic accuracy."""
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[3]
ROOT=PROJECT/'docs/benchmarks/2026-11-16-four-resume-metrics'
LIVE=PROJECT/'docs/benchmarks/2026-11-16-eight-case-live'
ROOT.mkdir(parents=True,exist_ok=True)

STABILITY=[
 ('branch_isolation','tests/research/test_runtime.py::test_ordinary_branch_failure_preserves_sibling_evidence_without_false_completion'),
 ('sqlite_checkpoint_resume','tests/research/test_runtime.py::test_sqlite_resume_reuses_completed_sibling_on_new_graph'),
 ('transient_model_retry','tests/harness/test_model_gateway.py::test_transport_timeout_retries_once'),
 ('bounded_tool_retries','tests/tools/test_gateway.py::test_transient_failure_is_retried_once_inside_the_gateway'),
 ('fatal_tool_no_retry','tests/tools/test_gateway.py::test_unhandled_tool_exception_is_fatal_and_never_retried'),
 ('tool_timeout','tests/tools/test_gateway.py::test_timeout_is_sanitized_recorded_and_charged'),
 ('cancelled_budget_persists','tests/harness/test_durable_model_budget.py::test_cancelled_call_consumption_survives_restart'),
 ('duplicate_recovery_stops','tests/research/test_adaptive_completion.py::test_unresolved_duplicate_recovery_stops_without_redispatching'),
]
BUDGET=[
 ('task_model_cap','tests/research/test_runtime.py::test_task_model_limit_is_enforced_before_provider_dispatch'),
 ('concurrent_reservations','tests/harness/test_model_run_budget.py::test_concurrent_research_calls_reserve_the_shared_run_budget_atomically'),
 ('token_cap_and_writer_reserve','tests/harness/test_model_run_budget.py::test_provider_input_usage_limits_next_call_without_spending_writer_reserve'),
 ('final_review_call_reserve','tests/harness/test_model_run_budget.py::test_final_review_has_a_call_reserved_within_the_existing_total_cap'),
 ('research_and_finishing_deadlines','tests/harness/test_model_run_budget.py::test_elapsed_research_window_leaves_a_separate_finishing_window'),
 ('durable_run_caps','tests/research/test_runtime.py::test_contract_budget_restores_original_run_limits_before_planning'),
]

def save(name,value):
 (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def scenario_group(name,selection):
 xml=ROOT/f'{name}.xml'
 command=[sys.executable,'-m','pytest',*(item[1] for item in selection),'-q',f'--junitxml={xml}']
 result=subprocess.run(command,cwd=PROJECT/'backend',capture_output=True,text=True,encoding='utf-8',errors='replace')
 (ROOT/f'{name}.stdout.log').write_text(result.stdout,encoding='utf-8')
 (ROOT/f'{name}.stderr.log').write_text(result.stderr,encoding='utf-8')
 cases=ET.parse(xml).getroot().findall('.//testcase')
 rows=[]
 for label,identity in selection:
  test_name=identity.rsplit('::',1)[1]
  found=[c for c in cases if c.attrib['name']==test_name]
  assert len(found)==1,(label,'missing_or_parameterized_case')
  c=found[0]
  rows.append({'scenario':label,'test':identity,'passed':not any(c.find(t) is not None for t in ('failure','error','skipped')),
               'seconds':float(c.attrib['time'])})
 assert result.returncode==0,result.stdout[-2000:]
 return {'total':len(rows),'passed':sum(r['passed'] for r in rows),'scenarios':rows,
         'scope':'Controlled injected responses/errors and actual runtime/storage code, not live-provider recovery reliability.'}

summary={'stability':scenario_group('stability',STABILITY),'budget_boundary':scenario_group('budget-boundary',BUDGET),
         'evidence':{},'live_budget':{},'runtime_model':'kimi-k3'}
observations=[]
for group in ('baseline','optimized'):
 counts={'runs':0,'final_citation_refs':0,'traceable_final_citation_refs':0,'accepted_support_segments':0,
         'exact_body_matches':0,'version_hash_matches':0,'generic_empty_answers':0,'budget_compliant_runs':0}
 for p in sorted((LIVE/group).glob('*/result.json')):
  result=json.loads(p.read_text(encoding='utf-8'))
  sources={s['id']:s for s in json.loads((p.parent/'sources.json').read_text(encoding='utf-8'))}
  response=result.get('response_outcome') or {}
  metrics=json.loads((p.parent/'metrics.json').read_text(encoding='utf-8'))
  counts['runs']+=1
  counts['generic_empty_answers']+=int(response.get('content','').startswith('本次研究未能生成有引用支持的完整内容'))
  counts['budget_compliant_runs']+=int(metrics['model_calls']<=20 and metrics['usage']['input_tokens']<=100000
                                     and metrics['elapsed_seconds']<=600)
  for citation in response.get('citations',[]):
   source=sources.get(citation['evidence_id'])
   traceable=bool(source and source['status']=='active' and citation['marker'] in response['content'])
   counts['final_citation_refs']+=1
   counts['traceable_final_citation_refs']+=traceable
   observations.append({'group':group,'case_id':p.parent.name,'kind':'final_citation','marker':citation['marker'],
                        'evidence_id':citation['evidence_id'],'traceable':traceable})
  for finding in (result.get('research_outcome') or {}).get('findings',[]):
   for support in finding['supports']:
    counts['accepted_support_segments']+=1
    source=sources.get(support['evidence_id'])
    exact=bool(source and 0<=support['start']<support['end']<=len(source['body'])
               and source['body'][support['start']:support['end']]==support['quote'])
    intact=bool(source and source['version']==support['version'] and
                source['content_hash']==support['content_hash']=='sha256:'+hashlib.sha256(source['body'].encode()).hexdigest())
    counts['exact_body_matches']+=exact
    counts['version_hash_matches']+=intact
    observations.append({'group':group,'case_id':p.parent.name,'kind':'accepted_support','finding_id':finding['id'],
      'evidence_id':support['evidence_id'],'start':support['start'],'end':support['end'],
      'exact_body_match':exact,'version_hash_match':intact})
 summary['evidence'][group]=counts
summary['evidence']['scope']='Accepted stored support segments and final citation identities only; not raw proposal quality, unique facts, semantic entailment or hallucination rate.'
summary['live_budget']={'compliant_runs':sum(summary['evidence'][g]['budget_compliant_runs'] for g in ('baseline','optimized')),
 'total_runs':16,'caps':{'model_calls':20,'input_tokens':100000,'research_seconds':600},
 'time_note':'All recorded full-task elapsed times are below 600s, a stricter observation than the research-only cap; this does not claim a general hard end-to-end deadline.',
 'page_budget_note':'Frozen documents were preloaded; no live page-budget stress or web duplicate-search rate is inferred.'}
summary['stable_resume_observation']={
 'scenario':'sqlite_checkpoint_resume','completed_branch_calls_before_and_after_resume':1,'completed_branch_reexecutions':0,
 'interrupted_branch_total_calls':2,'scope':'One injected interruption and one fresh-graph SQLite resume, asserted by the named regression.'}
summary['cautions']=['Scenario pass rates are not production uptime or real-provider recovery rates.',
 'Accepted support segments can be repeated across findings; the denominator is stored support records, not distinct facts.',
 'Exact quote matching verifies provenance, not whether the quote semantically supports the claim.',
 'Both configurations already have host evidence checks; these observations do not prove that a new evidence mechanism improved citation accuracy.']
save('measurements.json',summary)
save('evidence-checks.json',observations)
save('protocol.json',{'stability':STABILITY,'budget_boundary':BUDGET,'source_live_experiment':str(LIVE.relative_to(PROJECT)),
 'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
print(json.dumps(summary,ensure_ascii=False,indent=2))

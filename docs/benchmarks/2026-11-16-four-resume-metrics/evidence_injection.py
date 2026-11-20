"""Live production review of eight synthetic drafts with predefined faults."""
import asyncio
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from deeptrace.application.assembly import build_harness_runtime
from deeptrace.config import Settings
from deeptrace.observability.model_metrics import run_usage_payload
from deeptrace.responses.fact_review import review_answer

PROJECT=Path(__file__).resolve().parents[3]
OUT=PROJECT/'docs/benchmarks/2026-11-16-four-resume-metrics/evidence-injection'

CASES=[
 {'id':'latency_metric_scope','type':'metric conflation',
  'question':'报告测试服务的p50和p95延迟，并说明测量范围。',
  'sources':['[1] 合成测试记录：服务A在单机实验中的p50延迟为120ms，p95延迟为300ms；不是生产环境SLA。'],
  'draft':'服务A单机实验的p50为120ms，p95也为120ms；不是生产环境SLA。[1]',
  'known_error':'p95被错写为120ms，正确值300ms。','correct_control':'p50为120ms，且为单机实验。'},
 {'id':'strict_capability_scope','type':'feature boundary overgeneralization',
  'question':'哪些合成服务支持JSON格式与strict约束？',
  'sources':['[1] 合成能力表：服务A和服务B均支持JSON输出，但strict约束仅服务A支持。'],
  'draft':'服务A和B均支持JSON输出，服务B也支持strict约束。[1]',
  'known_error':'服务B支持strict错误，strict仅A支持。','correct_control':'A、B均支持JSON。'},
 {'id':'minimum_version','type':'version error',
  'question':'合成AsterSDK的strict参数最低版本和Python运行要求是什么？',
  'sources':['[1] 合成版本记录：AsterSDK的strict参数从2.4版本起提供；该SDK要求Python 3.11及以上。'],
  'draft':'AsterSDK的strict参数从2.1版本起提供，要求Python 3.11及以上。[1]',
  'known_error':'参数最低版本2.1错误，应2.4。','correct_control':'Python最低3.11。'},
 {'id':'opening_exception','type':'exception omitted',
  'question':'合成展馆周一是否开放，以及提前预约窗口是多少天？',
  'sources':['[1] 合成展馆规则：周二至周日09:00-17:00开放，周一闭馆；预约窗口为提前7天。'],
  'draft':'周一09:00-17:00也开放，预约窗口为提前7天。[1]',
  'known_error':'周一开放错误，应周一闭馆。','correct_control':'提前7天预约。'},
 {'id':'object_field_scope','type':'object hierarchy error',
  'question':'在合成接口快照中messages和tenant_id分别属于哪个对象？',
  'sources':['[1] 合成接口快照：run_state对象包含messages字段；runtime_context对象包含tenant_id字段。'],
  'draft':'messages属于runtime_context对象，tenant_id也属于runtime_context对象。[1]',
  'known_error':'messages归属错误，应run_state。','correct_control':'tenant_id属于runtime_context。'},
 {'id':'invented_improvement','type':'unsupported measured benefit',
  'question':'该合成指南是否支持批处理，能否从中得出具体延迟改善比例？',
  'sources':['[1] 合成指南：提供单条调用和批处理两种模式，批处理可一次提交多条任务。本文没有基准测量、耗时数值或延迟改善比例。'],
  'draft':'指南支持批处理，而且已证明批处理延迟降低20%。[1]',
  'known_error':'20%收益无证据，应说明无法得出具体改善比例。','correct_control':'支持批处理，一次可提交多条任务。'},
 {'id':'wrong_citation','type':'source attribution error',
  'question':'合成服务的免费探针额度是多少，SSO是否需要付费？',
  'sources':['[1] 合成额度页：免费方案最多支持10个探针。',
             '[2] 合成许可页：SSO仅在付费方案提供。本页不涉及探针额度。'],
  'draft':'免费方案支持10个探针。[2] SSO需要付费。[2]',
  'known_error':'探针额度误引[2]，应引[1]。','correct_control':'10个探针事实正确，SSO付费且引[2]。'},
 {'id':'free_paid_boundary','type':'free and paid tier conflation',
  'question':'合成存储服务免费保留多久，付费可延长至多久？',
  'sources':['[1] 合成套餐表：免费方案保留历史7天；付费方案可将历史保留延长至30天。'],
  'draft':'免费方案保留历史30天，付费方案也可延长至30天。[1]',
  'known_error':'免费30天错误，应7天。','correct_control':'付费可延长至30天。'},
]

def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

async def main():
 if (OUT/'cases.json').exists():
  raise ValueError('Do not overwrite injection trial records')
 settings=replace(Settings.from_env(),runtime_mode='local',mysql_dsn='',redis_url='',memory_retrieval='lexical')
 save(OUT/'cases.json',CASES)
 save(OUT/'protocol.json',{'model':settings.openai_model,'thinking':settings.model_thinking,
  'method':'Eight synthetic error-injected drafts with one known fault and retained correct control; real production review_answer and actual model calls.',
  'not':'Not eight additional open-ended questions, not naturally generated hallucination-rate measurement, not full-agent retrieval evaluation.',
  'assessment':'Root assistant checks correction, correct-control retention, no wholesale deletion; raw review retained.',
  'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
 bundle=build_harness_runtime(settings,runs_dir=Path(__file__).resolve().parent/'review-runtime')
 try:
  for case in CASES:
   run_id='injection-'+uuid4().hex[:12]
   context=bundle.context_factory(run_id)
   events=[]
   started=time.perf_counter()
   root=OUT/case['id']
   try:
    result=await review_answer(context,question=case['question'],
     constraints=['仅依据给定合成测试资料回答，不引入外部知识；修正错误同时保留正确要点。'],
     content=case['draft'],sources=case['sources'],input_budget=20000,max_content_chars=1200)
    save(root/'review.json',result.model_dump(mode='json'))
    (root/'answer.md').write_text(result.content,encoding='utf-8')
    print(case['id'],'reviewed',flush=True)
   except Exception as exc:
    save(root/'failure.json',{'error_code':getattr(exc,'code',type(exc).__name__)})
    print(case['id'],'FAILED',flush=True)
   finally:
    save(root/'usage.json',run_usage_payload(context))
    save(root/'timing.json',{'elapsed_seconds':time.perf_counter()-started})
    blocked=context.model_gateway.unavailable_reason
    bundle.release_run(run_id)
   if blocked:
    save(OUT/'status.json',{'status':'blocked','reason':blocked})
    return
  save(OUT/'status.json',{'status':'awaiting_controlled_assessment','cases':len(CASES)})
 finally:
  await bundle.aclose()

asyncio.run(main())

from types import SimpleNamespace

from deeptrace.evaluation.review import writer_materials
import pytest


def test_grounding_uses_actual_writer_sources_not_findings_or_other_model_inputs():
    def span(text, time):
        return SimpleNamespace(start_time=time, inputs={"messages":[[{"kwargs":{"content":text}}]]})
    header = '以下是本轮已加载的全部资料（编号即引用标记，禁止引用未列出的来源）：\n\n'
    runs = [span('research finding is not original evidence',1),
            span('question and findings\n'+header+'[1] Original source, condition and limitation.\n只输出 JSON：{"content":"..."}',2)]
    assert writer_materials(runs) == '[1] Original source, condition and limitation.'


@pytest.mark.asyncio
async def test_native_review_rejects_mismatched_reference_before_any_call():
    from deeptrace.evaluation.review import trace_grounded_evaluator
    class Model:
        def with_structured_output(self, schema): return self
    evaluator = trace_grounded_evaluator(object(), Model())
    with pytest.raises(ValueError, match='do not match'):
        await evaluator(SimpleNamespace(reference_example_id='a'),SimpleNamespace(id='b'))


def test_compacted_answer_citations_are_mapped_to_writer_source_urls():
    from deeptrace.evaluation.review import align_citations
    materials = '[1]\n标题：A\n来源：https://example.com/a\n正文摘录：\nsource A\n\n[3]\n标题：B\n来源：https://example.com/b\n正文摘录：\nsource B'
    aligned = align_citations(materials, ['https://example.com/b','https://example.com/a'])
    assert 'Final answer [1] -> https://example.com/b' in aligned
    assert 'Final answer [2] -> https://example.com/a' in aligned
    assert 'original writer labels' in aligned


@pytest.mark.asyncio
async def test_native_review_retries_one_transient_trace_read():
    from deeptrace.evaluation.review import trace_grounded_evaluator
    from langsmith.utils import LangSmithConnectionError
    header='以下是本轮已加载的全部资料（编号即引用标记，禁止引用未列出的来源）：\n\n'
    class Client:
        calls=0
        def flush(self, **kwargs): pass
        def list_runs(self, **kwargs):
            self.calls+=1
            if self.calls==1: raise LangSmithConnectionError('temporary')
            return [SimpleNamespace(start_time=1,inputs={'messages':[[{'kwargs':{'content':header+'evidence\n只输出 JSON：'}}]]})]
    class Model:
        def with_structured_output(self,schema): return self
        async def ainvoke(self,messages): return SimpleNamespace(score=1,groundedness=1,reason='supported')
    client=Client()
    result=await trace_grounded_evaluator(client,Model())(
        SimpleNamespace(reference_example_id='a',trace_id='t',outputs={'answer':'answer','sources':[],
            'source_scope_ok':True,'budget_compliant':True,'status':'completed'}),
        SimpleNamespace(id='a',inputs={'question':'q'},outputs={'answer':'ref'}))
    assert client.calls==2
    assert result['results'][-1]['score'] is True

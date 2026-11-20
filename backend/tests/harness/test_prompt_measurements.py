import pytest
from langchain_core.messages import AIMessage

from deeptrace.harness.model_budget import RunBudgetModelGateway
from deeptrace.harness.prompts import task_messages
from strategies.fixtures import RecordingEventSink


@pytest.mark.asyncio
async def test_prompt_estimates_and_actual_request_parameters_do_not_replace_usage():
    class Model:
        evaluation_identity = {'model':'fixture', 'temperature':0}

        async def invoke(self, **kwargs):
            return AIMessage(content='ok', usage_metadata={
                'input_tokens':42, 'output_tokens':2, 'total_tokens':44})

    sink = RecordingEventSink()
    gateway = RunBudgetModelGateway(Model(), event_sink=sink)
    await gateway.invoke(role='evaluator', messages=task_messages(
        instruction='Check original evidence.', task='question', constraints=[],
        prompt='EVIDENCE_VIEW_JSON:\n{"passages":["source text"]}'))
    started = next(payload for event, payload in sink.events if event == 'model.started')
    completed = next(payload for event, payload in sink.events if event == 'model.completed')
    assert started['prompt_segment_estimates']['evidence'] > 0
    assert started['request_parameters']['temperature'] == 0
    assert completed['input_tokens'] == 42

"""Tier 2 model factories: real OpenAI-compatible model through the gateway.

Kept behind an explicit factory so Tier 1 stays fully offline and the real path
is opt-in via the CLI ``--model real`` flag or ``@pytest.mark.real`` tests.
"""

from __future__ import annotations

from collections.abc import Callable

from deeptrace.eval.experiment import EvaluationLimits
from deeptrace.eval.telemetry import MeteredChatModel, ModelTelemetry, RequestCounter
from deeptrace.harness.model_gateway import ChatModelGateway


class EvalChatModelGateway(ChatModelGateway):
    def __init__(self, model, *, telemetry: ModelTelemetry, timeout_seconds: float):
        super().__init__(model, timeout_seconds=timeout_seconds)
        self.telemetry = telemetry


def build_real_model_factory(
    settings=None,
    *,
    limits: EvaluationLimits | None = None,
    batch_counter: RequestCounter | None = None,
) -> Callable[[], object]:
    """Return a factory producing ``ChatModelGateway`` instances.

    ``ChatModelGateway`` enforces the same context envelope the production
    assembly uses, so Tier 2 exercises the real model boundary.
    """

    from langchain_openai import ChatOpenAI

    from deeptrace.config import Settings

    resolved = settings or Settings.from_env()
    ceilings = limits or EvaluationLimits()
    shared = batch_counter or RequestCounter(
        ceilings.max_batch_provider_attempts or ceilings.max_provider_attempts
    )

    def factory() -> object:
        model = ChatOpenAI(
            api_key=resolved.openai_api_key,
            base_url=resolved.openai_base_url,
            model=resolved.openai_model,
            temperature=0,
            max_retries=0,
            max_tokens=resolved.openai_max_tokens,
        )
        telemetry = ModelTelemetry()
        return EvalChatModelGateway(
            MeteredChatModel(
                model, telemetry, RequestCounter(ceilings.max_provider_attempts), shared
            ),
            telemetry=telemetry,
            timeout_seconds=resolved.planner_timeout_seconds,
        )

    return factory

import pytest
from langchain_core.runnables import RunnableLambda

from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.harness.registry import (
    ResponseRegistration,
    ResponseGraphRegistry,
    StrategyRegistration,
    StrategyRegistry,
)


def _graph() -> RunnableLambda:
    return RunnableLambda(lambda value: value)


def test_registry_resolves_only_canonical_mode_names() -> None:
    registry = StrategyRegistry()
    registration = StrategyRegistration(ResearchMode.WORKFLOW, _graph())

    registry.register(registration)

    assert registry.resolve(ResearchMode.WORKFLOW) is registration
    assert registry.modes() == (ResearchMode.WORKFLOW,)
    with pytest.raises(KeyError, match="mode is not registered"):
        registry.resolve(ResearchMode.PLAN_EXECUTE)


def test_registry_rejects_duplicate_registration() -> None:
    registry = StrategyRegistry()
    registry.register(StrategyRegistration(ResearchMode.WORKFLOW, _graph()))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(StrategyRegistration(ResearchMode.WORKFLOW, _graph()))


@pytest.mark.parametrize("raw_name", ["basic", "deep", "workflow"])
def test_registry_rejects_raw_string_registration(raw_name: str) -> None:
    registry = StrategyRegistry()
    registration = StrategyRegistration(raw_name, _graph())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="registration name must be a ResearchMode"):
        registry.register(registration)


def test_registry_rejects_raw_string_resolution() -> None:
    registry = StrategyRegistry()
    registry.register(StrategyRegistration(ResearchMode.WORKFLOW, _graph()))

    with pytest.raises(TypeError, match="mode name must be a ResearchMode"):
        registry.resolve("workflow")  # type: ignore[arg-type]


def test_response_registry_resolves_canonical_response_modes() -> None:
    registry = ResponseGraphRegistry()
    registration = ResponseRegistration(ResponseMode.ANSWER, _graph())

    registry.register(registration)

    assert registry.resolve(ResponseMode.ANSWER) is registration
    assert registry.modes() == (ResponseMode.ANSWER,)
    with pytest.raises(KeyError, match="response mode is not registered"):
        registry.resolve(ResponseMode.REPORT)


def test_response_registry_rejects_duplicates_and_raw_strings() -> None:
    registry = ResponseGraphRegistry()
    registry.register(ResponseRegistration(ResponseMode.ANSWER, _graph()))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(ResponseRegistration(ResponseMode.ANSWER, _graph()))
    with pytest.raises(TypeError, match="registration name must be a ResponseMode"):
        registry.register(ResponseRegistration("answer", _graph()))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="mode name must be a ResponseMode"):
        registry.resolve("answer")  # type: ignore[arg-type]

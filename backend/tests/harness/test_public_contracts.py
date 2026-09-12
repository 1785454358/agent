from deeptrace.domain import (
    ConversationSummary,
    Finding,
    ResearchInput,
    ResearchOutcome,
    ResearchMode,
    ResponseMode,
)
from deeptrace.harness import (
    HarnessContext,
    HarnessState,
    ResearchStrategyGraph,
    StrategyRegistration,
    StrategyRegistry,
    build_agent_runtime_graph,
)


def test_foundation_exports_are_stable() -> None:
    assert ResearchMode.WORKFLOW.value == "workflow"
    assert ResponseMode.ANSWER.value == "answer"
    assert ConversationSummary.__name__ == "ConversationSummary"
    assert Finding.__name__ == "Finding"
    assert ResearchInput.__name__ == "ResearchInput"
    assert ResearchOutcome.__name__ == "ResearchOutcome"
    assert HarnessContext.__name__ == "HarnessContext"
    assert HarnessState.__name__ == "HarnessState"
    assert ResearchStrategyGraph.__name__ == "ResearchStrategyGraph"
    assert StrategyRegistration.__name__ == "StrategyRegistration"
    assert StrategyRegistry.__name__ == "StrategyRegistry"
    assert callable(build_agent_runtime_graph)

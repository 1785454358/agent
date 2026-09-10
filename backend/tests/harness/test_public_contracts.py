from deeptrace.domain import (
    ConversationSummary,
    Finding,
    ResearchInput,
    ResearchOutcome,
    ResearchProfile,
    ResponseProfile,
)
from deeptrace.harness import (
    HarnessContext,
    HarnessState,
    ProfileRegistration,
    ProfileRegistry,
    build_harness_graph,
)


def test_foundation_exports_are_stable() -> None:
    assert ResearchProfile.WORKFLOW.value == "workflow"
    assert ResponseProfile.ANSWER.value == "answer"
    assert ConversationSummary.__name__ == "ConversationSummary"
    assert Finding.__name__ == "Finding"
    assert ResearchInput.__name__ == "ResearchInput"
    assert ResearchOutcome.__name__ == "ResearchOutcome"
    assert HarnessContext.__name__ == "HarnessContext"
    assert HarnessState.__name__ == "HarnessState"
    assert ProfileRegistration.__name__ == "ProfileRegistration"
    assert ProfileRegistry.__name__ == "ProfileRegistry"
    assert callable(build_harness_graph)

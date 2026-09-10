import pytest
from langchain_core.runnables import RunnableLambda

from deeptrace.domain import ResearchProfile
from deeptrace.harness.registry import ProfileRegistration, ProfileRegistry


def _graph() -> RunnableLambda:
    return RunnableLambda(lambda value: value)


def test_registry_resolves_only_canonical_profile_names() -> None:
    registry = ProfileRegistry()
    registration = ProfileRegistration(ResearchProfile.WORKFLOW, _graph())

    registry.register(registration)

    assert registry.resolve(ResearchProfile.WORKFLOW) is registration
    assert registry.profiles() == (ResearchProfile.WORKFLOW,)
    with pytest.raises(KeyError, match="profile is not registered"):
        registry.resolve(ResearchProfile.PLAN_EXECUTE)


def test_registry_rejects_duplicate_registration() -> None:
    registry = ProfileRegistry()
    registry.register(ProfileRegistration(ResearchProfile.WORKFLOW, _graph()))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(ProfileRegistration(ResearchProfile.WORKFLOW, _graph()))


@pytest.mark.parametrize("raw_name", ["basic", "deep", "workflow"])
def test_registry_rejects_raw_string_registration(raw_name: str) -> None:
    registry = ProfileRegistry()
    registration = ProfileRegistration(raw_name, _graph())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="registration name must be a ResearchProfile"):
        registry.register(registration)


def test_registry_rejects_raw_string_resolution() -> None:
    registry = ProfileRegistry()
    registry.register(ProfileRegistration(ResearchProfile.WORKFLOW, _graph()))

    with pytest.raises(TypeError, match="profile name must be a ResearchProfile"):
        registry.resolve("workflow")  # type: ignore[arg-type]

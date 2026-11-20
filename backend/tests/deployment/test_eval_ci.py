"""Cloud evaluations are opt-in; ordinary CI never requires provider secrets."""
from pathlib import Path
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]

def test_langsmith_evaluation_is_manual_and_separate_from_offline_ci():
    workflows = ROOT / ".github/workflows"
    if not workflows.exists():
        pytest.skip("workflows are not copied into the test image")
    cloud = yaml.safe_load((workflows / "langsmith-evaluation.yml").read_text())
    triggers = cloud.get("on", cloud.get(True))
    assert set(triggers) == {"workflow_dispatch"}
    assert "LANGSMITH_API_KEY" in cloud["jobs"]["evaluate"]["env"]
    offline = (workflows / "ci.yml").read_text()
    assert "secrets." not in offline
    assert "backend/evaluation" not in offline

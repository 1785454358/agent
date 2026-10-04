"""Validate CI input boundaries; not evidence of a remote CI run."""

from pathlib import Path

import pytest
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ROOT = BACKEND_ROOT.parent


def test_scorer_ci_has_isolated_build_context_without_secret_inputs():
    workflow = ROOT / ".github/workflows/ci.yml"
    if not workflow.exists():
        pytest.skip("workflow is not copied into the production test image")
    jobs = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]
    assert "evaluation" in jobs
    job = jobs["evaluation"]
    build = next(
        s
        for s in job["steps"]
        if s.get("uses", "").startswith("docker/build-push-action")
    )
    assert build["with"]["context"] == "backend/evaluation"
    assert build["with"]["file"] == "backend/evaluation/Dockerfile"
    assert build["with"]["push"] is False
    assert "secrets." not in str(job)
    assert "build-args" not in build["with"]
    assert "secrets" not in build["with"]


def test_scorer_image_never_installs_production_and_tests_without_network():
    path = BACKEND_ROOT / "evaluation/Dockerfile"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    copies = [l.split() for l in lines if l.startswith("COPY ")]
    assert [l[1:-1] for l in copies] == [
        ["requirements.lock"],
        ["ragas_quality.py", "ragas_tools.py"],
        ["data"],
        ["tests"],
    ]
    runs = [l for l in lines if l.startswith("RUN ")]
    assert any("pip install" in l and "-r requirements.lock" in l for l in runs)
    assert all("--network=none" in l for l in runs if "pytest" in l)
    assert any("pytest tests" in l for l in runs)
    assert not any("uv sync" in l or "deeptrace" in l for l in runs)

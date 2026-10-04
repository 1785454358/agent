import json

import pytest


def test_saved_failure_is_complete_and_resume_does_not_overwrite(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore

    record = {
        "run_id": "../unsafe/id",
        "status": "failed",
        "answer": "a" * 5000,
        "system_error": "TimeoutError",
    }
    with ExperimentStore(tmp_path, {"schema_version": 2, "model": "a"}) as store:
        store.claim(record["run_id"])
        store.save(record)
        with pytest.raises(ValueError, match="already"):
            store.claim(record["run_id"])
        assert store.load(record["run_id"])["answer"] == "a" * 5000
    with ExperimentStore(
        tmp_path, {"schema_version": 2, "model": "a"}, resume=True
    ) as store:
        assert store.load(record["run_id"])["status"] == "failed"
    assert len(list((tmp_path / "samples").glob("*.json"))) == 1
    assert not (tmp_path.parent / "unsafe").exists()


def test_resume_rejects_changed_identity_and_new_mode_refuses_overwrite(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore

    with ExperimentStore(tmp_path, {"schema_version": 2, "model": "a"}):
        pass
    for manifest, resume, message in [
        ({"schema_version": 2, "model": "b"}, True, "identity"),
        ({"schema_version": 2, "model": "a"}, False, "exists"),
    ]:
        with pytest.raises(ValueError, match=message):
            with ExperimentStore(tmp_path, manifest, resume=resume):
                pass


def test_inflight_claim_cannot_be_automatically_reissued(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore

    with ExperimentStore(tmp_path, {"schema_version": 2}) as store:
        store.claim("r")
    with ExperimentStore(tmp_path, {"schema_version": 2}, resume=True) as store:
        with pytest.raises(ValueError, match="incomplete"):
            store.load("r")
        with pytest.raises(ValueError, match="already"):
            store.claim("r")


def test_modified_record_is_not_silently_used_for_resume(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore

    with ExperimentStore(tmp_path, {"schema_version": 2}) as store:
        store.claim("r")
        store.save({"run_id": "r", "status": "completed"})
    path = next((tmp_path / "samples").glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["record"]["status"] = "failed"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with ExperimentStore(tmp_path, {"schema_version": 2}, resume=True) as store:
        with pytest.raises(ValueError, match="integrity"):
            store.load("r")


def test_two_writers_are_rejected_before_work(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore

    with ExperimentStore(tmp_path, {"schema_version": 2}):
        with pytest.raises(ValueError, match="locked"):
            with ExperimentStore(tmp_path, {"schema_version": 2}, resume=True):
                pass


def test_unrelated_nonempty_directory_is_preserved(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore

    original = tmp_path / "user-data.txt"
    original.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        with ExperimentStore(tmp_path, {"schema_version": 2}):
            pass
    assert original.read_text(encoding="utf-8") == "keep"


def test_save_requires_matching_claim(tmp_path):
    from deeptrace.eval.artifacts import ExperimentStore

    with ExperimentStore(tmp_path, {"schema_version": 2}) as store:
        with pytest.raises(ValueError, match="claim"):
            store.save({"run_id": "r", "status": "completed"})

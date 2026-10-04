"""Single-writer local experiment journal with integrity-checked resume."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from deeptrace.eval.trajectory import _content_hash


def atomic_json(path: Path, payload: dict | list) -> None:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2
    ).encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class ExperimentStore:
    """A crash claim is ambiguous: never silently repeat potentially paid work.

    The exclusive lock is removed on normal exit. Following a hard process
    crash a human must review the lock/claim before resuming this experiment.
    """

    def __init__(self, path: Path, manifest: dict, *, resume: bool = False):
        self.path = Path(path).resolve()
        self.manifest = manifest
        self.identity = _content_hash(manifest)
        self.resume = resume
        self._locked = False

    def __enter__(self):
        self.path.mkdir(parents=True, exist_ok=True)
        lock = self.path / ".writer.lock"
        try:
            with lock.open("x", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            self._locked = True
        except FileExistsError as exc:
            raise ValueError("experiment locked; inspect interrupted writer") from exc
        try:
            manifest_path = self.path / "manifest.json"
            if manifest_path.exists():
                if not self.resume:
                    raise ValueError(
                        "experiment already exists; use resume or new path"
                    )
                saved = self._read(manifest_path)
                if (
                    saved.get("identity_sha256") != self.identity
                    or _content_hash(saved.get("manifest")) != self.identity
                ):
                    raise ValueError("experiment identity mismatch")
            else:
                if self.resume:
                    raise ValueError("resume requires an existing manifest")
                if any(p != lock for p in self.path.iterdir()):
                    raise ValueError("new experiment requires an empty directory")
                atomic_json(
                    manifest_path,
                    {
                        "identity_sha256": self.identity,
                        "started_at": datetime.now(UTC).isoformat(),
                        "manifest": self.manifest,
                    },
                )
            for name in ("samples", "claims"):
                directory = self.path / name
                if directory.is_symlink():
                    raise ValueError("experiment directories cannot be symlinks")
                directory.mkdir(exist_ok=True)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self._locked:
            (self.path / ".writer.lock").unlink(missing_ok=True)
            self._locked = False

    def _require_lock(self):
        if not self._locked:
            raise ValueError("experiment must be opened with a writer lock")

    def _paths(self, run_id: str) -> tuple[Path, Path]:
        name = _content_hash(run_id) + ".json"
        return self.path / "samples" / name, self.path / "claims" / name

    @staticmethod
    def _read(path: Path) -> dict:
        if path.is_symlink():
            raise ValueError("experiment files cannot be symlinks")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("experiment integrity: invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("experiment integrity: object required")  # noqa: TRY004 - uniform corruption contract.
        return payload

    def load(self, run_id: str) -> dict | None:
        self._require_lock()
        saved, claim = self._paths(run_id)
        if saved.exists():
            payload = self._read(saved)
            record = payload.get("record")
            if (
                not isinstance(record, dict)
                or record.get("run_id") != run_id
                or payload.get("record_sha256") != _content_hash(record)
                or payload.get("identity_sha256") != self.identity
            ):
                raise ValueError("experiment integrity: record mismatch")
            return record
        if claim.exists():
            raise ValueError("incomplete run; inspect before issuing more requests")
        return None

    def claim(self, run_id: str) -> None:
        self._require_lock()
        saved, claim = self._paths(run_id)
        if saved.exists() or claim.exists():
            raise ValueError("run already claimed or saved")
        atomic_json(claim, {"run_id": run_id, "identity_sha256": self.identity})

    def save(self, record: dict) -> None:
        self._require_lock()
        saved, claim = self._paths(record["run_id"])
        if saved.exists():
            raise ValueError("run already saved")
        if not claim.exists() or self._read(claim) != {
            "run_id": record["run_id"],
            "identity_sha256": self.identity,
        }:
            raise ValueError("matching run claim required")
        atomic_json(
            saved,
            {
                "identity_sha256": self.identity,
                "record_sha256": _content_hash(record),
                "record": record,
            },
        )
        claim.unlink()

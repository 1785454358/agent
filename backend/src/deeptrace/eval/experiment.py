"""Explicit, credential-free identity for a reproducible experiment."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
from dataclasses import asdict
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from deeptrace.eval.trajectory import _content_hash, _git_identity
from deeptrace.harness.policies.agent_context import (
    RESEARCH_CONTEXT_SOFT_TOKENS,
    RESEARCH_RECENT_GROUPS,
)
from deeptrace.harness.token_budget import TokenBudgetConfig


class EvaluationLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_model_calls: int = Field(default=40, gt=0)
    max_tool_calls: int = Field(default=24, gt=0)
    max_provider_attempts: int = Field(default=80, gt=0)
    max_batch_model_calls: int | None = Field(default=None, gt=0)
    max_batch_provider_attempts: int | None = Field(default=None, gt=0)
    run_timeout_seconds: int = Field(default=240, gt=0)
    agent_iterations: int = Field(default=12, gt=0)


class ModelIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["scripted", "real"]
    name: str = Field(min_length=1)
    provider: str | None = None
    endpoint_sha256: str | None = None
    temperature: float = 0.0
    max_output_tokens: int | None = Field(default=None, gt=0)
    transport_attempts: int = Field(default=2, gt=0)
    context_tokens: int | None = Field(default=None, gt=0)
    request_timeout_seconds: float | None = Field(default=None, gt=0)


def provider_origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("provider must have an HTTP origin")
    hostname = parsed.hostname
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{hostname}{port}"


def provider_endpoint_hash(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("provider credentials must not be embedded in endpoint URL")
    return _content_hash(provider_origin(url) + parsed.path)


def source_identity(project_root: Path) -> dict[str, str]:
    """Hash untracked implementation too; never walk credentials or run output."""
    files = {}
    for directory in ("backend/src/deeptrace", "backend/evaluation"):
        root = project_root / directory
        if root.exists():
            for path in sorted(root.rglob("*.py")):
                if "__pycache__" not in path.parts and not path.is_symlink():
                    files[path.relative_to(project_root).as_posix()] = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
    data_root = project_root / "backend/src/deeptrace/eval/data"
    if data_root.exists():
        for path in sorted(data_root.rglob("*")):
            if (
                path.is_file()
                and not path.is_symlink()
                and path.suffix in {".json", ".jsonl", ".txt", ".md", ".mdx"}
            ):
                files[path.relative_to(project_root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    for name in (
        "backend/pyproject.toml",
        "backend/uv.lock",
        "backend/evaluation/requirements.in",
        "backend/evaluation/requirements.lock",
    ):
        path = project_root / name
        if path.is_file() and not path.is_symlink():
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def build_manifest(
    questions,
    corpus,
    *,
    model: ModelIdentity,
    modes: list[str],
    repeats: int,
    run_prefix: str,
    limits: EvaluationLimits,
    project_root: Path | None = None,
    response_mode: str | None = None,
    response_max_content_chars: int | None = None,
    live_retrieval: dict | None = None,
) -> dict:
    if (corpus is None) != (live_retrieval is not None):
        raise ValueError("explicit live retrieval identity required without corpus")
    allowed = {
        "search",
        "fetch",
        "search_depth",
        "max_results",
        "min_chars",
        "min_tokens",
        "max_page_chars",
        "allow_benchmark_dns_proxy",
    }
    if live_retrieval is not None and (
        not live_retrieval or set(live_retrieval) - allowed
    ):
        raise ValueError("invalid live retrieval identity")
    if not questions or repeats < 1 or not run_prefix or not modes:
        raise ValueError("nonempty experiment and positive repeats required")
    if len(modes) != len(set(modes)):
        raise ValueError("modes must be unique")
    if response_max_content_chars is not None and (
        type(response_max_content_chars) is not int or response_max_content_chars < 1
    ):
        raise ValueError("response_max_content_chars must be a positive integer")
    sample_ids = [
        f"{run_prefix}-{q.id}-{mode}" + (f"-r{index}" if repeats > 1 else "")
        for q in questions
        for mode in modes
        for index in range(repeats)
    ]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("sample IDs must be unique")
    root = project_root or Path(__file__).resolve().parents[4]
    versions = {}
    for package in (
        "pydantic",
        "langgraph",
        "langchain-core",
        "langchain-openai",
        "openai",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "schema_version": 2,
        "dataset_sha256": _content_hash([q.model_dump(mode="json") for q in questions]),
        "corpus_sha256": None
        if corpus is None
        else _content_hash([d.model_dump(mode="json") for d in corpus.documents()]),
        "source_files": source_identity(root),
        "python_version": platform.python_version(),
        "installed_versions": versions,
        "context_allocator": asdict(TokenBudgetConfig()),
        "research_context_policy": {
            "soft_input_tokens": RESEARCH_CONTEXT_SOFT_TOKENS,
            "recent_exchange_groups": RESEARCH_RECENT_GROUPS,
            "retained_actual_read_previews": 3,
        },
        "evidence_policy": "actual-url-coherent-read-raw-evaluation-v1",
        "model": model.model_dump(mode="json"),
        "tools_backend": "live_web"
        if live_retrieval is not None
        else "frozen_local_corpus",
        **({"live_retrieval": live_retrieval} if live_retrieval is not None else {}),
        "memory_backend": "disabled",
        "modes": modes,
        "repeats": repeats,
        "run_prefix": run_prefix,
        "response_mode": response_mode,
        "response_max_content_chars": response_max_content_chars,
        "limits": limits.model_dump(mode="json"),
        "sample_ids": sample_ids,
        **_git_identity(),
    }

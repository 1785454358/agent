"""Controlled memory contracts through the application and a disposable SQL store.

This runner intentionally accepts only the scripted gateway. It is not a real
model preference-compliance benchmark; references are used after invocation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deeptrace.application.research import (
    ApplicationResearchRequest,
    ResearchApplicationService,
)
from deeptrace.domain import ResearchMode
from deeptrace.eval.artifacts import ExperimentStore, atomic_json
from deeptrace.eval.dataset import CorpusDocument
from deeptrace.eval.env import Corpus, build_eval_context
from deeptrace.eval.experiment import EvaluationLimits, ModelIdentity, build_manifest
from deeptrace.eval.runner import build_eval_graph
from deeptrace.eval.scripted import ScriptedResearchModel
from deeptrace.eval.telemetry import RequestCounter
from deeptrace.eval.trajectory import _content_hash
from deeptrace.harness.memory.forget import apply_lifecycle, forget
from deeptrace.harness.memory.recall import eligible_memory
from deeptrace.persistence.database import create_session_factory
from deeptrace.persistence.memory_store import SqlAlchemyMemoryStore
from deeptrace.persistence.orm import Base

ASSET = Path(__file__).parent / "data" / "memory" / "lifecycle-v2.json"
PRIORITY_RULE = "本轮用户明确要求优先于历史偏好"


class MemoryStage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    action: Literal["turn", "advance", "forget"] = "turn"
    question: str = Field(default="", max_length=2000)
    user_id: str = Field(default="memory-eval-user", min_length=1, max_length=80)
    workspace_id: str = Field(
        default="memory-eval-workspace", min_length=1, max_length=80
    )
    days: int = Field(default=0, ge=0, le=365)
    target_content: str = Field(default="", max_length=2000)
    probe: bool = False
    expected_contents: list[str] = Field(default_factory=list, max_length=10)
    forbidden_contents: list[str] = Field(default_factory=list, max_length=10)
    gold_note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_action(self):
        if self.action == "turn" and not self.question.strip():
            raise ValueError("turn question required")
        if self.action == "advance" and self.days < 1:
            raise ValueError("positive advance required")
        if self.action == "forget" and not self.target_content:
            raise ValueError("forget target required")
        if self.action != "turn" and (self.probe or self.question):
            raise ValueError("only turns can be probes")
        if any(
            not s or len(s) > 2000
            for s in self.expected_contents + self.forbidden_contents
        ):
            raise ValueError("bounded nonempty reference content required")
        if set(self.expected_contents) & set(self.forbidden_contents):
            raise ValueError("contradictory memory references")
        return self


class MemoryEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    category: str = Field(min_length=1, max_length=80)
    stages: list[MemoryStage] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def has_probe(self):
        if not any(s.probe for s in self.stages):
            raise ValueError("episode must have a recall probe")
        return self


def load_episodes(path: Path = ASSET) -> list[MemoryEpisode]:
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("memory asset exceeds 1 MiB")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not 1 <= len(payload) <= 100:
        raise ValueError("1..100 episodes required")
    episodes = [MemoryEpisode.model_validate(row) for row in payload]
    if len({e.id for e in episodes}) != len(episodes):
        raise ValueError("duplicate memory episode")
    return episodes


@dataclass
class MemoryClock:
    instant: datetime = datetime(2026, 10, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self.instant


def memory_corpus() -> Corpus:
    return Corpus(
        [
            CorpusDocument(
                doc_id="controlled-memory-background",
                url="https://example.org/memory-eval/background",
                title="Controlled memory lifecycle fixture",
                body="This is a synthetic background fixture, not a factual benchmark. "
                "分析资料结论 请用英文分析资料结论 资料结论的背景 "
                "研究资料背景 重新研究资料结论",
            )
        ]
    )


async def _stored(store, namespaces):
    records = []
    for namespace in sorted(namespaces):
        records.extend(await store.list_namespace(namespace, include_inactive=True))
    return sorted(records, key=lambda r: (r.namespace, r.identity(), r.version))


async def run_memory_episode(
    episode: MemoryEpisode,
    *,
    enabled: bool,
    model_factory=ScriptedResearchModel,
    limits: EvaluationLimits | None = None,
) -> dict:
    """Shared episode limits; no previous thread messages at any probe.

    The factory is called once, not once per turn. There are no Provider
    attempts in this scripted-only slice; do not infer model quality from it.
    """
    if not isinstance(episode, MemoryEpisode) or type(enabled) is not bool:
        raise ValueError("typed episode and boolean memory switch required")
    limits = limits or EvaluationLimits()
    model = model_factory()
    if not isinstance(model, ScriptedResearchModel):
        raise ValueError(
            "memory runner is scripted-only; real calibration "
            "requires a separate manifest and budget"
        )
    model_counter = RequestCounter(limits.max_model_calls)
    tool_counter = RequestCounter(limits.max_tool_calls)
    clock, corpus = MemoryClock(), memory_corpus()
    namespaces = {
        (s, owner, kind)
        for stage in episode.stages
        for s, owner, kind in (
            ("user", stage.user_id, "preferences"),
            ("workspace", stage.workspace_id, "facts"),
        )
    }
    result = {
        "run_id": f"memory-{episode.id}-{'on' if enabled else 'off'}",
        "episode_id": episode.id,
        "category": episode.category,
        "memory_enabled": enabled,
        "memory_backend": "sqlite_lexical" if enabled else "disabled",
        "data_kind": "controlled_scenario",
        "model_kind": "scripted",
        "status": "completed",
        "turns": [],
        "actions": [],
        "violations": [],
        "cross_namespace_hits": 0,
        "provider_attempts": 0,
        "answer_quality": None,
    }
    with tempfile.TemporaryDirectory(prefix="deeptrace-memory-eval-") as directory:
        database = (Path(directory) / "memory.db").as_posix()
        engine, sessions = create_session_factory(f"sqlite+aiosqlite:///{database}")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            store = SqlAlchemyMemoryStore(sessions)
            graph = build_eval_graph(max_iterations=limits.agent_iterations)
            application = ResearchApplicationService(graph)
            async with asyncio.timeout(limits.run_timeout_seconds):
                for index, stage in enumerate(episode.stages):
                    existing = await _stored(store, namespaces)
                    if stage.action == "advance":
                        clock.instant += timedelta(days=stage.days)
                        transitions = apply_lifecycle(existing, now=clock.now())
                        changed = []
                        for record in existing:
                            status = transitions[record.id or record.identity()]
                            if status is not None:
                                await store.set_status(
                                    record.namespace, record.identity(), status
                                )
                                changed.append(
                                    {"id": record.id, "status": status.value}
                                )
                        result["actions"].append(
                            {
                                "index": index,
                                "action": "advance",
                                "now": clock.now().isoformat(),
                                "transitions": changed,
                            }
                        )
                        continue
                    if stage.action == "forget":
                        targets = [
                            r
                            for r in existing
                            if r.content == stage.target_content
                            and r.namespace == ("user", stage.user_id, "preferences")
                        ]
                        for target in targets:
                            await forget(store, target)
                        result["actions"].append(
                            {
                                "index": index,
                                "action": "forget",
                                "matched_records": len(targets),
                            }
                        )
                        if enabled and not targets:
                            result["violations"].append(
                                f"stage_{index}:forget_target_missing"
                            )
                        continue
                    run_id = f"{result['run_id']}-{index}"
                    thread_id = f"{run_id}-fresh-thread"
                    config = {
                        "configurable": {"thread_id": thread_id},
                        "recursion_limit": 200,
                    }
                    before = await graph.aget_state(config)
                    prior_messages = [
                        str(m.content)
                        for m in before.values.get("conversation", {}).get(
                            "messages", []
                        )
                    ]
                    env = build_eval_context(
                        corpus,
                        model_gateway=model,
                        run_id=run_id,
                        workspace_id=stage.workspace_id,
                        limits=limits,
                        batch_model_counter=model_counter,
                        tool_counter=tool_counter,
                        memory_enabled=False,
                        response_max_content_chars=600,
                    )
                    context = replace(
                        env.context,
                        user_id=stage.user_id,
                        clock=clock,
                        memory_store=store if enabled else None,
                    )
                    outcome = await application.invoke(
                        ApplicationResearchRequest(
                            run_id=run_id,
                            thread_id=thread_id,
                            question=stage.question,
                            mode=ResearchMode.WORKFLOW,
                        ),
                        config=config,
                        context=context,
                    )
                    snapshot = await graph.aget_state(config)
                    turn = snapshot.values["turn"]
                    memories = turn.get("recalled_memories", [])
                    content = {m["content"] for m in memories}
                    known = {r.id: r for r in existing}
                    allowed = {
                        ("user", stage.user_id, "preferences"),
                        ("workspace", stage.workspace_id, "facts"),
                    }
                    foreign = sum(
                        m["id"] not in known or known[m["id"]].namespace not in allowed
                        for m in memories
                    )
                    hits = sum(c in content for c in stage.expected_contents)
                    forbidden = sorted(content & set(stage.forbidden_contents))
                    trajectory = env.trajectory.snapshot(full=True)
                    model_inputs = "\n".join(
                        str(message["content"])
                        for call in trajectory["model_messages"]
                        for message in call["messages"]
                    )
                    checks = {}
                    if stage.probe:
                        checks = {
                            "fresh_thread": not prior_messages,
                            "namespace_isolated": foreign == 0,
                            "expected_memory_recalled": hits
                            == len(stage.expected_contents),
                            "forbidden_memory_absent": not forbidden,
                            "eligible_memory_only": all(
                                m["id"] in known
                                and eligible_memory(known[m["id"]], now=clock.now())
                                for m in memories
                            ),
                            "recalled_content_in_model_inputs": all(
                                m["content"] in model_inputs for m in memories
                            ),
                            "disabled_memory_empty": enabled or not memories,
                            "current_request_priority_visible": PRIORITY_RULE
                            in model_inputs,
                        }
                        # Missing positive recall in the off variant is the comparison,
                        # not a broken memory-disabled contract.
                        for name, passed in checks.items():
                            if not passed and (
                                enabled or name != "expected_memory_recalled"
                            ):
                                result["violations"].append(f"stage_{index}:{name}")
                    result["cross_namespace_hits"] += foreign
                    response = outcome.response_outcome
                    accepted_write = response is not None and (
                        response.partial_reason == "memory_updated"
                        or (
                            not enabled
                            and response.partial_reason == "memory_unavailable"
                        )
                    )
                    if outcome.status != "completed" and not accepted_write:
                        result["status"] = "partial"
                        result["violations"].append(
                            f"stage_{index}:application_partial"
                        )
                    result["turns"].append(
                        {
                            "stage_index": index,
                            "thread_id": thread_id,
                            "question": stage.question,
                            "user_id": stage.user_id,
                            "workspace_id": stage.workspace_id,
                            "now": clock.now().isoformat(),
                            "prior_messages": prior_messages,
                            "status": outcome.status,
                            "response_partial_reason": response.partial_reason
                            if response
                            else None,
                            "answer": response.content if response else "",
                            "recalled_memories": memories,
                            "stored_before": [
                                r.model_dump(mode="json") for r in existing
                            ],
                            "probe": stage.probe,
                            "target_count": len(stage.expected_contents),
                            "target_hits": hits,
                            "forbidden_hits": forbidden,
                            "checks": checks,
                            "trajectory": trajectory,
                        }
                    )
            result["stored_memories"] = [
                r.model_dump(mode="json") for r in await _stored(store, namespaces)
            ]
        finally:
            await engine.dispose()
    result.update(model_calls=model_counter.used, tool_calls=tool_counter.used)
    return result


def render_memory_report(records: list[dict]) -> str:
    lines = [
        "# Controlled memory lifecycle evaluation",
        "",
        "Scripted model / temporary SQLite / lexical recall. "
        "Not real-model answer quality.",
        "",
        "| memory | episodes | violations | "
        "positive recall hits / targets | cross-namespace hits |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for enabled in (False, True):
        rows = [r for r in records if r["memory_enabled"] is enabled]
        probes = [t for r in rows for t in r["turns"] if t["probe"]]
        lines.append(
            f"| {'on' if enabled else 'off'} | {len(rows)} | "
            f"{sum(len(r['violations']) for r in rows)} | "
            f"{sum(t['target_hits'] for t in probes)} / "
            f"{sum(t['target_count'] for t in probes)} | "
            f"{sum(r['cross_namespace_hits'] for r in rows)} |"
        )
    lines.extend(
        [
            "",
            "Full checks, stored versions/status and model messages "
            "are in memory_records.json.",
            "Positive misses with memory off remain visible but are not "
            "runtime contract violations. No semantic recall or "
            "preference-compliance score is claimed.",
        ]
    )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--episodes", type=Path, default=ASSET)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        episodes, limits = load_episodes(args.episodes), EvaluationLimits()
        manifest = build_manifest(
            episodes,
            memory_corpus(),
            model=ModelIdentity(kind="scripted", name="ScriptedResearchModel"),
            modes=["on", "off"],
            repeats=1,
            run_prefix="memory",
            limits=limits,
            response_max_content_chars=600,
        )
        manifest.update(
            experiment_type="memory_lifecycle",
            data_kind="controlled_scenario",
            memory_backend="sqlite_lexical",
            clock_start=MemoryClock().now().isoformat(),
            episode_ids=[e.id for e in episodes],
            execution_order=["off", "on"],
        )
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["RAGAS_DO_NOT_TRACK"] = "true"
        records = []
        with ExperimentStore(args.out, manifest, resume=args.resume) as journal:
            for episode in episodes:
                for enabled in (False, True):
                    run_id = f"memory-{episode.id}-{'on' if enabled else 'off'}"
                    record = journal.load(run_id)
                    if record is None:
                        journal.claim(run_id)
                        record = asyncio.run(
                            run_memory_episode(episode, enabled=enabled, limits=limits)
                        )
                        journal.save(record)
                    records.append(record)
            atomic_json(journal.path / "memory_records.json", records)
            atomic_json(
                journal.path / "memory_summary.json",
                {
                    "identity_sha256": _content_hash(manifest),
                    "episodes": len(episodes),
                    "variants": len(records),
                    "violations": sum(len(r["violations"]) for r in records),
                    "answer_quality": None,
                },
            )
            (journal.path / "report.md").write_text(
                render_memory_report(records), encoding="utf-8"
            )
        return int(any(r["violations"] for r in records))
    except (ValueError, OSError, TimeoutError) as exc:
        parser.error(
            f"memory evaluation aborted: {type(exc).__name__}; "
            "inspect claims before resuming"
        )


if __name__ == "__main__":
    raise SystemExit(main())

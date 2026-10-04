"""Markdown rendering for a score report."""

from __future__ import annotations

from deeptrace.eval.scoring import ScoreReport

_HEADERS = [
    "mode",
    "runs",
    "completed",
    "answered",
    "gold_coverage",
    "evidence",
    "citation_ok",
    "steps",
    "tools",
    "models",
    "wall_ms",
]


def render_markdown(report: ScoreReport, *, tools_backend="frozen_local_corpus") -> str:
    live = tools_backend == "live_web"
    lines = [
        "# Research mode evaluation (live web)"
        if live
        else "# Research mode baseline (offline corpus)",
        "",
        f"- questions: {report.questions}",
        f"- runs: {report.runs}",
        "",
        "| " + " | ".join(_HEADERS) + " |",
        "| " + " | ".join("---" for _ in _HEADERS) + " |",
    ]
    for mode in report.modes:
        lines.append(
            "| "
            + " | ".join(
                [
                    mode.mode,
                    str(mode.runs),
                    str(mode.completed),
                    str(mode.answered),
                    f"{mode.mean_gold_coverage:.3f}",
                    f"{mode.mean_evidence_count:.2f}",
                    f"{mode.citation_validity:.3f}",
                    f"{mode.mean_executed_steps:.2f}",
                    f"{mode.mean_tool_calls:.2f}",
                    f"{mode.mean_model_calls:.2f}",
                    f"{mode.mean_wall_ms:.1f}",
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("Termination reasons:")
    for mode in report.modes:
        detail = ", ".join(
            f"{reason}={count}" for reason, count in mode.termination_reasons.items()
        )
        lines.append(f"- {mode.mode}: {detail or '(none)'}")

    if any(mode.judge_attempted for mode in report.modes):
        judge_headers = [
            "mode",
            "judged",
            "attempted",
            "failed",
            "faithfulness",
            "correctness",
            "coverage",
            "citation",
            "coherence",
        ]
        lines.append("")
        lines.append("legacy_custom LLM-as-judge (1-5; missing/failed scores are N/A):")
        lines.append("| " + " | ".join(judge_headers) + " |")
        lines.append("| " + " | ".join("---" for _ in judge_headers) + " |")
        for mode in report.modes:
            lines.append(
                "| "
                + " | ".join(
                    [
                        mode.mode,
                        str(mode.judge_runs),
                        str(mode.judge_attempted),
                        str(mode.judge_failures),
                        *[
                            "N/A" if value is None else f"{value:.2f}"
                            for value in (
                                mode.mean_faithfulness,
                                mode.mean_answer_correctness,
                                mode.mean_source_coverage,
                                mode.mean_citation_accuracy,
                                mode.mean_coherence,
                            )
                        ],
                    ]
                )
                + " |"
            )

    lines.append("")
    lines.append(
        "These are execution and live-web retrieval/citation-validity measurements, "
        "not a research-quality verdict. Independent quality scoring and "
        "sufficient paired samples are required."
        if live
        else "These are execution and retrieval/citation-validity measurements on a "
        "frozen local corpus, not a research-quality verdict. Synthetic smoke data "
        "is for plumbing only; real-source calibration also needs independent "
        "quality scoring and sufficient paired samples."
    )
    return "\n".join(lines)

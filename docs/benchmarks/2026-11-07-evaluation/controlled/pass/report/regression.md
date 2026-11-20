# Agent regression: PASS

Policy: synthetic-gate-demonstration-only (`70867483ee0baa6e256e1e1686f7e71beac9f74dc9f1bcfcf403f5c7bade39c8`).
Strategies: workflow -> workflow.

The decision checks configured observed tolerances. It is not proof of statistical non-inferiority or an absolute quality certification.

| dataset / split / kind | check | verdict | delta or ratio | paired tasks | coverage (old/new) | reason |
| --- | --- | --- | ---: | ---: | --- | --- |
| controlled-gate-fixture / dev / synthetic | completion_rate | pass | 0.0 | N/A | N/A / N/A | operational rate only; not semantic task success |
| controlled-gate-fixture / dev / synthetic | answered_rate | pass | 0.0 | N/A | N/A / N/A | operational rate only; not semantic task success |
| controlled-gate-fixture / dev / synthetic | factual_correctness | pass | 0.125 | 2 | 1.0 / 1.0 | observed quality drop is within policy tolerance |

## Task changes

| dataset / split | metric | question | delta | change |
| --- | --- | --- | ---: | --- |
| controlled-gate-fixture / dev | factual_correctness | q0 | 0.25 | improved |
| controlled-gate-fixture / dev | factual_correctness | q1 | 0.0 | unchanged |

## Original trials

Full answers, evidence and trajectories remain in the source quality exports.

| side | question | repeat | original run ID | status |
| --- | --- | ---: | --- | --- |
| baseline | q0 | 0 | old-q0-0 | completed |
| baseline | q1 | 0 | old-q1-0 | completed |
| candidate | q0 | 0 | pass-q0-0 | completed |
| candidate | q1 | 0 | pass-q1-0 | completed |

## Resources

| dataset / split / kind | side | runs | p50 ms | p95 ms | input tokens | output tokens | provider attempts |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| controlled-gate-fixture / dev / synthetic | baseline | 2 | 100.0 | 100.0 | 100 | 20 | 2 |
| controlled-gate-fixture / dev / synthetic | candidate | 2 | 100.0 | 100.0 | 100 | 20 | 2 |

CI95, all-output/completed-only views, observed usage subtotals and complete scoring provenance are in regression.json.

## Source artifacts

- baseline: D:\Dev\Projects\agent_new\docs\benchmarks\2026-11-07-evaluation\controlled\baseline\quality_eval.json
- candidate: D:\Dev\Projects\agent_new\docs\benchmarks\2026-11-07-evaluation\controlled\pass\candidate\quality_eval.json
- metadata: D:\Dev\Projects\agent_new\docs\benchmarks\2026-11-07-evaluation\controlled\baseline\metadata.json
- policy: D:\Dev\Projects\agent_new\docs\benchmarks\2026-11-07-evaluation\controlled\policy.json

## Limits

- Completion and answered rates are operational, not semantic task success.
- Point-estimate tolerances are policy checks, not statistical non-inferiority proof.
- CI95 bootstraps questions; repeats are averaged within each question.
- A pass establishes no absolute quality floor or general population improvement.
- Hashes verify artifact consistency, not independent authenticity or judge accuracy.

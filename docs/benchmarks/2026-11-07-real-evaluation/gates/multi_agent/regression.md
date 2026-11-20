# Agent regression: FAIL

Policy: example-uncalibrated-research-v1 (`3024bb663cbb93476a77ca9d7d87c50ae664bf5b68445c8a73da0eca7bb1ac1e`).
Strategies: baseline -> multi_agent.

The decision checks configured observed tolerances. It is not proof of statistical non-inferiority or an absolute quality certification.

| dataset / split / kind | check | verdict | delta or ratio | paired tasks | coverage (old/new) | reason |
| --- | --- | --- | ---: | ---: | --- | --- |
| research-v1 / dev / real_source | completion_rate | pass | 0.0 | N/A | N/A / N/A | operational rate only; not semantic task success |
| research-v1 / dev / real_source | answered_rate | pass | 0.0 | N/A | N/A / N/A | operational rate only; not semantic task success |
| research-v1 / dev / real_source | latency_p50_ratio | fail | 2.812669697638802 | N/A | N/A / N/A | observed latency ratio; no significance claim |
| research-v1 / dev / real_source | agent_goal_accuracy | fail | 0.08333333333333333 | 12 | 1.0 / 1.0 | observed quality drop exceeds policy tolerance |
| research-v1 / dev / real_source | factual_correctness | fail | 0.09999999999999996 | 12 | 1.0 / 1.0 | observed quality drop exceeds policy tolerance |
| research-v1 / dev / real_source | faithfulness | inconclusive | N/A | 0 | 0.0 / 0.5833333333333334 | insufficient paired tasks or score coverage |
| research-v1 / dev / real_source | citation_accuracy | inconclusive | 0.007467532467532461 | 11 | 1.0 / 0.9166666666666666 | insufficient paired tasks or score coverage |

## Task changes

| dataset / split | metric | question | delta | change |
| --- | --- | --- | ---: | --- |
| research-v1 / dev | agent_goal_accuracy | comparison-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | comparison-dev-02 | 1.0 | improved |
| research-v1 / dev | agent_goal_accuracy | conflicting_evidence-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | conflicting_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | insufficient_evidence-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | insufficient_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | multi_hop-dev-01 | 1.0 | improved |
| research-v1 / dev | agent_goal_accuracy | multi_hop-dev-02 | -1.0 | regressed |
| research-v1 / dev | agent_goal_accuracy | single_hop-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | single_hop-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | version_boundary-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | version_boundary-dev-02 | 0.0 | unchanged |
| research-v1 / dev | factual_correctness | comparison-dev-01 | -0.27 | regressed |
| research-v1 / dev | factual_correctness | comparison-dev-02 | 0.06999999999999995 | improved |
| research-v1 / dev | factual_correctness | conflicting_evidence-dev-01 | -0.27 | regressed |
| research-v1 / dev | factual_correctness | conflicting_evidence-dev-02 | 0.15999999999999998 | improved |
| research-v1 / dev | factual_correctness | insufficient_evidence-dev-01 | 0.6499999999999999 | improved |
| research-v1 / dev | factual_correctness | insufficient_evidence-dev-02 | -0.10000000000000009 | regressed |
| research-v1 / dev | factual_correctness | multi_hop-dev-01 | -0.10000000000000003 | regressed |
| research-v1 / dev | factual_correctness | multi_hop-dev-02 | 0.31 | improved |
| research-v1 / dev | factual_correctness | single_hop-dev-01 | -0.07000000000000006 | regressed |
| research-v1 / dev | factual_correctness | single_hop-dev-02 | 0.51 | improved |
| research-v1 / dev | factual_correctness | version_boundary-dev-01 | -0.020000000000000018 | regressed |
| research-v1 / dev | factual_correctness | version_boundary-dev-02 | 0.32999999999999996 | improved |

Excluded for faithfulness: comparison-dev-01, comparison-dev-02, conflicting_evidence-dev-01, conflicting_evidence-dev-02, insufficient_evidence-dev-01, insufficient_evidence-dev-02, multi_hop-dev-01, multi_hop-dev-02, single_hop-dev-01, single_hop-dev-02, version_boundary-dev-01, version_boundary-dev-02.

| research-v1 / dev | citation_accuracy | comparison-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | conflicting_evidence-dev-01 | -0.08333333333333337 | regressed |
| research-v1 / dev | citation_accuracy | conflicting_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | insufficient_evidence-dev-01 | 0.375 | improved |
| research-v1 / dev | citation_accuracy | insufficient_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | multi_hop-dev-01 | 0.033333333333333326 | improved |
| research-v1 / dev | citation_accuracy | multi_hop-dev-02 | 0.13888888888888884 | improved |
| research-v1 / dev | citation_accuracy | single_hop-dev-01 | -0.059523809523809534 | regressed |
| research-v1 / dev | citation_accuracy | single_hop-dev-02 | 0.050000000000000044 | improved |
| research-v1 / dev | citation_accuracy | version_boundary-dev-01 | -0.2333333333333334 | regressed |
| research-v1 / dev | citation_accuracy | version_boundary-dev-02 | -0.13888888888888884 | regressed |

Excluded for citation_accuracy: comparison-dev-01.


## Original trials

Full answers, evidence and trajectories remain in the source quality exports.

| side | question | repeat | original run ID | status |
| --- | --- | ---: | --- | --- |
| baseline | single_hop-dev-01 | 0 | real-dev-20261107-single_hop-dev-01-baseline | completed |
| baseline | single_hop-dev-02 | 0 | real-dev-20261107-single_hop-dev-02-baseline | completed |
| baseline | multi_hop-dev-01 | 0 | real-dev-20261107-multi_hop-dev-01-baseline | partial |
| baseline | multi_hop-dev-02 | 0 | real-dev-20261107-multi_hop-dev-02-baseline | completed |
| baseline | comparison-dev-01 | 0 | real-dev-20261107-comparison-dev-01-baseline | completed |
| baseline | comparison-dev-02 | 0 | real-dev-20261107-comparison-dev-02-baseline | completed |
| baseline | version_boundary-dev-01 | 0 | real-dev-20261107-version_boundary-dev-01-baseline | completed |
| baseline | version_boundary-dev-02 | 0 | real-dev-20261107-version_boundary-dev-02-baseline | completed |
| baseline | conflicting_evidence-dev-01 | 0 | real-dev-20261107-conflicting_evidence-dev-01-baseline | completed |
| baseline | conflicting_evidence-dev-02 | 0 | real-dev-20261107-conflicting_evidence-dev-02-baseline | completed |
| baseline | insufficient_evidence-dev-01 | 0 | real-dev-20261107-insufficient_evidence-dev-01-baseline | completed |
| baseline | insufficient_evidence-dev-02 | 0 | real-dev-20261107-insufficient_evidence-dev-02-baseline | partial |
| candidate | single_hop-dev-01 | 0 | real-dev-20261107-single_hop-dev-01-multi_agent | completed |
| candidate | single_hop-dev-02 | 0 | real-dev-20261107-single_hop-dev-02-multi_agent | completed |
| candidate | multi_hop-dev-01 | 0 | real-dev-20261107-multi_hop-dev-01-multi_agent | completed |
| candidate | multi_hop-dev-02 | 0 | real-dev-20261107-multi_hop-dev-02-multi_agent | completed |
| candidate | comparison-dev-01 | 0 | real-dev-20261107-comparison-dev-01-multi_agent | partial |
| candidate | comparison-dev-02 | 0 | real-dev-20261107-comparison-dev-02-multi_agent | completed |
| candidate | version_boundary-dev-01 | 0 | real-dev-20261107-version_boundary-dev-01-multi_agent | completed |
| candidate | version_boundary-dev-02 | 0 | real-dev-20261107-version_boundary-dev-02-multi_agent | completed |
| candidate | conflicting_evidence-dev-01 | 0 | real-dev-20261107-conflicting_evidence-dev-01-multi_agent | completed |
| candidate | conflicting_evidence-dev-02 | 0 | real-dev-20261107-conflicting_evidence-dev-02-multi_agent | completed |
| candidate | insufficient_evidence-dev-01 | 0 | real-dev-20261107-insufficient_evidence-dev-01-multi_agent | completed |
| candidate | insufficient_evidence-dev-02 | 0 | real-dev-20261107-insufficient_evidence-dev-02-multi_agent | partial |

## Resources

| dataset / split / kind | side | runs | p50 ms | p95 ms | input tokens | output tokens | provider attempts |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| research-v1 / dev / real_source | baseline | 12 | 11695.21200004965 | 14389.598505070899 | 143409 | 11373 | 24 |
| research-v1 / dev / real_source | candidate | 12 | 32894.76840000134 | 61319.63740003991 | 309918 | 39549 | 84 |

CI95, all-output/completed-only views, observed usage subtotals and complete scoring provenance are in regression.json.

## Source artifacts

- baseline: D:\Dev\Projects\agent_new\tmp\real-evaluation-20261107\research-batch\quality_eval.json
- candidate: D:\Dev\Projects\agent_new\tmp\real-evaluation-20261107\research-batch\quality_eval.json
- metadata: D:\Dev\Projects\agent_new\tmp\real-evaluation-20261107\research-batch\analysis-dev.json
- policy: D:\Dev\Projects\agent_new\backend\src\deeptrace\eval\data\policies\regression-v1.json

## Limits

- Completion and answered rates are operational, not semantic task success.
- Point-estimate tolerances are policy checks, not statistical non-inferiority proof.
- CI95 bootstraps questions; repeats are averaged within each question.
- A pass establishes no absolute quality floor or general population improvement.
- Hashes verify artifact consistency, not independent authenticity or judge accuracy.

# Agent regression: FAIL

Policy: example-uncalibrated-research-v1 (`3024bb663cbb93476a77ca9d7d87c50ae664bf5b68445c8a73da0eca7bb1ac1e`).
Strategies: baseline -> workflow.

The decision checks configured observed tolerances. It is not proof of statistical non-inferiority or an absolute quality certification.

| dataset / split / kind | check | verdict | delta or ratio | paired tasks | coverage (old/new) | reason |
| --- | --- | --- | ---: | ---: | --- | --- |
| research-v1 / dev / real_source | completion_rate | pass | 0.08333333333333326 | N/A | N/A / N/A | operational rate only; not semantic task success |
| research-v1 / dev / real_source | answered_rate | fail | -0.08333333333333337 | N/A | N/A / N/A | operational rate only; not semantic task success |
| research-v1 / dev / real_source | latency_p50_ratio | fail | 2.5839338654098425 | N/A | N/A / N/A | observed latency ratio; no significance claim |
| research-v1 / dev / real_source | agent_goal_accuracy | pass | 0.25 | 12 | 1.0 / 1.0 | observed quality drop is within policy tolerance |
| research-v1 / dev / real_source | factual_correctness | fail | 0.07499999999999998 | 12 | 1.0 / 1.0 | observed quality drop exceeds policy tolerance |
| research-v1 / dev / real_source | faithfulness | inconclusive | N/A | 0 | 0.0 / 0.5833333333333334 | insufficient paired tasks or score coverage |
| research-v1 / dev / real_source | citation_accuracy | inconclusive | 0.080188246097337 | 11 | 1.0 / 0.9166666666666666 | insufficient paired tasks or score coverage |

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
| research-v1 / dev | agent_goal_accuracy | multi_hop-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | single_hop-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | single_hop-dev-02 | 1.0 | improved |
| research-v1 / dev | agent_goal_accuracy | version_boundary-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | version_boundary-dev-02 | 0.0 | unchanged |
| research-v1 / dev | factual_correctness | comparison-dev-01 | -0.27 | regressed |
| research-v1 / dev | factual_correctness | comparison-dev-02 | 0.010000000000000009 | improved |
| research-v1 / dev | factual_correctness | conflicting_evidence-dev-01 | -0.19999999999999996 | regressed |
| research-v1 / dev | factual_correctness | conflicting_evidence-dev-02 | 0.29 | improved |
| research-v1 / dev | factual_correctness | insufficient_evidence-dev-01 | 0.44 | improved |
| research-v1 / dev | factual_correctness | insufficient_evidence-dev-02 | -0.36000000000000004 | regressed |
| research-v1 / dev | factual_correctness | multi_hop-dev-01 | -0.12 | regressed |
| research-v1 / dev | factual_correctness | multi_hop-dev-02 | 0.29 | improved |
| research-v1 / dev | factual_correctness | single_hop-dev-01 | 0.029999999999999916 | improved |
| research-v1 / dev | factual_correctness | single_hop-dev-02 | 0.43 | improved |
| research-v1 / dev | factual_correctness | version_boundary-dev-01 | 0.17000000000000004 | improved |
| research-v1 / dev | factual_correctness | version_boundary-dev-02 | 0.18999999999999995 | improved |

Excluded for faithfulness: comparison-dev-01, comparison-dev-02, conflicting_evidence-dev-01, conflicting_evidence-dev-02, insufficient_evidence-dev-01, insufficient_evidence-dev-02, multi_hop-dev-01, multi_hop-dev-02, single_hop-dev-01, single_hop-dev-02, version_boundary-dev-01, version_boundary-dev-02.

| research-v1 / dev | citation_accuracy | comparison-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | conflicting_evidence-dev-01 | -0.09090909090909094 | regressed |
| research-v1 / dev | citation_accuracy | conflicting_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | insufficient_evidence-dev-01 | 0.375 | improved |
| research-v1 / dev | citation_accuracy | insufficient_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | multi_hop-dev-01 | 0.11666666666666659 | improved |
| research-v1 / dev | citation_accuracy | multi_hop-dev-02 | 0.2222222222222222 | improved |
| research-v1 / dev | citation_accuracy | single_hop-dev-01 | 0.08333333333333337 | improved |
| research-v1 / dev | citation_accuracy | single_hop-dev-02 | 0.21666666666666667 | improved |
| research-v1 / dev | citation_accuracy | version_boundary-dev-01 | -0.033333333333333326 | regressed |
| research-v1 / dev | citation_accuracy | version_boundary-dev-02 | -0.007575757575757569 | regressed |

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
| candidate | single_hop-dev-01 | 0 | real-dev-20261107-single_hop-dev-01-workflow | completed |
| candidate | single_hop-dev-02 | 0 | real-dev-20261107-single_hop-dev-02-workflow | completed |
| candidate | multi_hop-dev-01 | 0 | real-dev-20261107-multi_hop-dev-01-workflow | partial |
| candidate | multi_hop-dev-02 | 0 | real-dev-20261107-multi_hop-dev-02-workflow | completed |
| candidate | comparison-dev-01 | 0 | real-dev-20261107-comparison-dev-01-workflow | completed |
| candidate | comparison-dev-02 | 0 | real-dev-20261107-comparison-dev-02-workflow | completed |
| candidate | version_boundary-dev-01 | 0 | real-dev-20261107-version_boundary-dev-01-workflow | completed |
| candidate | version_boundary-dev-02 | 0 | real-dev-20261107-version_boundary-dev-02-workflow | completed |
| candidate | conflicting_evidence-dev-01 | 0 | real-dev-20261107-conflicting_evidence-dev-01-workflow | completed |
| candidate | conflicting_evidence-dev-02 | 0 | real-dev-20261107-conflicting_evidence-dev-02-workflow | completed |
| candidate | insufficient_evidence-dev-01 | 0 | real-dev-20261107-insufficient_evidence-dev-01-workflow | completed |
| candidate | insufficient_evidence-dev-02 | 0 | real-dev-20261107-insufficient_evidence-dev-02-workflow | completed |

## Resources

| dataset / split / kind | side | runs | p50 ms | p95 ms | input tokens | output tokens | provider attempts |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| research-v1 / dev / real_source | baseline | 12 | 11695.21200004965 | 14389.598505070899 | 143409 | 11373 | 24 |
| research-v1 / dev / real_source | candidate | 12 | 30219.65435007587 | 38754.97286496683 | 278084 | 33359 | 78 |

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

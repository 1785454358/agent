# Agent regression: FAIL

Policy: example-uncalibrated-research-v1 (`3024bb663cbb93476a77ca9d7d87c50ae664bf5b68445c8a73da0eca7bb1ac1e`).
Strategies: workflow -> workflow.

The decision checks configured observed tolerances. It is not proof of statistical non-inferiority or an absolute quality certification.

| dataset / split / kind | check | verdict | delta or ratio | paired tasks | coverage (old/new) | reason |
| --- | --- | --- | ---: | ---: | --- | --- |
| research-v1 / dev / real_source | completion_rate | pass | 0.0 | N/A | N/A / N/A | operational rate only; not semantic task success |
| research-v1 / dev / real_source | answered_rate | pass | 0.08333333333333337 | N/A | N/A / N/A | operational rate only; not semantic task success |
| research-v1 / dev / real_source | latency_p50_ratio | pass | 0.9774908444652645 | N/A | N/A / N/A | observed latency ratio; no significance claim |
| research-v1 / dev / real_source | agent_goal_accuracy | fail | -0.08333333333333333 | 12 | 1.0 / 1.0 | observed quality drop exceeds policy tolerance |
| research-v1 / dev / real_source | factual_correctness | fail | 0.07666666666666667 | 12 | 1.0 / 1.0 | observed quality drop exceeds policy tolerance |
| research-v1 / dev / real_source | faithfulness | inconclusive | 0.09239218338597223 | 7 | 0.5833333333333334 / 0.5833333333333334 | insufficient paired tasks or score coverage |
| research-v1 / dev / real_source | citation_accuracy | fail | -0.06320018365472911 | 11 | 0.9166666666666666 / 1.0 | observed quality drop exceeds policy tolerance |

## Task changes

| dataset / split | metric | question | delta | change |
| --- | --- | --- | ---: | --- |
| research-v1 / dev | agent_goal_accuracy | comparison-dev-01 | 1.0 | improved |
| research-v1 / dev | agent_goal_accuracy | comparison-dev-02 | -1.0 | regressed |
| research-v1 / dev | agent_goal_accuracy | conflicting_evidence-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | conflicting_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | insufficient_evidence-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | insufficient_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | multi_hop-dev-01 | -1.0 | regressed |
| research-v1 / dev | agent_goal_accuracy | multi_hop-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | single_hop-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | single_hop-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | version_boundary-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | version_boundary-dev-02 | 0.0 | unchanged |
| research-v1 / dev | factual_correctness | comparison-dev-01 | 0.81 | improved |
| research-v1 / dev | factual_correctness | comparison-dev-02 | 0.16000000000000003 | improved |
| research-v1 / dev | factual_correctness | conflicting_evidence-dev-01 | 0.04999999999999993 | improved |
| research-v1 / dev | factual_correctness | conflicting_evidence-dev-02 | 0.12 | improved |
| research-v1 / dev | factual_correctness | insufficient_evidence-dev-01 | -0.19 | regressed |
| research-v1 / dev | factual_correctness | insufficient_evidence-dev-02 | 0.27999999999999997 | improved |
| research-v1 / dev | factual_correctness | multi_hop-dev-01 | 0.21000000000000002 | improved |
| research-v1 / dev | factual_correctness | multi_hop-dev-02 | -0.10999999999999999 | regressed |
| research-v1 / dev | factual_correctness | single_hop-dev-01 | 0.09000000000000008 | improved |
| research-v1 / dev | factual_correctness | single_hop-dev-02 | 0.030000000000000027 | improved |
| research-v1 / dev | factual_correctness | version_boundary-dev-01 | -0.49000000000000005 | regressed |
| research-v1 / dev | factual_correctness | version_boundary-dev-02 | -0.039999999999999925 | regressed |
| research-v1 / dev | faithfulness | comparison-dev-01 | 0.7 | improved |
| research-v1 / dev | faithfulness | insufficient_evidence-dev-01 | 0.07307692307692315 | improved |
| research-v1 / dev | faithfulness | insufficient_evidence-dev-02 | 0.07905138339920958 | improved |
| research-v1 / dev | faithfulness | multi_hop-dev-01 | -0.06666666666666665 | regressed |
| research-v1 / dev | faithfulness | single_hop-dev-01 | 0.0 | unchanged |
| research-v1 / dev | faithfulness | version_boundary-dev-01 | -0.09523809523809523 | regressed |
| research-v1 / dev | faithfulness | version_boundary-dev-02 | -0.04347826086956519 | regressed |

Excluded for faithfulness: comparison-dev-02, conflicting_evidence-dev-01, conflicting_evidence-dev-02, multi_hop-dev-02, single_hop-dev-02.

| research-v1 / dev | citation_accuracy | comparison-dev-02 | -0.125 | regressed |
| research-v1 / dev | citation_accuracy | conflicting_evidence-dev-01 | 0.09090909090909094 | improved |
| research-v1 / dev | citation_accuracy | conflicting_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | insufficient_evidence-dev-01 | -0.33333333333333337 | regressed |
| research-v1 / dev | citation_accuracy | insufficient_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | multi_hop-dev-01 | 0.08333333333333337 | improved |
| research-v1 / dev | citation_accuracy | multi_hop-dev-02 | -0.09090909090909094 | regressed |
| research-v1 / dev | citation_accuracy | single_hop-dev-01 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | single_hop-dev-02 | -0.16666666666666663 | regressed |
| research-v1 / dev | citation_accuracy | version_boundary-dev-01 | -0.24444444444444446 | regressed |
| research-v1 / dev | citation_accuracy | version_boundary-dev-02 | 0.09090909090909094 | improved |

Excluded for citation_accuracy: comparison-dev-01.


## Original trials

Full answers, evidence and trajectories remain in the source quality exports.

| side | question | repeat | original run ID | status |
| --- | --- | ---: | --- | --- |
| baseline | single_hop-dev-01 | 0 | real-dev-20261107-single_hop-dev-01-workflow | completed |
| baseline | single_hop-dev-02 | 0 | real-dev-20261107-single_hop-dev-02-workflow | completed |
| baseline | multi_hop-dev-01 | 0 | real-dev-20261107-multi_hop-dev-01-workflow | partial |
| baseline | multi_hop-dev-02 | 0 | real-dev-20261107-multi_hop-dev-02-workflow | completed |
| baseline | comparison-dev-01 | 0 | real-dev-20261107-comparison-dev-01-workflow | completed |
| baseline | comparison-dev-02 | 0 | real-dev-20261107-comparison-dev-02-workflow | completed |
| baseline | version_boundary-dev-01 | 0 | real-dev-20261107-version_boundary-dev-01-workflow | completed |
| baseline | version_boundary-dev-02 | 0 | real-dev-20261107-version_boundary-dev-02-workflow | completed |
| baseline | conflicting_evidence-dev-01 | 0 | real-dev-20261107-conflicting_evidence-dev-01-workflow | completed |
| baseline | conflicting_evidence-dev-02 | 0 | real-dev-20261107-conflicting_evidence-dev-02-workflow | completed |
| baseline | insufficient_evidence-dev-01 | 0 | real-dev-20261107-insufficient_evidence-dev-01-workflow | completed |
| baseline | insufficient_evidence-dev-02 | 0 | real-dev-20261107-insufficient_evidence-dev-02-workflow | completed |
| candidate | single_hop-dev-01 | 0 | answer-optimization-20261107-single_hop-dev-01-workflow | completed |
| candidate | single_hop-dev-02 | 0 | answer-optimization-20261107-single_hop-dev-02-workflow | completed |
| candidate | multi_hop-dev-01 | 0 | answer-optimization-20261107-multi_hop-dev-01-workflow | completed |
| candidate | multi_hop-dev-02 | 0 | answer-optimization-20261107-multi_hop-dev-02-workflow | completed |
| candidate | comparison-dev-01 | 0 | answer-optimization-20261107-comparison-dev-01-workflow | completed |
| candidate | comparison-dev-02 | 0 | answer-optimization-20261107-comparison-dev-02-workflow | completed |
| candidate | version_boundary-dev-01 | 0 | answer-optimization-20261107-version_boundary-dev-01-workflow | completed |
| candidate | version_boundary-dev-02 | 0 | answer-optimization-20261107-version_boundary-dev-02-workflow | partial |
| candidate | conflicting_evidence-dev-01 | 0 | answer-optimization-20261107-conflicting_evidence-dev-01-workflow | completed |
| candidate | conflicting_evidence-dev-02 | 0 | answer-optimization-20261107-conflicting_evidence-dev-02-workflow | completed |
| candidate | insufficient_evidence-dev-01 | 0 | answer-optimization-20261107-insufficient_evidence-dev-01-workflow | completed |
| candidate | insufficient_evidence-dev-02 | 0 | answer-optimization-20261107-insufficient_evidence-dev-02-workflow | completed |

## Resources

| dataset / split / kind | side | runs | p50 ms | p95 ms | input tokens | output tokens | provider attempts |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| research-v1 / dev / real_source | baseline | 12 | 30219.65435007587 | 38754.97286496683 | 278084 | 33359 | 78 |
| research-v1 / dev / real_source | candidate | 12 | 29539.435450104065 | 37685.46733991242 | 292493 | 31530 | 79 |

CI95, all-output/completed-only views, observed usage subtotals and complete scoring provenance are in regression.json.

## Source artifacts

- baseline: D:\Dev\Projects\agent_new\tmp\real-evaluation-20261107\research-batch\quality_eval.json
- candidate: D:\Dev\Projects\agent_new\tmp\answer-optimization-20261107\workflow\quality_eval.json
- metadata: D:\Dev\Projects\agent_new\tmp\real-evaluation-20261107\research-batch\analysis-dev.json
- policy: D:\Dev\Projects\agent_new\backend\src\deeptrace\eval\data\policies\regression-v1.json

## Limits

- Completion and answered rates are operational, not semantic task success.
- Point-estimate tolerances are policy checks, not statistical non-inferiority proof.
- CI95 bootstraps questions; repeats are averaged within each question.
- A pass establishes no absolute quality floor or general population improvement.
- Hashes verify artifact consistency, not independent authenticity or judge accuracy.

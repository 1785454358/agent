# Agent regression: FAIL

Policy: example-uncalibrated-research-v1 (`3024bb663cbb93476a77ca9d7d87c50ae664bf5b68445c8a73da0eca7bb1ac1e`).
Strategies: workflow -> workflow.

The decision checks configured observed tolerances. It is not proof of statistical non-inferiority or an absolute quality certification.

| dataset / split / kind | check | verdict | delta or ratio | paired tasks | coverage (old/new) | reason |
| --- | --- | --- | ---: | ---: | --- | --- |
| research-v1 / dev / real_source | completion_rate | fail | -0.08333333333333326 | N/A | N/A / N/A | operational rate only; not semantic task success |
| research-v1 / dev / real_source | answered_rate | fail | -0.08333333333333337 | N/A | N/A / N/A | operational rate only; not semantic task success |
| research-v1 / dev / real_source | latency_p50_ratio | pass | 0.951485109113312 | N/A | N/A / N/A | observed latency ratio; no significance claim |
| research-v1 / dev / real_source | agent_goal_accuracy | fail | -0.08333333333333333 | 12 | 1.0 / 1.0 | observed quality drop exceeds policy tolerance |
| research-v1 / dev / real_source | factual_correctness | fail | -0.085 | 12 | 1.0 / 1.0 | observed quality drop exceeds policy tolerance |
| research-v1 / dev / real_source | faithfulness | inconclusive | -0.013899451399451382 | 8 | 0.6666666666666666 / 0.6666666666666666 | insufficient paired tasks or score coverage |
| research-v1 / dev / real_source | citation_accuracy | pass | 0.010416666666666676 | 12 | 1.0 / 1.0 | observed quality drop is within policy tolerance |

## Task changes

| dataset / split | metric | question | delta | change |
| --- | --- | --- | ---: | --- |
| research-v1 / dev | agent_goal_accuracy | comparison-dev-01 | -1.0 | regressed |
| research-v1 / dev | agent_goal_accuracy | comparison-dev-02 | -1.0 | regressed |
| research-v1 / dev | agent_goal_accuracy | conflicting_evidence-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | conflicting_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | insufficient_evidence-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | insufficient_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | multi_hop-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | multi_hop-dev-02 | 1.0 | improved |
| research-v1 / dev | agent_goal_accuracy | single_hop-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | single_hop-dev-02 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | version_boundary-dev-01 | 0.0 | unchanged |
| research-v1 / dev | agent_goal_accuracy | version_boundary-dev-02 | 0.0 | unchanged |
| research-v1 / dev | factual_correctness | comparison-dev-01 | -0.57 | regressed |
| research-v1 / dev | factual_correctness | comparison-dev-02 | 0.29999999999999993 | improved |
| research-v1 / dev | factual_correctness | conflicting_evidence-dev-01 | -0.050000000000000044 | regressed |
| research-v1 / dev | factual_correctness | conflicting_evidence-dev-02 | 0.1499999999999999 | improved |
| research-v1 / dev | factual_correctness | insufficient_evidence-dev-01 | 0.06999999999999995 | improved |
| research-v1 / dev | factual_correctness | insufficient_evidence-dev-02 | 0.050000000000000044 | improved |
| research-v1 / dev | factual_correctness | multi_hop-dev-01 | -0.39 | regressed |
| research-v1 / dev | factual_correctness | multi_hop-dev-02 | 0.0 | unchanged |
| research-v1 / dev | factual_correctness | single_hop-dev-01 | 0.050000000000000044 | improved |
| research-v1 / dev | factual_correctness | single_hop-dev-02 | -0.12 | regressed |
| research-v1 / dev | factual_correctness | version_boundary-dev-01 | -0.17000000000000004 | regressed |
| research-v1 / dev | factual_correctness | version_boundary-dev-02 | -0.33999999999999997 | regressed |
| research-v1 / dev | faithfulness | comparison-dev-01 | 0.022522522522522515 | improved |
| research-v1 / dev | faithfulness | conflicting_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | faithfulness | insufficient_evidence-dev-01 | -0.15319865319865322 | regressed |
| research-v1 / dev | faithfulness | insufficient_evidence-dev-02 | 0.25 | improved |
| research-v1 / dev | faithfulness | multi_hop-dev-01 | -0.06060606060606055 | regressed |
| research-v1 / dev | faithfulness | single_hop-dev-01 | -0.0714285714285714 | regressed |
| research-v1 / dev | faithfulness | version_boundary-dev-01 | -0.18181818181818177 | regressed |
| research-v1 / dev | faithfulness | version_boundary-dev-02 | 0.08333333333333337 | improved |

Excluded for faithfulness: comparison-dev-02, conflicting_evidence-dev-01, multi_hop-dev-02, single_hop-dev-02.

| research-v1 / dev | citation_accuracy | comparison-dev-01 | 0.19999999999999996 | improved |
| research-v1 / dev | citation_accuracy | comparison-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | conflicting_evidence-dev-01 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | conflicting_evidence-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | insufficient_evidence-dev-01 | -0.16666666666666663 | regressed |
| research-v1 / dev | citation_accuracy | insufficient_evidence-dev-02 | 0.33333333333333337 | improved |
| research-v1 / dev | citation_accuracy | multi_hop-dev-01 | -0.16666666666666663 | regressed |
| research-v1 / dev | citation_accuracy | multi_hop-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | single_hop-dev-01 | -0.19999999999999996 | regressed |
| research-v1 / dev | citation_accuracy | single_hop-dev-02 | 0.0 | unchanged |
| research-v1 / dev | citation_accuracy | version_boundary-dev-01 | 0.125 | improved |
| research-v1 / dev | citation_accuracy | version_boundary-dev-02 | 0.0 | unchanged |

## Original trials

Full answers, evidence and trajectories remain in the source quality exports.

| side | question | repeat | original run ID | status |
| --- | --- | ---: | --- | --- |
| baseline | single_hop-dev-01 | 0 | harness-contract-20261107-single_hop-dev-01-workflow | completed |
| baseline | single_hop-dev-02 | 0 | harness-contract-20261107-single_hop-dev-02-workflow | completed |
| baseline | multi_hop-dev-01 | 0 | harness-contract-20261107-multi_hop-dev-01-workflow | completed |
| baseline | multi_hop-dev-02 | 0 | harness-contract-20261107-multi_hop-dev-02-workflow | completed |
| baseline | comparison-dev-01 | 0 | harness-contract-20261107-comparison-dev-01-workflow | partial |
| baseline | comparison-dev-02 | 0 | harness-contract-20261107-comparison-dev-02-workflow | completed |
| baseline | version_boundary-dev-01 | 0 | harness-contract-20261107-version_boundary-dev-01-workflow | completed |
| baseline | version_boundary-dev-02 | 0 | harness-contract-20261107-version_boundary-dev-02-workflow | completed |
| baseline | conflicting_evidence-dev-01 | 0 | harness-contract-20261107-conflicting_evidence-dev-01-workflow | completed |
| baseline | conflicting_evidence-dev-02 | 0 | harness-contract-20261107-conflicting_evidence-dev-02-workflow | completed |
| baseline | insufficient_evidence-dev-01 | 0 | harness-contract-20261107-insufficient_evidence-dev-01-workflow | completed |
| baseline | insufficient_evidence-dev-02 | 0 | harness-contract-20261107-insufficient_evidence-dev-02-workflow | completed |
| candidate | single_hop-dev-01 | 0 | harness-scope-review-20261108-single_hop-dev-01-workflow | completed |
| candidate | single_hop-dev-02 | 0 | harness-scope-review-20261108-single_hop-dev-02-workflow | partial |
| candidate | multi_hop-dev-01 | 0 | harness-scope-review-20261108-multi_hop-dev-01-workflow | completed |
| candidate | multi_hop-dev-02 | 0 | harness-scope-review-20261108-multi_hop-dev-02-workflow | completed |
| candidate | comparison-dev-01 | 0 | harness-scope-review-20261108-comparison-dev-01-workflow | completed |
| candidate | comparison-dev-02 | 0 | harness-scope-review-20261108-comparison-dev-02-workflow | completed |
| candidate | version_boundary-dev-01 | 0 | harness-scope-review-20261108-version_boundary-dev-01-workflow | completed |
| candidate | version_boundary-dev-02 | 0 | harness-scope-review-20261108-version_boundary-dev-02-workflow | partial |
| candidate | conflicting_evidence-dev-01 | 0 | harness-scope-review-20261108-conflicting_evidence-dev-01-workflow | completed |
| candidate | conflicting_evidence-dev-02 | 0 | harness-scope-review-20261108-conflicting_evidence-dev-02-workflow | completed |
| candidate | insufficient_evidence-dev-01 | 0 | harness-scope-review-20261108-insufficient_evidence-dev-01-workflow | completed |
| candidate | insufficient_evidence-dev-02 | 0 | harness-scope-review-20261108-insufficient_evidence-dev-02-workflow | completed |

## Resources

| dataset / split / kind | side | runs | p50 ms | p95 ms | input tokens | output tokens | provider attempts |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| research-v1 / dev / real_source | baseline | 12 | 33854.25319999922 | 40052.70992508158 | 290232 | 34191 | 82 |
| research-v1 / dev / real_source | candidate | 12 | 32211.81779995095 | 60482.84612003481 | 328549 | 40974 | 96 |

CI95, all-output/completed-only views, observed usage subtotals and complete scoring provenance are in regression.json.

## Source artifacts

- baseline: D:\Dev\Projects\agent_new\tmp\harness-scope-review-20261108\baseline\quality_eval.json
- candidate: D:\Dev\Projects\agent_new\tmp\harness-scope-review-20261108\candidate\quality_eval.json
- metadata: D:\Dev\Projects\agent_new\tmp\harness-scope-review-20261108\baseline\analysis-dev.json
- policy: D:\Dev\Projects\agent_new\backend\src\deeptrace\eval\data\policies\regression-v1.json

## Limits

- Completion and answered rates are operational, not semantic task success.
- Point-estimate tolerances are policy checks, not statistical non-inferiority proof.
- CI95 bootstraps questions; repeats are averaged within each question.
- A pass establishes no absolute quality floor or general population improvement.
- Hashes verify artifact consistency, not independent authenticity or judge accuracy.

# Real-model quality results

Same-model automated judges, development tasks only, one trial per task/strategy. Values are available-case question means; parentheses show scored runs / all runs. FactualCorrectness is reference-based claim F1, not independently verified factual accuracy.

| strategy | goal | factual F1 | faithfulness | claim support | citation accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.667 (12/12) | 0.491 (12/12) | N/A (0/12) | N/A (0/12) | 0.867 (12/12) |
| multi_agent | 0.750 (12/12) | 0.591 (12/12) | 0.793 (7/12) | 0.929 (7/12) | 0.877 (11/12) |
| plan_execute | 0.833 (12/12) | 0.535 (12/12) | 0.951 (7/12) | 0.967 (7/12) | 0.874 (12/12) |
| workflow | 0.917 (12/12) | 0.566 (12/12) | 0.785 (7/12) | 0.946 (7/12) | 0.950 (11/12) |

## Paired differences against Baseline

| strategy | metric | paired tasks | candidate minus baseline | CI95 | excluded tasks |
| --- | --- | ---: | ---: | --- | ---: |
| multi_agent | agent_goal_accuracy | 12 | 0.08333333333333333 | [-0.16666666666666666, 0.4166666666666667] | 0 |
| multi_agent | factual_correctness | 12 | 0.09999999999999996 | [-0.0608541666666667, 0.2700416666666664] | 0 |
| multi_agent | faithfulness | 0 | None | None | 12 |
| multi_agent | claim_groundedness | 0 | None | None | 12 |
| multi_agent | citation_accuracy | 11 | 0.007467532467532461 | [-0.0757665945165945, 0.1051975108225108] | 1 |
| plan_execute | agent_goal_accuracy | 12 | 0.16666666666666666 | [-0.16666666666666666, 0.5] | 0 |
| plan_execute | factual_correctness | 12 | 0.044166666666666646 | [-0.0933541666666667, 0.1983333333333333] | 0 |
| plan_execute | faithfulness | 0 | None | None | 12 |
| plan_execute | claim_groundedness | 0 | None | None | 12 |
| plan_execute | citation_accuracy | 12 | 0.006923400673400674 | [-0.12572601010101012, 0.1250036826599326] | 0 |
| workflow | agent_goal_accuracy | 12 | 0.25 | [0.0, 0.5] | 0 |
| workflow | factual_correctness | 12 | 0.07499999999999998 | [-0.08250000000000002, 0.22166666666666665] | 0 |
| workflow | faithfulness | 0 | None | None | 12 |
| workflow | claim_groundedness | 0 | None | None | 12 |
| workflow | citation_accuracy | 11 | 0.080188246097337 | [0.008539944903581252, 0.16674644168962344] | 1 |

## Example-policy gates

The unchanged example-uncalibrated policy is diagnostic, not a calibrated release standard. Point-tolerance failures and insufficient evidence remain separate checks.

- workflow: **fail**, exit 1; failed=['answered_rate', 'latency_p50_ratio', 'factual_correctness']; insufficient=['faithfulness', 'citation_accuracy'].
- plan_execute: **fail**, exit 1; failed=['completion_rate', 'answered_rate', 'latency_p50_ratio', 'agent_goal_accuracy', 'citation_accuracy']; insufficient=['faithfulness'].
- multi_agent: **fail**, exit 1; failed=['latency_p50_ratio', 'agent_goal_accuracy', 'factual_correctness']; insufficient=['faithfulness', 'citation_accuracy'].

## Live supplement

These two tasks are separate from the frozen matrix. The retained live Ragas run used the earlier 2048-token cap and includes parsing errors. Citation scores may cover up to 12 citation uses per answer.

| task | goal | factual F1 | faithfulness | claim support | citation accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| live-sqlite-wal-20261107 | 1.000 | 0.390 | N/A (error) | 1.000 | 1.000 |
| live-langgraph-memory-20261107 | 1.000 | N/A (error) | 0.970 | 1.000 | 0.917 |

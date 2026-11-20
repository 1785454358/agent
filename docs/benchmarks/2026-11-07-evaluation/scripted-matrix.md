# Research mode baseline (offline corpus)

- questions: 3
- runs: 24

| mode | runs | completed | answered | gold_coverage | evidence | citation_ok | steps | tools | models | wall_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 6 | 6 | 6 | 1.000 | 1.00 | 1.000 | 2.00 | 2.00 | 1.00 | 13.0 |
| multi_agent | 6 | 6 | 6 | 1.000 | 1.00 | 1.000 | 9.00 | 3.00 | 7.00 | 63.0 |
| plan_execute | 6 | 6 | 6 | 1.000 | 1.00 | 1.000 | 9.00 | 3.00 | 7.00 | 64.9 |
| workflow | 6 | 6 | 6 | 1.000 | 1.00 | 1.000 | 9.00 | 3.00 | 7.00 | 89.1 |

Termination reasons:
- baseline: workflow_completed=6
- multi_agent: completed=6
- plan_execute: completed=6
- workflow: workflow_completed=6

These are execution and retrieval/citation-validity measurements on a frozen local corpus, not a research-quality verdict. Synthetic smoke data is for plumbing only; real-source calibration also needs independent quality scoring and sufficient paired samples.
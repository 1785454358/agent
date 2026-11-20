# Paired quality comparison

System quality means below are available-case question means; consult JSON for coverage. Repeat scores are averaged within question. Missing metrics are not zero. Completed-only and all-output pairs are separate.

## research-v1 / dev / real_source

| system | attempted runs | completed | goal | factual F1 | faithfulness | claim grounded | citation acc |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 12 | 10 | 0.667 | 0.491 | N/A | N/A | 0.867 |
| multi_agent | 12 | 10 | 0.750 | 0.591 | 0.793 | 0.929 | 0.877 |
| plan_execute | 12 | 9 | 0.833 | 0.535 | 0.951 | 0.967 | 0.874 |
| workflow | 12 | 11 | 0.917 | 0.566 | 0.785 | 0.946 | 0.950 |

- multi_agent vs baseline, agent_goal_accuracy, all_output: n=12, delta=0.08333333333333333, CI95=[-0.16666666666666666, 0.4166666666666667]; excluded=0
- multi_agent vs baseline, agent_goal_accuracy, completed_only: n=9, delta=0.0, CI95=[-0.3333333333333333, 0.3333333333333333]; excluded=3
- multi_agent vs baseline, factual_correctness, all_output: n=12, delta=0.09999999999999996, CI95=[-0.0608541666666667, 0.2700416666666664]; excluded=0
- multi_agent vs baseline, factual_correctness, completed_only: n=9, delta=0.18555555555555553, CI95=[0.009999999999999978, 0.36669444444444427]; excluded=3
- multi_agent vs baseline, faithfulness, all_output: n=0, delta=None, CI95=None; excluded=12
- multi_agent vs baseline, faithfulness, completed_only: n=0, delta=None, CI95=None; excluded=12
- multi_agent vs baseline, claim_groundedness, all_output: n=0, delta=None, CI95=None; excluded=12
- multi_agent vs baseline, claim_groundedness, completed_only: n=0, delta=None, CI95=None; excluded=12
- multi_agent vs baseline, citation_accuracy, all_output: n=11, delta=0.007467532467532461, CI95=[-0.0757665945165945, 0.1051975108225108]; excluded=1
- multi_agent vs baseline, citation_accuracy, completed_only: n=9, delta=0.005423280423280417, CI95=[-0.09241843033509702, 0.12037808641975303]; excluded=3
- plan_execute vs baseline, agent_goal_accuracy, all_output: n=12, delta=0.16666666666666666, CI95=[-0.16666666666666666, 0.5]; excluded=0
- plan_execute vs baseline, agent_goal_accuracy, completed_only: n=9, delta=0.1111111111111111, CI95=[-0.2222222222222222, 0.4444444444444444]; excluded=3
- plan_execute vs baseline, factual_correctness, all_output: n=12, delta=0.044166666666666646, CI95=[-0.0933541666666667, 0.1983333333333333]; excluded=0
- plan_execute vs baseline, factual_correctness, completed_only: n=9, delta=-0.010000000000000012, CI95=[-0.12111111111111111, 0.11777777777777779]; excluded=3
- plan_execute vs baseline, faithfulness, all_output: n=0, delta=None, CI95=None; excluded=12
- plan_execute vs baseline, faithfulness, completed_only: n=0, delta=None, CI95=None; excluded=12
- plan_execute vs baseline, claim_groundedness, all_output: n=0, delta=None, CI95=None; excluded=12
- plan_execute vs baseline, claim_groundedness, completed_only: n=0, delta=None, CI95=None; excluded=12
- plan_execute vs baseline, citation_accuracy, all_output: n=12, delta=0.006923400673400674, CI95=[-0.12572601010101012, 0.1250036826599326]; excluded=0
- plan_execute vs baseline, citation_accuracy, completed_only: n=9, delta=0.02404601571268239, CI95=[-0.07384960718294051, 0.13956439393939377]; excluded=3
- workflow vs baseline, agent_goal_accuracy, all_output: n=12, delta=0.25, CI95=[0.0, 0.5]; excluded=0
- workflow vs baseline, agent_goal_accuracy, completed_only: n=10, delta=0.2, CI95=[0.0, 0.5]; excluded=2
- workflow vs baseline, factual_correctness, all_output: n=12, delta=0.07499999999999998, CI95=[-0.08250000000000002, 0.22166666666666665]; excluded=0
- workflow vs baseline, factual_correctness, completed_only: n=10, delta=0.13799999999999998, CI95=[-0.005025000000000008, 0.27304999999999974]; excluded=2
- workflow vs baseline, faithfulness, all_output: n=0, delta=None, CI95=None; excluded=12
- workflow vs baseline, faithfulness, completed_only: n=0, delta=None, CI95=None; excluded=12
- workflow vs baseline, claim_groundedness, all_output: n=0, delta=None, CI95=None; excluded=12
- workflow vs baseline, claim_groundedness, completed_only: n=0, delta=None, CI95=None; excluded=12
- workflow vs baseline, citation_accuracy, all_output: n=11, delta=0.080188246097337, CI95=[0.008539944903581252, 0.16674644168962344]; excluded=1
- workflow vs baseline, citation_accuracy, completed_only: n=9, delta=0.08504489337822671, CI95=[0.0013425925925925892, 0.18241722783389444]; excluded=3

No population-effect or significance claim from a single pair; intervals for zero/one pair are null. Full coverage and exclusions are in comparison.json.
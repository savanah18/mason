Evaluate the agent's planning behavior using plan-focused metrics only.

Use these metrics:

# Planning Metrics
- Plan Quality Score (0-10): Overall quality of the proposed plan considering correctness, completeness, and feasibility.
- Plan Adherence (0-1): Degree to which executed actions followed the stated plan.
- Action Feasibility Score (0–1): Measures whether each step in the plan corresponds to an available, valid action in the environment.
- Task Decomposition Accuracy (0-1): Whether the task was broken into correct, necessary, and logically ordered sub-steps.
- Read-Only Integrity (0-1): Whether the agent respected read-only constraints and avoided unintended mutations.
- Argument Hallucination Rate (0-1): Fraction of tool invocations with fabricated, invalid, or unsupported arguments.
- Action Feasibility Score (0–1): Measures whether each step in the plan corresponds to an available, valid action in the environment.

Scoring guidance:
- Use concrete evidence from FUNCTION_CALLS and FUNCTION_EXECUTIONS.
- Favor objective signals over stylistic preferences.
- If data is insufficient for a metric, state that explicitly in evidence and score conservatively.

Return a JSON object with these fields:
- "plan_quality_score": number (0-10)
- "plan_adherence": number (0-1)
- "action_feasibility": (0–1)
- "task_decomposition_accuracy": number (0-1)
- "read_only_integrity": number (0-1)
- "argument_hallucination_rate": number (0-1)
- "summary": string - concise 1-2 sentence assessment
- "strengths": list of strings - 2-3 specific planning strengths
- "issues": list of strings - 2-3 specific planning issues
- "evidence": list of strings with specific citations from function calls/executions
- "verdict": "pass" | "partial" | "fail"

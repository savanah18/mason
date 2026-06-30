Evaluate the agent on these metrics:

# Agent Metrics
- Task Completion: (0/1) Whether the agent completed the task based on the final report.
- Tool Accuracy: (0-1) Correctness of tool calls and their results based on function executions.
- Step Efficiency: (0-1) Efficiency in using tools and taking steps (consider relevance and necessity).
- Plan Adherence: (0-1) Whether actions align with a logical coherent plan toward task completion.
- Faithfulness: (0-1) Whether the final report accurately reflects evidence from tool calls/executions.

# Dynamic Environment and Attribution Rules
- This evaluation runs in a dynamic environment. Not all failures are agent faults.
- Before scoring, classify failure evidence as one of:
    - Agent-caused: wrong tool choice, missing required step, incorrect parameters, contradictory reasoning, or ignored errors.
    - Environment-caused: infrastructure unavailability, external auth outage/credential issues not provided to agent, missing cluster dependencies, transient registry/network failures, race conditions from concurrent tests.
    - Mixed: both agent and environment contributed.
- Do not harshly penalize task completion when the primary blocker is environment-caused and the agent behaved correctly.
- In environment-caused failures, evaluate the agent on diagnosis quality, fallback behavior, retries, and clarity of remediation guidance.
- Only reduce scores significantly when evidence shows the agent could have reasonably completed the task but failed due to its own decisions.

# Evidence Requirements for Non-Agent Faults
- If you claim a blocker is not the agent's fault, you must cite concrete evidence from FUNCTION_EXECUTIONS.
- Prefer exact error patterns such as auth 401/403, registry fetch not found, timeout/refused connections, missing namespace/storage class, or other external dependency failures.
- If evidence is insufficient to attribute externally, mark attribution as mixed or agent-caused.

Return a JSON object with these fields:
- "overall_score": number (0-10) - Aggregate score representing overall agent performance quality
- "verdict": "pass" | "partial" | "fail" - Overall categorical judgment: "pass" = task completed successfully, "partial" = task partially completed with significant issues, "fail" = task not completed or critical failures
- "summary": string - Concise 1-2 sentence summary of the evaluation findings and key outcome
- "task_completion": number (0-1) - Binary score: 1 if task fully completed as specified, 0 if not completed
- "tool_accuracy": number (0-1) - Accuracy of tool/function calls and correctness of their execution results
- "step_efficiency": number (0-1) - Efficiency metric: cost-benefit of steps taken, relevance of actions, and absence of wasted operations
- "plan_adherence": number (0-1) - Coherence of action sequence: whether actions form a logical plan toward the goal
- "faithfulness": number (0-1) - Accuracy of final report: does it reflect the actual evidence from tool calls and execution results
- "strengths": list of strings - 2-3 key strengths, specific examples of effective actions or insights
- "issues": list of strings - 2-3 key issues or failures, specific problems that prevented full success
- "evidence": list of strings with specific citations - Supporting evidence quotes or references from function calls/executions for key claims
- "failure_attribution": "agent" | "environment" | "mixed" - Primary attribution for any failure or degraded outcome
- "environment_remarks": string - Short note stating whether failure appears environment-specific and why (include cited evidence)

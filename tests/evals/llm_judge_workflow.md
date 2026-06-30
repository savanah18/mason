# LLM Judge Workflow for Agent Evaluation

## Workflow
1. Build one evaluation record per run with:
   - Task input
   - Agent plan
   - Full tool trace (tool name, args, output, timestamps)
   - Final report

2. Run deterministic checks first:
   - Missing required steps
   - Forbidden tools/actions
   - Invalid schema/fields
   - Missing evidence references

3. Run LLM judge second:
   - Score each metric
   - Cite evidence from trace
   - Return strict JSON only

4. Aggregate score:
   - Weighted metric score
   - Hard fail if fabrication or unsupported claims detected

5. Calibrate:
   - Compare to human labels on a gold subset
   - Tune thresholds and prompt wording

## Judge Prompt Template

System prompt:
You are an evaluation judge for autonomous DevOps agents.
Score outputs only using the provided inputs.
Do not assume missing facts.
If evidence is missing, penalize faithfulness.
Return JSON only, matching the required schema exactly.

User prompt:
Evaluate this agent run.

Task:
{{task_input}}

Agent Plan:
{{agent_plan}}

Tool Trace:
{{tool_trace}}

Final Report:
{{final_report}}

Scoring rubric (0.0 to 1.0):
- task_completion_rate: Did the agent complete required objectives?
- tool_usage_accuracy: Were tools correctly chosen and correctly used?
- step_efficiency: Were there unnecessary steps/retries?
- plan_adherence_quality: Did execution follow and adapt the plan well?
- goal_accuracy_faithfulness: Are claims fully supported by trace evidence?
- response_time_latency: Normalize against baseline for this task type.
- cost_per_task: Normalize against baseline for this task type.
- human_in_the_loop_rate: Penalize if escalation was avoidable.

Hard fail conditions:
- fabricated_tool_output
- unsupported_claims
- forbidden_action

Return:
- per-metric scores
- weighted_total
- pass_fail
- findings with evidence references

## JSON Output Schema
{
  "run_id": "string",
  "hard_fail": {
    "triggered": true,
    "reasons": ["fabricated_tool_output"]
  },
  "scores": {
    "task_completion_rate": 0.0,
    "tool_usage_accuracy": 0.0,
    "step_efficiency": 0.0,
    "plan_adherence_quality": 0.0,
    "goal_accuracy_faithfulness": 0.0,
    "response_time_latency": 0.0,
    "cost_per_task": 0.0,
    "human_in_the_loop_rate": 0.0
  },
  "weights": {
    "task_completion_rate": 0.22,
    "tool_usage_accuracy": 0.20,
    "step_efficiency": 0.15,
    "plan_adherence_quality": 0.15,
    "goal_accuracy_faithfulness": 0.18,
    "response_time_latency": 0.06,
    "cost_per_task": 0.03,
    "human_in_the_loop_rate": 0.01
  },
  "weighted_total": 0.0,
  "pass_fail": "fail",
  "findings": [
    {
      "severity": "high",
      "metric": "goal_accuracy_faithfulness",
      "issue": "Claim not supported by tool output",
      "evidence": "tool_trace item 12 vs final_report paragraph 3"
    }
  ],
  "summary": "string"
}

## Recommended Decision Rule
1. Fail immediately if hard_fail.triggered is true.
2. Otherwise pass if weighted_total is at least 0.80.
3. Mark review-needed if weighted_total is 0.70 to 0.79.
4. Fail if weighted_total is below 0.70.

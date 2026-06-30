# Agent Capability Evaluation Plan

## Scope
This plan evaluates two existing agent specializations:
1. Deployment and Package Verification
2. Service Resource Benchmarking

It also adds one recommended workflow to increase coverage:
3. Incident Mitigation and Safe Rollback

Note: the benchmark URI provided (vscode-remote://wsl%2Brocky10-k8s/root/evaluations/DeathStarBench/mediaMicroservices/helm-chart/mediamicroservices) was not available in this workspace filesystem, so this plan is built from repository-local capabilities and can be mapped to that benchmark once mounted.

## Tool Inventory (Repository-Verified)

### Helm tools
Source: agent/actions/tools/helm/tools.py
- helm-add-repository
- helm-registry-login
- helm-update-repositories
- helm-list-repositories
- helm-remove-repository
- helm-template
- helm-lint
- helm-install
- helm-upgrade
- helm-list-releases
- helm-get-history
- helm-get-values
- helm-rollback
- helm-uninstall
- helm-test

### Kubernetes tools
Source: agent/actions/tools/kubernetes/tools.py
- kubernetes-list-workloads
- kubernetes-get-namespace-resource-quota
- kubernetes-get-namespace-events
- kubernetes-apply-resource-update

### Resource metrics tool
Source: agent/actions/tools/resource_collector/tools.py
- resource-collector

### Kafka tool
Source: agent/actions/tools/kafka/tools.py
- kafka-produce-message

## Persona Prompt Anchors
- Deployment persona goal: agent/personas/deployer/goal.yaml
- Resource benchmarking persona goal: agent/personas/resiliency-optimizer/goal.yaml

## Golden Dataset Design
Use tests/evals/golden_scenarios.yaml as the source of truth. Each scenario should include:
- id, workflow, difficulty
- input_event (release, namespace, event_type, constraints)
- environment_setup
- required_tools and optional_tools
- forbidden_actions
- expected_plan_steps
- success_criteria
- failure_signals

## Metric Definitions and Scoring
Use 0-1 normalized scores for each metric, then weighted aggregation.

### Agent Metrics
- Task Completion Rate (weight 0.22)
  - Formula: completed_tasks / total_tasks
  - Completed task requires all mandatory success criteria for a scenario.

- Tool Usage Accuracy (weight 0.20)
  - Formula: correct_tool_calls / total_tool_calls
  - Correct means: right tool, right parameter schema, right sequence constraints.

- Step Efficiency (weight 0.15)
  - Formula: optimal_step_count / actual_step_count, clipped to [0,1]
  - Penalize redundant retries and unnecessary exploratory calls.

- Plan Adherence/Quality (weight 0.15)
  - Rubric: explicit plan, ordered execution, adaptation to failures, and final verification.

- Goal Accuracy (Faithfulness) (weight 0.18)
  - Rubric: outputs and actions are grounded in observed tool evidence and persona goals.
  - Penalize fabricated metrics, fabricated tool outputs, or unsupported recommendations.

### Performance Metrics
- Response Time / Latency (weight 0.06)
  - Measure per task wall-clock from first action to final report.

- Cost per Task (weight 0.03)
  - Compute from model token usage + tool execution overhead if available.

- Human in the Loop Rate (weight 0.01)
  - Formula: tasks_requiring_human_intervention / total_tasks
  - Lower is better.

### Composite Score
Composite = sum(weight_i * metric_i)

## Required Evidence for Judging
For every scenario run, store:
- event input
- full tool call trace (name, args, timestamps, result status)
- intermediate plan states
- final summary report
- pass/fail decision and rubric-level notes

## Suggested Additional Workflow
Incident Mitigation and Safe Rollback:
- Trigger: high latency, elevated non-2xx/3xx rate, or pod restart spikes.
- Expected actions:
  1) validate impact using helm-test, resource-collector, namespace events
  2) identify risky rollout revision via helm-get-history
  3) execute rollback via helm-rollback
  4) verify post-rollback health and publish outcome summary
- Why this matters: tests closed-loop reliability behavior, not only deployment and benchmarking.

## Execution Recommendation
- Start with 5 easy + 5 medium + 5 hard scenarios from the dataset.
- Run each scenario 5 times to measure variance.
- Report mean, p90, and worst-case for each metric.

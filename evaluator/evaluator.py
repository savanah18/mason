"""Simple LLM-based evaluation for agent results using Google GenAI.

Run this inside the `conda-aiops` environment so the repo dependencies and
Google GenAI client are available.

Usage:
    python3 evaluator.py <eval_file.json> [--goal-file <path>] [--model <model>]

Example:
    python3 evaluator.py ../tests/evals/34781cb5-a94e-452c-90e7-bd8ae27c7bdf.json
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml
from google import genai


def load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML file and return parsed dict."""
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON file and return parsed dict."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_scores_path(eval_file: Path) -> Path:
    """Resolve scores output path as tests/evals/<date>/<test-id>/scores.json.

    Falls back to <eval_file.parent>/scores.json if the expected structure is
    not present in the provided path.
    """
    parts = eval_file.resolve().parts
    try:
        idx = parts.index("evals")
    except ValueError:
        return eval_file.parent / "scores.json"

    # Expected path contains: .../tests/evals/<date>/<test-id>/...
    if len(parts) > idx + 2:
        base = Path(*parts[: idx + 1])
        date_part = parts[idx + 1]
        test_id_part = parts[idx + 2]
        return base / date_part / test_id_part / "scores.json"

    return eval_file.parent / "scores.json"


def normalize_eval_record(raw_record: dict[str, Any]) -> dict[str, Any]:
    """Normalize eval record by parsing nested JSON strings."""
    normalized = dict(raw_record)
    for key in ("function_calls", "function_executions", "metadata", "stats"):
        value = normalized.get(key)
        if isinstance(value, str):
            try:
                normalized[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return normalized


def build_system_prompt(goal: dict[str, Any]) -> str:
    """Build system prompt from agent goal specification."""
    description = goal.get("spec", {}).get("description", "No goal description provided")
    
    return f"""You are an LLM judge evaluating an autonomous package deployer agent.

Agent Goal:
{description}

You will be given the following information:
- Task: The task given to the agent
- Result: The final report from the agent
- Function Calls: List of function calls made by the agent
- Function Executions: List of function executions and their results
- Stats: General task statistics

Evaluate the agent on these metrics:

# Agent Metrics
- Task Completion: (0/1) Whether the agent completed the task based on the final report.
- Tool Accuracy: (0-1) Correctness of tool calls and their results based on function executions.
- Step Efficiency: (0-1) Efficiency in using tools and taking steps (consider relevance and necessity).
- Plan Adherence: (0-1) Whether actions align with a logical coherent plan toward task completion.
- Faithfulness: (0-1) Whether the final report accurately reflects evidence from tool calls/executions.

Return a JSON object with these fields:
- "overall_score": number (0-10)
- "verdict": "pass" | "partial" | "fail"
- "summary": string
- "task_completion": number (0-1)
- "tool_accuracy": number (0-1)
- "step_efficiency": number (0-1)
- "plan_adherence": number (0-1)
- "faithfulness": number (0-1)
- "strengths": list of strings
- "issues": list of strings
- "evidence": list of strings with specific citations
"""


def build_user_prompt(eval_record: dict[str, Any]) -> str:
    """Build user prompt from evaluation record."""
    task = eval_record.get("task", "")
    result = eval_record.get("result", "")
    function_calls = eval_record.get("function_calls", [])
    function_executions = eval_record.get("function_executions", [])
    stats = eval_record.get("stats", {})
    
    return f"""Evaluate the agent based on this execution record:

TASK:
{task}

RESULT:
{result}

FUNCTION_CALLS:
{json.dumps(function_calls, indent=2)}

FUNCTION_EXECUTIONS:
{json.dumps(function_executions, indent=2)}

STATS:
{json.dumps(stats, indent=2)}

Provide your evaluation in the specified JSON format."""


def evaluate_with_gemini(
    goal: dict[str, Any],
    eval_record: dict[str, Any],
    model: str,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Evaluate agent result using Google GenAI."""
    client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
    
    system_prompt = build_system_prompt(goal)
    user_prompt = build_user_prompt(eval_record)

    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    
    if not response.text:
        raise RuntimeError("Gemini returned an empty response")
    
    return json.loads(response.text)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Evaluate an agent result with Google GenAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "eval_file",
        type=Path,
        help="Path to the evaluation JSON file (e.g., tests/evals/<workflow_id>.json)",
    )
    parser.add_argument(
        "--goal-file",
        type=Path,
        default=Path("../agent/personas/deployer/goal.yaml"),
        help="Path to the agent goal YAML file (default: ../agent/personas/deployer/goal.yaml)",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-pro",
        help="Google GenAI model name (default: gemini-2.5-pro)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional Google API key. Defaults to GEMINI_API_KEY environment variable or GEMINI_API_KEY.",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    # Handle GEMINI_API_KEY fallback
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    
    goal = load_yaml(args.goal_file)
    eval_record = normalize_eval_record(load_json(args.eval_file))

    result = evaluate_with_gemini(
        goal=goal,
        eval_record=eval_record,
        model=args.model,
        api_key=api_key,
    )

    scores_path = resolve_scores_path(args.eval_file)
    scores_path.parent.mkdir(parents=True, exist_ok=True)
    with scores_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    print(f"Wrote LLM evaluation to: {scores_path}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
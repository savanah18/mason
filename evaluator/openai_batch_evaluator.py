"""Batch evaluator for workflow results using the OpenAI Batch API.

This script mirrors evaluator/batch_evaluator.py but submits the judge call to
OpenAI instead of Gemini. It:
1. Reads workflow result JSON files from tests/evals/<date>/<test-id>
2. Builds an OpenAI batch JSONL request file
3. Optionally submits the file as an OpenAI Batch job
4. Optionally polls job status and downloads output JSONL

Example (build JSONL and submit):
  python3 openai_batch_evaluator.py \
    --date 20260409 \
    --test-id 60835a41-d3c4-43c4-9636-21eff2b33882 \
    --goal-file ../agent/personas/deployer/goal.yaml \
    --submit --poll --download-results
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from batch_evaluator import (
    build_system_prompt,
    build_user_prompt,
    format_tool_catalog_for_prompt,
    get_workflow_ids_union,
    load_json,
    load_text,
    load_tool_catalog_from_jsonl,
    load_yaml,
    normalize_eval_record,
    recover_missing_workflow_results,
)


OPENAI_BATCH_ENDPOINT = "/v1/responses"
TERMINAL_STATES = {
    "completed",
    "failed",
    "cancelled",
    "canceled",
    "expired",
}

JUDGE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "overall_score",
        "verdict",
        "summary",
        "task_completion",
        "tool_accuracy",
        "step_efficiency",
        "plan_adherence",
        "faithfulness",
        "strengths",
        "issues",
        "evidence",
        "failure_attribution",
        "environment_remarks",
    ],
    "properties": {
        "overall_score": {"type": "number"},
        "verdict": {"type": "string", "enum": ["pass", "partial", "fail"]},
        "summary": {"type": "string"},
        "task_completion": {"type": "number"},
        "tool_accuracy": {"type": "number"},
        "step_efficiency": {"type": "number"},
        "plan_adherence": {"type": "number"},
        "faithfulness": {"type": "number"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "issues": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "failure_attribution": {"type": "string", "enum": ["agent", "environment", "mixed"]},
        "environment_remarks": {"type": "string"},
    },
}

JUDGE_TEXT_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "name": "workflow_evaluation",
    "strict": True,
    "schema": JUDGE_OUTPUT_SCHEMA,
}


def get_batch_value(batch_job: Any, key: str, default: Any = None) -> Any:
    if isinstance(batch_job, dict):
        return batch_job.get(key, default)
    return getattr(batch_job, key, default)


def is_openai_batch_terminal(state: str | None) -> bool:
    return bool(state) and state.lower() in TERMINAL_STATES


def upload_jsonl_file(client: OpenAI, jsonl_file: Path, display_name: str) -> str:
    with jsonl_file.open("rb") as handle:
        file_object = client.files.create(file=handle, purpose="batch")

    file_id = getattr(file_object, "id", None)
    if not isinstance(file_id, str) or not file_id.strip():
        raise RuntimeError(f"OpenAI file upload response did not include an id: {file_object}")

    print(f"Uploaded batch input file: {file_id} ({display_name})")
    return file_id


def create_batch_job(client: OpenAI, input_file_id: str, display_name: str) -> Any:
    return client.batches.create(
        input_file_id=input_file_id,
        endpoint=OPENAI_BATCH_ENDPOINT,
        completion_window="24h",
        metadata={"display_name": display_name},
    )


def build_openai_batch_requests(workflow_files: list[Path], model: str, system_prompt: str) -> list[dict[str, Any]]:
    requests_payload: list[dict[str, Any]] = []

    for file_path in workflow_files:
        eval_record = normalize_eval_record(load_json(file_path))
        user_prompt = build_user_prompt(eval_record)
        workflow_id = file_path.stem

        request_payload: dict[str, Any] = {
            "model": model,
            "instructions": system_prompt,
            "input": user_prompt,
            "text": {"format": JUDGE_TEXT_FORMAT},
            "max_output_tokens": 2048,
        }

        requests_payload.append(
            {
                "custom_id": workflow_id,
                "method": "POST",
                "url": OPENAI_BATCH_ENDPOINT,
                "body": request_payload,
            }
        )

    return requests_payload


def validate_batch_request(request_payload: dict[str, Any]) -> None:
    errors: list[str] = []

    custom_id = request_payload.get("custom_id")
    if not isinstance(custom_id, str) or not custom_id.strip():
        errors.append("custom_id must be a non-empty string")

    if request_payload.get("method") != "POST":
        errors.append("method must be POST")

    if request_payload.get("url") != OPENAI_BATCH_ENDPOINT:
        errors.append(f"url must be {OPENAI_BATCH_ENDPOINT}")

    body = request_payload.get("body")
    if not isinstance(body, dict):
        errors.append("body must be an object")
    else:
        model = body.get("model")
        if not isinstance(model, str) or not model.strip():
            errors.append("body.model must be a non-empty string")

        instructions = body.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            errors.append("body.instructions must be a non-empty string")

        user_input = body.get("input")
        if not isinstance(user_input, str) or not user_input.strip():
            errors.append("body.input must be a non-empty string")

        text = body.get("text")
        if not isinstance(text, dict):
            errors.append("body.text must be an object")
        else:
            format_spec = text.get("format")
            if not isinstance(format_spec, dict):
                errors.append("body.text.format must be an object")
            else:
                if format_spec.get("type") != "json_schema":
                    errors.append("body.text.format.type must be json_schema")
                if format_spec.get("strict") is not True:
                    errors.append("body.text.format.strict must be true")
                schema = format_spec.get("schema")
                if not isinstance(schema, dict):
                    errors.append("body.text.format.schema must be an object")
                else:
                    if schema.get("type") != "object":
                        errors.append("schema.type must be object")
                    if schema.get("additionalProperties") is not False:
                        errors.append("schema.additionalProperties must be false")

    if errors:
        raise ValueError(f"Invalid batch request for {custom_id!r}: {'; '.join(errors)}")


def validate_batch_requests(requests_payload: list[dict[str, Any]]) -> None:
    seen_ids: set[str] = set()
    for request_payload in requests_payload:
        validate_batch_request(request_payload)
        custom_id = str(request_payload["custom_id"])
        if custom_id in seen_ids:
            raise ValueError(f"Duplicate custom_id found in batch JSONL: {custom_id}")
        seen_ids.add(custom_id)


def write_jsonl(path: Path, lines: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, ensure_ascii=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"Invalid JSONL line {line_number}: expected object")
            parsed.append(record)
    return parsed


def append_pending_request(requests_file: Path, batch_job: dict[str, Any]) -> None:
    state = str(get_batch_value(batch_job, "status", ""))
    if is_openai_batch_terminal(state):
        return

    job_id = get_batch_value(batch_job, "id")
    if not isinstance(job_id, str) or not job_id.strip():
        return

    requests_file.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if requests_file.exists():
        with requests_file.open("r", encoding="utf-8") as handle:
            existing = {line.strip() for line in handle if line.strip()}

    if job_id in existing:
        return

    with requests_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{job_id}\n")

    print(f"Appended pending batch request: {job_id} -> {requests_file}")


def poll_batch(client: OpenAI, batch_id: str, interval_seconds: int) -> Any:
    while True:
        batch_job = client.batches.retrieve(batch_id)
        state = str(get_batch_value(batch_job, "status", "UNKNOWN"))
        print(f"Batch job state: {state}")
        if is_openai_batch_terminal(state):
            return batch_job
        time.sleep(interval_seconds)


def write_downloaded_file_content(output_file: Path, file_content: Any) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(file_content, bytes):
        output_file.write_bytes(file_content)
        return

    if isinstance(file_content, str):
        output_file.write_text(file_content, encoding="utf-8")
        return

    text_attr = getattr(file_content, "text", None)
    if callable(text_attr):
        text_value = text_attr()
        if isinstance(text_value, bytes):
            output_file.write_bytes(text_value)
        else:
            output_file.write_text(str(text_value), encoding="utf-8")
        return

    if isinstance(text_attr, str):
        output_file.write_text(text_attr, encoding="utf-8")
        return

    if hasattr(file_content, "read"):
        raw_value = file_content.read()
        if isinstance(raw_value, bytes):
            output_file.write_bytes(raw_value)
        else:
            output_file.write_text(str(raw_value), encoding="utf-8")
        return

    output_file.write_text(str(file_content), encoding="utf-8")


def download_batch_results(client: OpenAI, batch_job: Any, output_file: Path) -> None:
    output_file_id = get_batch_value(batch_job, "output_file_id")
    if not isinstance(output_file_id, str) or not output_file_id.strip():
        raise RuntimeError("Batch job has no output_file_id to download")

    file_content = client.files.content(output_file_id)
    write_downloaded_file_content(output_file, file_content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create and run OpenAI Batch evaluations for workflow result files",
    )
    parser.add_argument("--date", required=True, help="Date folder name under tests/evals (e.g., 20260409)")
    parser.add_argument("--test-id", required=True, help="Test/session id folder under tests/evals/<date>")
    parser.add_argument(
        "--goal-file",
        type=Path,
        default=Path("../agent/personas/deployer/goal.yaml"),
        help="Path to the agent goal YAML file",
    )
    parser.add_argument(
        "--evaluation-prompt-file",
        type=Path,
        default=Path(__file__).resolve().parent / "e2e_evaluation_prompt.md",
        help="Path to evaluation rubric/instructions markdown (default: e2e_evaluation_prompt.md)",
    )
    parser.add_argument(
        "--eval-root",
        type=Path,
        default=Path("../tests/evals"),
        help="Root directory for eval outputs",
    )
    parser.add_argument(
        "--agent-tool-files",
        nargs="+",
        type=Path,
        default=None,
        help="One or more JSONL files containing tool definitions for prompt injection",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.4",
        help="OpenAI model to use for batch (must support the Responses API and structured JSON outputs)",
    )
    parser.add_argument("--api-key", default=None, help="OpenAI API key (fallback: OPENAI_API_KEY)")
    parser.add_argument(
        "--jsonl-out",
        type=Path,
        default=None,
        help="Path for generated JSONL batch requests file (default: tests/evals/<date>/<test-id>/<test-id>.jsonl)",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit the generated JSONL as an OpenAI batch job",
    )
    parser.add_argument(
        "--poll",
        action="store_true",
        help="Poll batch job until it reaches a terminal state (requires --submit)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Polling interval in seconds",
    )
    parser.add_argument(
        "--download-results",
        action="store_true",
        help="Download result JSONL when batch succeeds (requires --submit and --poll)",
    )
    parser.add_argument(
        "--result-out",
        type=Path,
        default=None,
        help="Output file path for downloaded batch results JSONL",
    )
    parser.add_argument(
        "--requests-file",
        type=Path,
        default=Path(__file__).resolve().parent / "requests",
        help="Path to pending batch request tracking file",
    )
    parser.add_argument(
        "--result-extract-timeout",
        type=int,
        default=120,
        help="Timeout in seconds per workflow when recovering missing results from metadata",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OpenAI API key. Set OPENAI_API_KEY or pass --api-key.")

    client = OpenAI(api_key=api_key)
    print(f"Using OpenAI model: {args.model}")

    run_dir = args.eval_root / args.date / args.test_id
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created missing run directory: {run_dir}")

    still_missing = recover_missing_workflow_results(
        eval_root=args.eval_root,
        run_dir=run_dir,
        run_date=args.date,
        test_id=args.test_id,
        timeout_seconds=args.result_extract_timeout,
    )

    union_ids, available_json_ids = get_workflow_ids_union(run_dir)
    workflow_files = [run_dir / f"{workflow_id}.json" for workflow_id in union_ids if workflow_id in available_json_ids]

    if still_missing:
        print(
            "Proceeding with available workflow files only. "
            f"Recovered={len(available_json_ids)} Missing={len(still_missing)}"
        )
    print(f"Union of workflows: {len(union_ids)} total (metadata + directory)")
    print(f"Available JSON files: {len(available_json_ids)}")

    goal = load_yaml(args.goal_file)
    evaluation_prompt = load_text(args.evaluation_prompt_file)

    tool_catalog_files = [p if p.is_absolute() else Path.cwd() / p for p in (args.agent_tool_files or [])]
    for tool_file in tool_catalog_files:
        if not tool_file.exists() or not tool_file.is_file():
            raise FileNotFoundError(f"Agent tool file not found: {tool_file}")

    tool_catalog = load_tool_catalog_from_jsonl(tool_catalog_files)
    available_tools = format_tool_catalog_for_prompt(tool_catalog)
    system_prompt = build_system_prompt(goal, evaluation_prompt, available_tools)

    if not workflow_files:
        print(
            f"No workflow JSON files found in: {run_dir}. "
            "Batch setup is complete; skipping JSONL generation and batch submission."
        )
        return

    jsonl_out = args.jsonl_out or (run_dir / f"{args.test_id}.jsonl")
    request_lines = build_openai_batch_requests(workflow_files, args.model, system_prompt)
    validate_batch_requests(request_lines)
    write_jsonl(jsonl_out, request_lines)
    if read_jsonl(jsonl_out) != request_lines:
        raise RuntimeError("Generated JSONL failed round-trip validation")

    print(f"Discovered workflow files: {len(workflow_files)}")
    print(f"Wrote batch JSONL: {jsonl_out}")

    if not args.submit:
        return

    display_name = f"eval-{args.date}-{args.test_id}"
    input_file_id = upload_jsonl_file(client, jsonl_out, display_name)
    batch_job = create_batch_job(client, input_file_id, display_name)
    print(f"Created batch job: {get_batch_value(batch_job, 'id')}")
    append_pending_request(args.requests_file, batch_job)

    if not args.poll:
        return

    batch_id = get_batch_value(batch_job, "id")
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise RuntimeError(f"OpenAI batch response did not include an id: {batch_job}")

    final_job = poll_batch(client, batch_id, args.poll_interval)
    print(f"Final batch state: {get_batch_value(final_job, 'status')}")

    if args.download_results and str(get_batch_value(final_job, "status", "")).lower() == "completed":
        result_out = args.result_out or (run_dir / "batch_results.jsonl")
        download_batch_results(client, final_job, result_out)
        print(f"Downloaded batch results: {result_out}")


if __name__ == "__main__":
    main()
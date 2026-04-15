"""Batch evaluator for workflow results using Gemini Batch API (JSONL file method).

This script:
1. Creates a cached system instruction (reusable up to 1 hour)
2. Reads workflow result JSON files from tests/evals/<date>/<test-id>
3. Builds a JSONL batch request file referencing the cache
4. Optionally submits the file as a Gemini Batch job
5. Optionally polls job status and downloads output JSONL

Example (create cache, build JSONL, and submit):
  python3 batch_evaluator.py \
    --date 20260409 \
    --test-id 60835a41-d3c4-43c4-9636-21eff2b33882 \
    --goal-file ../agent/personas/deployer/goal.yaml \
    --create-cache --submit --poll --download-results

Example (reuse existing cache):
  python3 batch_evaluator.py \
    --date 20260409 \
    --test-id 60835a41-d3c4-43c4-9636-21eff2b33882 \
    --goal-file ../agent/personas/deployer/goal.yaml \
    --cache-name projects/my-project/cachedContents/abc123def456 \
    --submit --poll --download-results
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from google import genai
from google.genai import types


TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        return handle.read().strip()


def normalize_eval_record(raw_record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(raw_record)
    for key in ("function_calls", "function_executions", "metadata", "stats"):
        value = normalized.get(key)
        if isinstance(value, str):
            try:
                normalized[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return normalized


def build_system_prompt(goal: dict[str, Any], evaluation_prompt: str) -> str:
    # Support both Goal CRD files (spec.description) and prompt files (system/prompts).
    description = (
        goal.get("spec", {}).get("description")
        or goal.get("system")
        or goal.get("prompts")
        or "No goal description provided"
    )

    return f"""You are an LLM judge evaluating an autonomous package deployer agent.

You are evaluating the agent's performance on the following general goal:
{description}

You will be given the following information:
- Task: The task given to the agent
- Result: The final report from the agent
- Function Calls: List of function calls made by the agent
- Function Executions: List of function executions and their results
- Stats: General task statistics

{evaluation_prompt}
"""


def is_prompt_too_small_error(exc: Exception) -> bool:
    msg = str(exc)
    return "Cached content is too small" in msg and "INVALID_ARGUMENT" in msg


def build_user_prompt(eval_record: dict[str, Any]) -> str:
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


def discover_workflow_files(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Workflow result directory not found: {root}")
    files = sorted(p for p in root.glob("*.json") if p.is_file())
    if not files:
        raise FileNotFoundError(f"No workflow JSON files found in: {root}")
    return files


def load_workflow_ids_from_metadata(run_dir: Path) -> list[str]:
    metadata_file = run_dir / "metadata"
    if not metadata_file.exists():
        return []

    ids: list[str] = []
    seen: set[str] = set()
    with metadata_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            workflow_id = line.strip()
            if not workflow_id or workflow_id in seen:
                continue
            seen.add(workflow_id)
            ids.append(workflow_id)
    return ids


def recover_missing_workflow_results(
    eval_root: Path,
    run_dir: Path,
    run_date: str,
    test_id: str,
    timeout_seconds: int,
) -> list[str]:
    """Recover missing workflow JSON results by calling tests/evals/tools/result_extractor.py."""
    expected_ids = load_workflow_ids_from_metadata(run_dir)
    if not expected_ids:
        print(f"No metadata file found or empty metadata in: {run_dir}")
        return []

    extractor = eval_root / "tools" / "result_extractor.py"
    if not extractor.exists():
        raise FileNotFoundError(f"result_extractor.py not found: {extractor}")

    existing_ids = {p.stem for p in run_dir.glob("*.json") if p.is_file()}
    missing_ids = [workflow_id for workflow_id in expected_ids if workflow_id not in existing_ids]
    if not missing_ids:
        print("All workflow results are already present; no recovery needed.")
        return []

    print(
        "Recovering missing workflow results from Redis: "
        f"{len(missing_ids)} missing out of {len(expected_ids)} expected"
    )

    env = os.environ.copy()
    env["RUN_DATE"] = run_date
    env["SESSION_ID"] = test_id
    env["TEST_ID"] = test_id

    for workflow_id in missing_ids:
        print(f"Recovering workflow result: {workflow_id}")
        subprocess.run(
            [
                sys.executable,
                str(extractor),
                workflow_id,
                str(timeout_seconds),
            ],
            cwd=str(eval_root),
            env=env,
            check=False,
        )

    refreshed_ids = {p.stem for p in run_dir.glob("*.json") if p.is_file()}
    still_missing = [workflow_id for workflow_id in expected_ids if workflow_id not in refreshed_ids]
    if still_missing:
        print(
            "WARNING: Some workflow results are still missing after recovery: "
            f"{len(still_missing)}"
        )
    return still_missing


def create_cache(
    client: genai.Client,
    model: str,
    system_prompt: str,
    ttl_seconds: int = 86400,
) -> tuple[str, dict[str, Any]]:
    """Create a cached system instruction and return (cache_name, cache_metadata)."""
    print("DEBUG", system_prompt)
    cached_content = client.caches.create(
        model=model,
        config=types.CreateCachedContentConfig(
            system_instruction=system_prompt,
            ttl=f"{ttl_seconds}s",
        ),
    )

    cache_name = cached_content.name
    cache_metadata = {
        "cache_name": cache_name,
        "model": model,
        "ttl_seconds": ttl_seconds,
        "created_at": cached_content.create_time,
        "expire_at": cached_content.expire_time,
    }
    print(f"Created cache: {cache_name}")
    print(f"  Expires: {cached_content.expire_time}")
    return cache_name, cache_metadata


def save_cache_metadata(run_dir: Path, cache_metadata: dict[str, Any]) -> None:
    """Save cache metadata to file for reuse."""
    metadata_file = run_dir / "cache_metadata.json"
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    with metadata_file.open("w", encoding="utf-8") as f:
        json.dump(cache_metadata, f, indent=2, default=str)
    print(f"Saved cache metadata: {metadata_file}")


def load_cache_metadata(run_dir: Path) -> dict[str, Any] | None:
    """Load cache metadata from previous run if available."""
    metadata_file = run_dir / "cache_metadata.json"
    if metadata_file.exists():
        with metadata_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    return None


def get_workflow_ids_union(run_dir: Path) -> tuple[list[str], set[str]]:
    """Get union of workflow IDs from metadata and directory.
    
    Returns:
        (union_ids, available_json_ids) - List of all workflow IDs and set of IDs with existing JSON files
    """
    metadata_ids = load_workflow_ids_from_metadata(run_dir)
    dir_ids = {p.stem for p in run_dir.glob("*.json") if p.is_file()}
    union_ids = list(dict.fromkeys(metadata_ids))  # Preserve metadata order, remove duplicates
    union_ids.extend(sorted(dir_ids - set(union_ids)))  # Add any dir-only IDs not in metadata
    return union_ids, dir_ids


def build_jsonl_requests(
    workflow_files: list[Path],
    cache_name: str | None,
    system_prompt: str | None = None,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []

    for file_path in workflow_files:
        eval_record = normalize_eval_record(load_json(file_path))
        user_prompt = build_user_prompt(eval_record)
        workflow_id = file_path.stem

        request_payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generation_config": {
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        }

        if cache_name:
            request_payload["cached_content"] = cache_name
        else:
            # Manual system instruction fallback when cache creation is not possible.
            if not system_prompt:
                raise RuntimeError("system_prompt is required when cache_name is not provided")
            request_payload["system_instruction"] = system_prompt

        requests.append({"key": workflow_id, "request": request_payload})

    return requests


def write_jsonl(path: Path, lines: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, ensure_ascii=True) + "\n")


def submit_batch(
    client: genai.Client,
    model: str,
    jsonl_file: Path,
    display_name: str,
):
    uploaded_file = client.files.upload(
        file=str(jsonl_file),
        config=types.UploadFileConfig(
            display_name=display_name,
            mime_type="jsonl",
        ),
    )

    batch_job = client.batches.create(
        model=model,
        src=uploaded_file.name,
        config={"display_name": display_name},
    )
    return batch_job


def append_pending_request(requests_file: Path, batch_job: Any) -> None:
    """Append pending batch job name to a tracking file, avoiding duplicates."""
    state = getattr(getattr(batch_job, "state", None), "name", None)
    if state in TERMINAL_STATES:
        return

    job_name = getattr(batch_job, "name", None)
    if not job_name:
        return

    requests_file.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if requests_file.exists():
        with requests_file.open("r", encoding="utf-8") as handle:
            existing = {line.strip() for line in handle if line.strip()}

    if job_name in existing:
        return

    with requests_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{job_name}\n")

    print(f"Appended pending batch request: {job_name} -> {requests_file}")


def poll_batch(client: genai.Client, job_name: str, interval_seconds: int) -> Any:
    while True:
        batch_job = client.batches.get(name=job_name)
        state = batch_job.state.name
        print(f"Batch job state: {state}")
        if state in TERMINAL_STATES:
            return batch_job
        time.sleep(interval_seconds)


def download_batch_results(client: genai.Client, batch_job: Any, output_file: Path) -> None:
    if not batch_job.dest or not batch_job.dest.file_name:
        raise RuntimeError("Batch job has no file output to download")

    content = client.files.download(file=batch_job.dest.file_name)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as handle:
        handle.write(content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create and run Gemini Batch evaluations for workflow result files",
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
    parser.add_argument("--model", default="gemini-3.1-flash-lite-preview", help="Gemini model to use for batch")
    parser.add_argument("--api-key", default=None, help="Google API key (fallback: GEMINI_API_KEY/GOOGLE_API_KEY)")
    parser.add_argument(
        "--jsonl-out",
        type=Path,
        default=None,
        help="Path for generated JSONL batch requests file (default: tests/evals/<date>/<test-id>/<test-id>.jsonl)",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit the generated JSONL as a Gemini batch job",
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
        "--create-cache",
        action="store_true",
        help="Create a new cached system instruction (1-hour TTL)",
    )
    parser.add_argument(
        "--cache-name",
        type=str,
        default=None,
        help="Use existing cache by name (e.g., projects/my-project/cachedContents/abc123)",
    )
    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=3600,
        help="TTL for new cache in seconds (default: 3600 = 1 hour)",
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

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

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
    
    # Get union of workflows from metadata and directory
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
    system_prompt = build_system_prompt(goal, evaluation_prompt)

    # Determine cache name
    cache_name: str | None = args.cache_name
    cache_metadata: dict[str, Any] | None = None
    use_manual_system_injection = False

    if not cache_name:
        if args.create_cache:
            # Create a fresh cache when explicitly requested.
            try:
                cache_name, cache_metadata = create_cache(
                    client,
                    args.model,
                    system_prompt,
                    ttl_seconds=args.cache_ttl,
                )
                save_cache_metadata(run_dir, cache_metadata)
            except Exception as exc:
                if is_prompt_too_small_error(exc):
                    print("Cache creation failed: prompt too small. Falling back to manual system prompt injection.")
                    use_manual_system_injection = True
                    cache_name = None
                else:
                    raise
        else:
            # Try to load existing cache metadata only when not forcing creation.
            cache_metadata = load_cache_metadata(run_dir)
            if cache_metadata:
                cache_name = cache_metadata.get("cache_name")
                print(f"Reusing existing cache: {cache_name}")
            else:
                raise RuntimeError(
                    "No cache specified. Use --cache-name, --create-cache, or ensure cache_metadata.json exists."
                )

    if not cache_name and not use_manual_system_injection:
        raise RuntimeError("Failed to determine cache name")

    if not workflow_files:
        print(
            f"No workflow JSON files found in: {run_dir}. "
            "Cache setup is complete; skipping JSONL generation and batch submission."
        )
        return

    # Build and write JSONL with cache reference
    jsonl_out = args.jsonl_out or (run_dir / f"{args.test_id}.jsonl")
    request_lines = build_jsonl_requests(
        workflow_files,
        cache_name,
        system_prompt=system_prompt if use_manual_system_injection else None,
    )
    write_jsonl(jsonl_out, request_lines)

    print(f"Discovered workflow files: {len(workflow_files)}")
    print(f"Cache: {cache_name}")
    print(f"Wrote batch JSONL: {jsonl_out}")

    if not args.submit:
        return

    display_name = f"eval-{args.date}-{args.test_id}"
    batch_job = submit_batch(client, args.model, jsonl_out, display_name)
    print(f"Created batch job: {batch_job.name}")
    append_pending_request(args.requests_file, batch_job)

    if not args.poll:
        return

    final_job = poll_batch(client, batch_job.name, args.poll_interval)
    print(f"Final batch state: {final_job.state.name}")

    if args.download_results and final_job.state.name == "JOB_STATE_SUCCEEDED":
        result_out = args.result_out or (run_dir / "batch_results.jsonl")
        download_batch_results(client, final_job, result_out)
        print(f"Downloaded batch results: {result_out}")


if __name__ == "__main__":
    main()

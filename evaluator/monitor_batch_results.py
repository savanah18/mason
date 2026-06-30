"""Monitor Gemini batch jobs directly from the Gemini Batch API.

This script:
1. Lists available batch jobs directly from Gemini Batch API
2. Polls each job's current state via Gemini Batch API
3. Optionally downloads output files for succeeded jobs
4. Repeats until no non-terminal jobs remain (unless run once)

Example (single pass):
  python3 monitor_batch_results.py --once

Example (continuous polling):
  python3 monitor_batch_results.py --poll-interval 30 --download-results
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Any

from google import genai


TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor Gemini batch jobs via Gemini Batch API")
    parser.add_argument(
        "--api-key",
        default=None,
        help="Google API key (fallback: GEMINI_API_KEY/GOOGLE_API_KEY)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Polling interval in seconds for continuous mode",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single status check pass and exit",
    )
    parser.add_argument(
        "--download-results",
        action="store_true",
        help="Download output files for succeeded jobs",
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "batch_results",
        help="Directory to store downloaded batch output files",
    )
    return parser.parse_args()


def list_all_batch_jobs(client: genai.Client) -> list[Any]:
    """List all visible batch jobs from API, handling iterator/pager variants."""
    try:
        response = client.batches.list()
    except TypeError:
        response = client.batches.list(config={})

    jobs = list(response)
    jobs.sort(key=lambda job: getattr(job, "name", ""))
    return jobs


def safe_job_id(job_name: str) -> str:
    return job_name.replace("/", "__")


def download_result_file(client: genai.Client, batch_job: Any, output_file: Path) -> None:
    if not batch_job.dest or not batch_job.dest.file_name:
        print(f"No downloadable output for job {batch_job.name}")
        return

    content = client.files.download(file=batch_job.dest.file_name)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as handle:
        handle.write(content)
    print(f"Downloaded results: {output_file}")


def check_jobs(client: genai.Client, args: argparse.Namespace) -> tuple[int, int]:
    jobs = list_all_batch_jobs(client)
    if not jobs:
        print("No batch jobs returned by API.")
        return 0, 0

    pending_count = 0
    terminal_count = 0

    for batch_job in jobs:
        job_name = getattr(batch_job, "name", "<unknown>")
        state = getattr(getattr(batch_job, "state", None), "name", "UNKNOWN")
        print(f"{job_name} -> {state}")

        if state in TERMINAL_STATES:
            terminal_count += 1
            if args.download_results and state == "JOB_STATE_SUCCEEDED":
                output_file = args.result_dir / f"{safe_job_id(job_name)}.jsonl"
                if output_file.exists():
                    print(f"Results already exist; skipping download: {output_file}")
                    continue
                try:
                    download_result_file(client, batch_job, output_file)
                except Exception as exc:  # noqa: BLE001
                    print(f"Failed downloading results for {job_name}: {exc}")
        else:
            pending_count += 1

    print(
        "Summary: "
        f"total={len(jobs)} pending={pending_count} terminal={terminal_count}"
    )
    return len(jobs), pending_count


def main() -> None:
    args = parse_args()

    api_key = args.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    if args.once:
        check_jobs(client, args)
        return

    while True:
        total, pending = check_jobs(client, args)
        if total == 0 or pending == 0:
            print("No pending jobs remaining; exiting monitor loop.")
            return
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()

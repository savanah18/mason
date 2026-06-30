"""Monitor OpenAI batch jobs directly from the OpenAI Batch API.

This script mirrors evaluator/monitor_batch_results.py but reads OpenAI batch
job status instead of Gemini batch job status.

Example (single pass):
  python3 monitor_openai_batch_results.py --once

Example (continuous polling):
  python3 monitor_openai_batch_results.py --poll-interval 30 --download-results
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Any

from openai import OpenAI


OPENAI_API_BASE = "/v1/"
TERMINAL_STATES = {
    "completed",
    "failed",
    "cancelled",
    "canceled",
    "expired",
}


def get_batch_value(batch_job: Any, key: str, default: Any = None) -> Any:
    if isinstance(batch_job, dict):
        return batch_job.get(key, default)
    return getattr(batch_job, key, default)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor OpenAI batch jobs via the OpenAI Batch API")
    parser.add_argument(
        "--api-key",
        default=None,
        help="OpenAI API key (fallback: OPENAI_API_KEY)",
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
        default=Path(__file__).resolve().parent / "batch_results" / "openai",
        help="Directory to store downloaded batch output files",
    )
    return parser.parse_args()


def list_all_batch_jobs(client: OpenAI) -> list[Any]:
    jobs = list(client.batches.list())
    jobs.sort(key=lambda job: str(get_batch_value(job, "id", "")))
    return jobs


def safe_job_id(job_id: str) -> str:
    return job_id.replace("/", "__")


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


def download_result_file(client: OpenAI, batch_job: Any, output_file: Path) -> None:
    output_file_id = get_batch_value(batch_job, "output_file_id")
    if not isinstance(output_file_id, str) or not output_file_id.strip():
        print(f"No downloadable output for job {get_batch_value(batch_job, 'id')}")
        return

    file_content = client.files.content(output_file_id)
    write_downloaded_file_content(output_file, file_content)
    print(f"Downloaded results: {output_file}")


def check_jobs(client: OpenAI, args: argparse.Namespace) -> tuple[int, int]:
    jobs = list_all_batch_jobs(client)
    if not jobs:
        print("No batch jobs returned by API.")
        return 0, 0

    pending_count = 0
    terminal_count = 0

    for batch_job in jobs:
        job_id = str(get_batch_value(batch_job, "id", "<unknown>"))
        state = str(get_batch_value(batch_job, "status", "UNKNOWN"))
        print(f"{job_id} -> {state}")

        if state.lower() in TERMINAL_STATES:
            terminal_count += 1
            if args.download_results and state.lower() == "completed":
                output_file = args.result_dir / f"{safe_job_id(job_id)}.jsonl"
                if output_file.exists():
                    print(f"Results already exist; skipping download: {output_file}")
                    continue
                try:
                    download_result_file(client, batch_job, output_file)
                except Exception as exc:  # noqa: BLE001
                    print(f"Failed downloading results for {job_id}: {exc}")
        else:
            pending_count += 1

    print(
        "Summary: "
        f"total={len(jobs)} pending={pending_count} terminal={terminal_count}"
    )
    return len(jobs), pending_count


def main() -> None:
    args = parse_args()

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OpenAI API key. Set OPENAI_API_KEY or pass --api-key.")

    client = OpenAI(api_key=api_key)

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
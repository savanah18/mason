"""Aggregate LLM evaluation scores per batch JSONL file.

This script scans evaluator batch result JSONL files and computes per-batch
summary metrics, including score averages, verdict distribution, metric means,
and failure attribution counts.

Examples:
  python3 evaluation_score_aggregation.py
  python3 evaluation_score_aggregation.py --batch-files batch_results/foo.jsonl batch_results/bar.jsonl
  python3 evaluation_score_aggregation.py --output-json aggregated_scores.json --output-csv aggregated_scores.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

import redis


NUMERIC_FIELDS = [
    "overall_score",
    "task_completion",
    "tool_accuracy",
    "step_efficiency",
    "plan_adherence",
    "faithfulness",
    "plan_quality_score",
    "task_decomposition_accuracy",
    "read_only_integrity",
    "argument_hallucination_rate",
]

MOCK_PLAN_METRICS = [
    "plan_quality_score",
    "task_decomposition_accuracy",
    "read_only_integrity",
    "argument_hallucination_rate",
]

OTHER_METRICS = [
    "overall_score",
    "task_completion",
    "tool_accuracy",
    "step_efficiency",
    "plan_adherence",
    "faithfulness",
]

VERDICTS = ["pass", "partial", "fail"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate evaluator scores per batch JSONL file and enrich with Redis workflow metrics",
    )
    parser.add_argument(
        "--persona",
        required=True,
        help="Agent persona (e.g., 'deployer', 'chat') for Redis memory key construction",
    )
    parser.add_argument(
        "--batch-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "batch_results",
        help="Directory containing batch result JSONL files (default: evaluator/batch_results)",
    )
    parser.add_argument(
        "--batch-files",
        nargs="+",
        type=Path,
        default=None,
        help="Explicit batch JSONL files to aggregate",
    )
    parser.add_argument(
        "--pattern",
        default="*.jsonl",
        help="Glob pattern for batch files when using --batch-dir (default: *.jsonl)",
    )
    parser.add_argument(
        "--redis-host",
        default="127.0.0.1",
        help="Redis host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=6379,
        help="Redis port (default: 6379)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write aggregation output as JSON",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional path to write batch summary as CSV",
    )
    parser.add_argument(
        "--run-mode",
        choices=["mock-plan", "mock-test", "e2e"],
        default="e2e",
        help="Run mode: mock-plan (only planning metrics), mock-test (all except planning), e2e (all except planning) (default: e2e)",
    )
    return parser.parse_args()


def get_batch_files(args: argparse.Namespace) -> list[Path]:
    if args.batch_files:
        files = [p if p.is_absolute() else Path.cwd() / p for p in args.batch_files]
    else:
        batch_dir = args.batch_dir if args.batch_dir.is_absolute() else Path.cwd() / args.batch_dir
        files = sorted(batch_dir.glob(args.pattern))

    existing_files = [p for p in files if p.exists() and p.is_file()]
    if not existing_files:
        raise FileNotFoundError(f"No batch JSONL files found in: {batch_dir if not args.batch_files else 'specified files'}")
    return existing_files


def extract_evaluation_payload(record: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Extract evaluation payload and workflow key from record."""
    response = record.get("response")
    if not isinstance(response, dict):
        return None, None

    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None, None

    first_candidate = candidates[0]
    if not isinstance(first_candidate, dict):
        return None, None

    content = first_candidate.get("content")
    if not isinstance(content, dict):
        return None, None

    parts = content.get("parts")
    if not isinstance(parts, list):
        return None, None

    payload = None
    for part in parts:
        if not isinstance(part, dict):
            continue
        text_value = part.get("text")
        if not isinstance(text_value, str):
            continue
        try:
            test_payload = json.loads(text_value)
        except json.JSONDecodeError:
            continue
        if isinstance(test_payload, dict):
            payload = test_payload
            break

    workflow_key = record.get("key")
    return payload, workflow_key


def summarize_batch(
    batch_file: Path,
    persona: str,
    redis_client: redis.Redis,
) -> dict[str, Any]:
    total_lines = 0
    parsed_payloads = 0
    parse_errors = 0

    verdict_counter: Counter[str] = Counter()
    attribution_counter: Counter[str] = Counter()

    numeric_buckets: dict[str, list[float]] = {field: [] for field in NUMERIC_FIELDS}
    stats_buckets: dict[str, list[float]] = {}
    latest_reference: str | None = None
    redis_records_fetched = 0

    with batch_file.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            total_lines += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue

            if not isinstance(record, dict):
                parse_errors += 1
                continue

            payload, record_key = extract_evaluation_payload(record)
            if payload is None:
                parse_errors += 1
                continue

            parsed_payloads += 1

            verdict = payload.get("verdict")
            if isinstance(verdict, str):
                verdict_counter[verdict.lower()] += 1

            attribution = payload.get("failure_attribution")
            if isinstance(attribution, str):
                attribution_counter[attribution.lower()] += 1

            for field in NUMERIC_FIELDS:
                value = payload.get(field)
                if isinstance(value, (int, float)):
                    numeric_buckets[field].append(float(value))

            # Fetch Redis memory for this workflow key
            if record_key:
                redis_hash_key = f"workflow:dev:{persona}:{record_key}"
                # print(f"Fetching Redis data for key: {redis_hash_key}")
                try:
                    memory_dict = redis_client.hgetall(redis_hash_key)
                    if memory_dict:
                        redis_records_fetched += 1

                        # Extract and parse stats
                        stats_raw = memory_dict.get(b"stats")
                        if stats_raw:
                            stats = json.loads(stats_raw)
                            for stat_key, stat_value in stats.items():
                                if isinstance(stat_value, (int, float)) and stat_value is not None:
                                    if stat_key not in stats_buckets:
                                        stats_buckets[stat_key] = []
                                    stats_buckets[stat_key].append(float(stat_value))

                        # Extract latest reference from optimization
                        optimization_raw = memory_dict.get(b"optimization")
                        if optimization_raw:
                            optimization = json.loads(optimization_raw)
                            reference = optimization.get("reference")
                            if isinstance(reference, str):
                                # Use max(reference) semantics to represent the latest reference.
                                latest_reference = (
                                    reference
                                    if latest_reference is None
                                    else max(latest_reference, reference)
                                )
                except Exception as exc:
                    print(
                        f"Warning: Failed to fetch Redis data for {redis_hash_key}: {exc}"
                    )

    summary: dict[str, Any] = {
        "batch_file": str(batch_file),
        "total_records": total_lines,
        "parsed_records": parsed_payloads,
        "parse_errors": parse_errors,
        "redis_records_fetched": redis_records_fetched,
        "verdict_counts": {name: verdict_counter.get(name, 0) for name in VERDICTS},
        "failure_attribution_counts": dict(sorted(attribution_counter.items())),
    }

    for field, values in numeric_buckets.items():
        if values:
            summary[f"avg_{field}"] = round(mean(values), 4)
            summary[f"min_{field}"] = round(min(values), 4)
            summary[f"max_{field}"] = round(max(values), 4)
        else:
            summary[f"avg_{field}"] = None
            summary[f"min_{field}"] = None
            summary[f"max_{field}"] = None

    for field, values in sorted(stats_buckets.items()):
        if values:
            summary[f"redis_avg_{field}"] = round(mean(values), 4)
            summary[f"redis_min_{field}"] = round(min(values), 4)
            summary[f"redis_max_{field}"] = round(max(values), 4)
        else:
            summary[f"redis_avg_{field}"] = None
            summary[f"redis_min_{field}"] = None
            summary[f"redis_max_{field}"] = None

    summary["latest_reference"] = latest_reference

    if parsed_payloads:
        summary["pass_rate"] = round(verdict_counter.get("pass", 0) / parsed_payloads, 4)
    else:
        summary["pass_rate"] = None

    return summary


def print_table(summaries: list[dict[str, Any]], run_mode: str = "e2e") -> None:
    # Determine which metrics to display based on run_mode
    if run_mode == "mock-plan":
        metric_fields = MOCK_PLAN_METRICS
        metric_headers = [
            "avg_plan_quality",
            "avg_task_decomp",
            "avg_read_only",
            "avg_hallucination",
        ]
    else:
        # mock-test and e2e show other metrics
        metric_fields = OTHER_METRICS
        metric_headers = [
            "avg_score",
            "avg_task",
            "avg_tool",
            "avg_step",
            "avg_plan",
            "avg_faith",
        ]

    headers = [
        "batch",
        "records",
        "parsed",
        "errors",
        "redis_fetched",
    ] + metric_headers + [
        "pass",
        "partial",
        "fail",
        "pass_rate",
        "latest_reference",
    ]

    rows: list[list[str]] = []
    for item in summaries:
        batch_name = Path(item["batch_file"]).name
        verdicts = item.get("verdict_counts", {})
        
        metric_values = []
        if run_mode == "mock-plan":
            metric_values = [
                "-" if item.get("avg_plan_quality_score") is None else f"{item['avg_plan_quality_score']:.2f}",
                "-" if item.get("avg_task_decomposition_accuracy") is None else f"{item['avg_task_decomposition_accuracy']:.2f}",
                "-" if item.get("avg_read_only_integrity") is None else f"{item['avg_read_only_integrity']:.2f}",
                "-" if item.get("avg_argument_hallucination_rate") is None else f"{item['avg_argument_hallucination_rate']:.2f}",
            ]
        else:
            metric_values = [
                "-" if item.get("avg_overall_score") is None else f"{item['avg_overall_score']:.2f}",
                "-" if item.get("avg_task_completion") is None else f"{item['avg_task_completion']:.2f}",
                "-" if item.get("avg_tool_accuracy") is None else f"{item['avg_tool_accuracy']:.2f}",
                "-" if item.get("avg_step_efficiency") is None else f"{item['avg_step_efficiency']:.2f}",
                "-" if item.get("avg_plan_adherence") is None else f"{item['avg_plan_adherence']:.2f}",
                "-" if item.get("avg_faithfulness") is None else f"{item['avg_faithfulness']:.2f}",
            ]
        
        row = [
            batch_name,
            str(item.get("total_records", 0)),
            str(item.get("parsed_records", 0)),
            str(item.get("parse_errors", 0)),
            str(item.get("redis_records_fetched", 0)),
        ] + metric_values + [
            str(verdicts.get("pass", 0)),
            str(verdicts.get("partial", 0)),
            str(verdicts.get("fail", 0)),
            "-" if item.get("pass_rate") is None else f"{item['pass_rate']:.2%}",
            "-" if not isinstance(item.get("latest_reference"), str) or not item.get("latest_reference", "").strip() else item.get("latest_reference", "").strip(),
        ]
        rows.append(row)

    widths = [len(h) for h in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def format_row(values: list[str]) -> str:
        return " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    separator = "-+-".join("-" * width for width in widths)
    print(format_row(headers))
    print(separator)
    for row in rows:
        print(format_row(row))


def print_redis_stats_table(summaries: list[dict[str, Any]]) -> None:
    stat_names = sorted(
        {
            key.replace("redis_avg_", "")
            for item in summaries
            for key in item.keys()
            if key.startswith("redis_avg_")
        }
    )

    if not stat_names:
        return

    headers = ["batch", "stat", "avg", "min", "max"]

    rows: list[list[str]] = []

    for item in summaries:
        batch_name = Path(item["batch_file"]).name
        for stat_name in stat_names:
            avg_value = item.get(f"redis_avg_{stat_name}")
            min_value = item.get(f"redis_min_{stat_name}")
            max_value = item.get(f"redis_max_{stat_name}")
            rows.append(
                [
                    batch_name,
                    stat_name,
                    "-" if avg_value is None else f"{avg_value:.4f}",
                    "-" if min_value is None else f"{min_value:.4f}",
                    "-" if max_value is None else f"{max_value:.4f}",
                ]
            )

    widths = [len(h) for h in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def format_row(values: list[str]) -> str:
        return " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    separator = "-+-".join("-" * width for width in widths)
    print()
    print("Redis Stats Summary")
    print(format_row(headers))
    print(separator)
    for row in rows:
        print(format_row(row))


def print_reference_table(summaries: list[dict[str, Any]]) -> None:
    rows: list[list[str]] = []
    for item in summaries:
        batch_name = Path(item["batch_file"]).name
        reference = item.get("latest_reference")
        reference_value = "-" if not isinstance(reference, str) or not reference.strip() else reference.strip()
        rows.append([batch_name, reference_value])

    headers = ["batch", "latest_reference"]
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def format_row(values: list[str]) -> str:
        return " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    separator = "-+-".join("-" * width for width in widths)
    print()
    print("Reference Summary")
    print(format_row(headers))
    print(separator)
    for row in rows:
        print(format_row(row))


def write_json(output_path: Path, summaries: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump({"batches": summaries}, handle, indent=2)
        handle.write("\n")


def write_csv(output_path: Path, summaries: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "batch_file",
        "total_records",
        "parsed_records",
        "parse_errors",
        "redis_records_fetched",
        "pass_count",
        "partial_count",
        "fail_count",
        "pass_rate",
        "latest_reference",
    ]
    for field in NUMERIC_FIELDS:
        fieldnames.extend([f"avg_{field}", f"min_{field}", f"max_{field}"])

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in summaries:
            verdicts = item.get("verdict_counts", {})
            row: dict[str, Any] = {
                "batch_file": item.get("batch_file"),
                "total_records": item.get("total_records"),
                "parsed_records": item.get("parsed_records"),
                "parse_errors": item.get("parse_errors"),
                "redis_records_fetched": item.get("redis_records_fetched", 0),
                "pass_count": verdicts.get("pass", 0),
                "partial_count": verdicts.get("partial", 0),
                "fail_count": verdicts.get("fail", 0),
                "pass_rate": item.get("pass_rate"),
                "latest_reference": item.get("latest_reference"),
            }
            for field in NUMERIC_FIELDS:
                row[f"avg_{field}"] = item.get(f"avg_{field}")
                row[f"min_{field}"] = item.get(f"min_{field}")
                row[f"max_{field}"] = item.get(f"max_{field}")
            writer.writerow(row)


def main() -> None:
    args = parse_args()
    batch_files = get_batch_files(args)
    
    # Initialize Redis client
    redis_client = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        decode_responses=False,
    )
    
    summaries = [
        summarize_batch(batch_file, args.persona, redis_client)
        for batch_file in batch_files
    ]

    print_table(summaries, run_mode=args.run_mode)
    print_redis_stats_table(summaries)
    print_reference_table(summaries)

    if args.output_json:
        write_json(args.output_json, summaries)
        print(f"Wrote JSON output: {args.output_json}")
    if args.output_csv:
        write_csv(args.output_csv, summaries)
        print(f"Wrote CSV output: {args.output_csv}")


if __name__ == "__main__":
    main()
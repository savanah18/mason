"""Collect raw evaluation metrics from batch JSONL files with Redis workflow data.

This script scans evaluator batch result JSONL files and collects individual
records with all evaluation metrics (numeric and non-numeric) along with
corresponding Redis workflow data without aggregation.

Examples:
  python3 collect_raw_metrics.py --persona deployer
  python3 collect_raw_metrics.py --persona deployer --batch-dir batch_results --pattern "*.jsonl"
  python3 collect_raw_metrics.py --persona deployer --output-json raw_metrics.json --output-csv raw_metrics.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import redis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect raw evaluator metrics from batch JSONL files with Redis workflow data",
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
        help="Explicit batch JSONL files to process",
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
        help="Optional path to write raw metrics as JSON (one record per line)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional path to write raw metrics as CSV",
    )
    parser.add_argument(
        "--skip-redis",
        action="store_true",
        help="Skip Redis lookups (faster, but without workflow data)",
    )
    return parser.parse_args()


def get_batch_files(args: argparse.Namespace) -> list[Path]:
    if args.batch_files:
        files = [p if p.is_absolute() else Path.cwd() / p for p in args.batch_files]
        source_desc = "specified files"
    else:
        batch_dir = args.batch_dir if args.batch_dir.is_absolute() else Path.cwd() / args.batch_dir
        files = sorted(batch_dir.glob(args.pattern))
        source_desc = str(batch_dir)

    existing_files = [p for p in files if p.exists() and p.is_file()]
    if not existing_files:
        raise FileNotFoundError(f"No batch JSONL files found in: {source_desc}")
    return existing_files


def extract_evaluation_payload(record: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Extract evaluation payload and workflow key from record."""
    def parse_payload_text(text_value: Any) -> dict[str, Any] | None:
        if not isinstance(text_value, str):
            return None
        try:
            parsed = json.loads(text_value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    # Gemini format: response.candidates[0].content.parts[].text
    response = record.get("response")
    if isinstance(response, dict):
        candidates = response.get("candidates")
        if isinstance(candidates, list) and candidates:
            first_candidate = candidates[0]
            if isinstance(first_candidate, dict):
                content = first_candidate.get("content")
                if isinstance(content, dict):
                    parts = content.get("parts")
                    if isinstance(parts, list):
                        for part in parts:
                            if not isinstance(part, dict):
                                continue
                            payload = parse_payload_text(part.get("text"))
                            if payload is not None:
                                return payload, record.get("key")

    # OpenAI batch format: response.body.output[-1].content[].text
    if isinstance(response, dict):
        body = response.get("body")
        if isinstance(body, dict):
            output_items = body.get("output")
            if isinstance(output_items, list):
                for output_item in reversed(output_items):
                    if not isinstance(output_item, dict):
                        continue
                    content_items = output_item.get("content")
                    if not isinstance(content_items, list):
                        continue
                    for content_item in content_items:
                        if not isinstance(content_item, dict):
                            continue
                        payload = parse_payload_text(content_item.get("text"))
                        if payload is not None:
                            return payload, record.get("custom_id") or record.get("key")

    return None, None


def fetch_redis_workflow_data(
    redis_client: redis.Redis,
    workflow_key: str,
    persona: str,
) -> dict[str, Any]:
    """Fetch and parse all workflow data from Redis."""
    redis_hash_key = f"workflow:dev:{persona}:{workflow_key}"
    redis_data: dict[str, Any] = {}

    try:
        memory_dict = redis_client.hgetall(redis_hash_key)
        if not memory_dict:
            return redis_data

        def parse_json_field(field_name: str) -> Any | None:
            raw_value = memory_dict.get(field_name) or memory_dict.get(field_name.encode("utf-8"))
            if raw_value is None:
                return None
            if isinstance(raw_value, bytes):
                raw_value = raw_value.decode("utf-8")
            return json.loads(raw_value)

        for field_name in ("stats", "optimization", "workflow", "actions"):
            parsed_value = parse_json_field(field_name)
            if parsed_value is None:
                continue
            redis_data.update(flatten_json_object(parsed_value, prefix=f"redis_{field_name}"))

    except Exception as exc:
        redis_data["redis_error"] = str(exc)

    return redis_data


def collect_metrics(
    batch_files: list[Path],
    persona: str,
    redis_client: redis.Redis | None = None,
    skip_redis: bool = False,
) -> list[dict[str, Any]]:
    """Collect all raw metrics from batch files with Redis workflow data."""
    all_records = []
    parse_errors = 0
    payloads_found = 0
    payloads_missing = 0

    for batch_file in batch_files:
        print(f"Processing: {batch_file}")

        with batch_file.open("r", encoding="utf-8") as handle:
            for line_num, raw_line in enumerate(handle, 1):
                line = raw_line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    parse_errors += 1
                    print(f"  Parse error on line {line_num}: {e}")
                    continue

                if not isinstance(record, dict):
                    parse_errors += 1
                    continue

                payload, workflow_key = extract_evaluation_payload(record)

                # Build collection record
                collection_record = {
                    "batch_file": str(batch_file.name),
                    "line_number": line_num,
                    "workflow_key": workflow_key,
                    "has_payload": payload is not None,
                }

                if payload is None:
                    payloads_missing += 1
                else:
                    payloads_found += 1
                    # Add all evaluation payload fields
                    collection_record.update(payload)

                # Fetch and add Redis data
                if redis_client and not skip_redis and workflow_key:
                    redis_data = fetch_redis_workflow_data(
                        redis_client,
                        workflow_key,
                        persona,
                    )
                    collection_record.update(redis_data)

                all_records.append(collection_record)

    print(f"\nTotal records collected: {len(all_records)}")
    print(f"Parse errors: {parse_errors}")
    print(f"Payloads found: {payloads_found}")
    print(f"Payloads missing: {payloads_missing}")

    return all_records


def write_json_records(
    records: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Write records as JSONL (one record per line)."""
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    print(f"Wrote {len(records)} records to {output_path}")


def write_csv_records(
    records: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Write records as CSV with all flattened fields."""
    if not records:
        print("No records to write")
        return

    # Collect all unique field names
    all_keys = set()
    for record in records:
        all_keys.update(flatten_json_object(record).keys())

    fieldnames = sorted(all_keys)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for record in records:
            flattened = flatten_json_object(record)
            writer.writerow(flattened)

    print(f"Wrote {len(records)} records to {output_path}")


def flatten_json_object(obj: Any, prefix: str = "", separator: str = "_") -> dict[str, Any]:
    """Recursively flatten a JSON-compatible object into a single-level dict."""
    flattened: dict[str, Any] = {}

    if isinstance(obj, dict):
        if not obj and prefix:
            flattened[prefix] = {}
            return flattened

        for key, value in obj.items():
            next_prefix = f"{prefix}{separator}{key}" if prefix else str(key)
            flattened.update(flatten_json_object(value, next_prefix, separator))
        return flattened

    if isinstance(obj, list):
        if not obj and prefix:
            flattened[prefix] = []
            return flattened

        if not obj:
            return flattened

        for index, value in enumerate(obj):
            next_prefix = f"{prefix}{separator}{index}" if prefix else str(index)
            flattened.update(flatten_json_object(value, next_prefix, separator))
        return flattened

    if prefix:
        flattened[prefix] = obj
    return flattened


def print_sample(records: list[dict[str, Any]], count: int = 3) -> None:
    """Print sample records for inspection."""
    print(f"\n=== Sample Records (first {min(count, len(records))}) ===")
    for i, record in enumerate(records[:count], 1):
        print(f"\n--- Record {i} ---")
        print(json.dumps(record, indent=2, default=str))


def main():
    args = parse_args()

    # Get batch files
    try:
        batch_files = get_batch_files(args)
        print(f"Found {len(batch_files)} batch files:")
        for f in batch_files:
            print(f"  - {f}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # Connect to Redis if needed
    redis_client = None
    if not args.skip_redis:
        try:
            redis_client = redis.Redis(
                host=args.redis_host,
                port=args.redis_port,
                password=None,
                decode_responses=True,
            )
            redis_client.ping()
            print(f"Connected to Redis at {args.redis_host}:{args.redis_port}")
        except Exception as e:
            print(f"Warning: Could not connect to Redis: {e}")
            print("Continuing without Redis data...")
            redis_client = None

    # Collect metrics
    records = collect_metrics(
        batch_files,
        args.persona,
        redis_client,
        args.skip_redis,
    )

    if not records:
        print("No records collected")
        return

    # Print sample records
    print_sample(records, count=2)

    # Write outputs
    if args.output_json:
        write_json_records(records, args.output_json)

    if args.output_csv:
        write_csv_records(records, args.output_csv)

    if not args.output_json and not args.output_csv:
        print("\nNote: No output files specified. Use --output-json or --output-csv to save results.")


if __name__ == "__main__":
    main()

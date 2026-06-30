"""Export system prompts from Redis to a flattened CSV file.

This script scans Redis hash keys matching a system prompt pattern, flattens
any JSON objects stored in hash fields, and writes one CSV row per key.

Example:
  python3 export_system_prompts_from_redis.py \
    --key-pattern "system-prompts:deployer:*" \
    --output-csv output/system_prompts_deployer.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import redis


DEFAULT_KEY_PATTERN = "system-prompts:deployer:*"
EXCLUDED_FIELDS = {"feedback", "prompt"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export system prompt hashes from Redis to a flattened CSV file.",
    )
    parser.add_argument(
        "--key-pattern",
        default=DEFAULT_KEY_PATTERN,
        help=f"Redis key pattern to scan (default: {DEFAULT_KEY_PATTERN})",
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
        "--redis-db",
        type=int,
        default=0,
        help="Redis DB index (default: 0)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path(__file__).resolve().parent / "output" / "system_prompts_deployer.csv",
        help="Path to write the flattened CSV export.",
    )
    parser.add_argument(
        "--separator",
        default="_",
        help="Separator used when flattening nested keys (default: _)",
    )
    return parser.parse_args()


def parse_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text:
        return ""

    try:
        return json.loads(text)
    except Exception:
        return value


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


def flatten_redis_hash(redis_key: str, redis_hash: dict[str, Any], separator: str = "_") -> dict[str, Any]:
    """Flatten a Redis hash into a CSV-friendly record."""
    record: dict[str, Any] = {"redis_key": redis_key}

    for field_name, raw_value in redis_hash.items():
        if field_name in EXCLUDED_FIELDS:
            continue

        parsed_value = parse_json_value(raw_value)

        if isinstance(parsed_value, (dict, list)):
            record.update(flatten_json_object(parsed_value, prefix=field_name, separator=separator))
        else:
            record[field_name] = parsed_value

    return record


def collect_system_prompts(
    redis_client: redis.Redis,
    key_pattern: str,
    separator: str = "_",
) -> list[dict[str, Any]]:
    """Collect and flatten all Redis hashes matching the given pattern."""
    records: list[dict[str, Any]] = []
    matched_keys = 0
    empty_hashes = 0
    parse_errors = 0

    for redis_key in sorted(redis_client.scan_iter(match=key_pattern)):
        matched_keys += 1
        try:
            hash_data = redis_client.hgetall(redis_key) or {}
        except Exception as exc:
            parse_errors += 1
            records.append(
                {
                    "redis_key": redis_key,
                    "redis_error": str(exc),
                }
            )
            continue

        if not hash_data:
            empty_hashes += 1
            records.append({"redis_key": redis_key})
            continue

        records.append(flatten_redis_hash(redis_key, hash_data, separator=separator))

    print(f"Matched Redis keys: {matched_keys}")
    print(f"Empty Redis hashes: {empty_hashes}")
    print(f"Redis parse errors: {parse_errors}")
    print(f"Records collected: {len(records)}")
    return records


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_csv_records(records: list[dict[str, Any]], output_path: Path) -> None:
    if not records:
        print("No records to write")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = sorted({key for record in records for key in record.keys()})

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for record in records:
            writer.writerow({key: _csv_value(record.get(key, "")) for key in fieldnames})

    print(f"Wrote {len(records)} records to {output_path}")


def main() -> None:
    args = parse_args()

    redis_client = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        db=args.redis_db,
        decode_responses=True,
    )

    try:
        redis_client.ping()
    except Exception as exc:
        raise RuntimeError(f"Could not connect to Redis at {args.redis_host}:{args.redis_port}: {exc}") from exc

    records = collect_system_prompts(redis_client, args.key_pattern, separator=args.separator)
    write_csv_records(records, args.output_csv)


if __name__ == "__main__":
    main()
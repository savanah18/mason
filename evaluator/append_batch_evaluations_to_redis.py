"""Append evaluator batch JSONL outputs into existing workflow Redis hashes.

Reads JSONL files under evaluator/batch_results/<persona>/e2e (or a custom path),
extracts:
  record["key"]
  record["response"]["candidates"][0]["content"]["parts"][0]["text"]

Then appends entries into a hash field for:
  workflow:dev:persona:<key>

By default, entries are appended to hash field "evaluations" as a JSON array.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import redis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append evaluation text from batch JSONL results to workflow Redis hashes.",
    )
    parser.add_argument(
        "--persona",
        required=True,
        help="Persona name (e.g., deployer, chat).",
    )
    parser.add_argument(
        "--batch-dir",
        type=Path,
        default=None,
        help="Directory containing JSONL files. Defaults to evaluator/batch_results/<persona>/e2e.",
    )
    parser.add_argument(
        "--pattern",
        default="*.jsonl",
        help="Glob pattern for JSONL files in --batch-dir (default: *.jsonl).",
    )
    parser.add_argument(
        "--redis-host",
        default="127.0.0.1",
        help="Redis host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=6379,
        help="Redis port (default: 6379).",
    )
    parser.add_argument(
        "--redis-db",
        type=int,
        default=0,
        help="Redis DB index (default: 0).",
    )
    parser.add_argument(
        "--redis-key-prefix",
        default="workflow:dev:persona:",
        help="Redis hash key prefix (default: workflow:dev:persona:).",
    )
    parser.add_argument(
        "--hash-field",
        default="evaluations",
        help="Hash field name used to store appended evaluations (default: evaluations).",
    )
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help="Create hash field even when the workflow hash key does not exist.",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable dedupe check (default behavior dedupes by source file + line + text hash).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse files and print summary without writing to Redis.",
    )
    return parser.parse_args()


def resolve_batch_dir(args: argparse.Namespace) -> Path:
    if args.batch_dir is not None:
        return args.batch_dir if args.batch_dir.is_absolute() else Path.cwd() / args.batch_dir

    return Path(__file__).resolve().parent / "batch_results" / args.persona / "e2e"


def extract_record_data(record: dict[str, Any]) -> tuple[str | None, str | None]:
    key = record.get("key")
    if not isinstance(key, str) or not key.strip():
        return None, None

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
    if not isinstance(parts, list) or not parts:
        return None, None

    first_part = parts[0]
    if not isinstance(first_part, dict):
        return None, None

    text = first_part.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, None

    return key, text


def safe_load_json_list(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def build_dedupe_key(batch_file: Path, line_number: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{batch_file.name}:{line_number}:{digest}"


def main() -> None:
    args = parse_args()
    batch_dir = resolve_batch_dir(args)

    if not batch_dir.exists() or not batch_dir.is_dir():
        raise FileNotFoundError(f"Batch directory not found: {batch_dir}")

    batch_files = sorted(batch_dir.glob(args.pattern))
    batch_files = [path for path in batch_files if path.is_file()]
    if not batch_files:
        raise FileNotFoundError(f"No JSONL files found in {batch_dir} matching {args.pattern}")

    redis_client: redis.Redis | None = None
    if not args.dry_run:
        redis_client = redis.Redis(
            host=args.redis_host,
            port=args.redis_port,
            db=args.redis_db,
            decode_responses=True,
        )
        redis_client.ping()

    total_lines = 0
    parsed_records = 0
    invalid_records = 0
    missing_hash_keys = 0
    updated_hash_keys = 0
    appended_entries = 0
    deduped_entries = 0

    for batch_file in batch_files:
        with batch_file.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                total_lines += 1

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    invalid_records += 1
                    continue

                if not isinstance(record, dict):
                    invalid_records += 1
                    continue

                workflow_key, eval_text = extract_record_data(record)
                if workflow_key is None or eval_text is None:
                    invalid_records += 1
                    continue

                parsed_records += 1

                redis_key = f"{args.redis_key_prefix}{workflow_key}"
                print(f"Processing workflow_key: {workflow_key} that will be stored in Redis hash key: {redis_key}")
                dedupe_key = build_dedupe_key(batch_file, line_number, eval_text)

                entry = {
                    "source_file": str(batch_file),
                    "source_line": line_number,
                    "ingested_at": datetime.now(UTC).isoformat(),
                    "dedupe_key": dedupe_key,
                    "evaluation_text": eval_text,
                }

                if args.dry_run:
                    appended_entries += 1
                    continue

                assert redis_client is not None

                if not redis_client.exists(redis_key):
                    if not args.create_missing:
                        missing_hash_keys += 1
                        continue

                existing_raw = redis_client.hget(redis_key, args.hash_field)
                print("DEBUG", existing_raw)
                existing_entries = safe_load_json_list(existing_raw)

                if not args.no_dedupe:
                    existing_keys = {
                        item.get("dedupe_key")
                        for item in existing_entries
                        if isinstance(item.get("dedupe_key"), str)
                    }
                    if dedupe_key in existing_keys:
                        deduped_entries += 1
                        continue

                existing_entries.append(entry)
                redis_client.hset(
                    redis_key,
                    mapping={
                        args.hash_field: json.dumps(existing_entries, ensure_ascii=False),
                    },
                )

                appended_entries += 1
                updated_hash_keys += 1

    print("Append evaluations summary")
    print(f"  batch_dir: {batch_dir}")
    print(f"  files_scanned: {len(batch_files)}")
    print(f"  total_lines: {total_lines}")
    print(f"  parsed_records: {parsed_records}")
    print(f"  invalid_records: {invalid_records}")
    print(f"  appended_entries: {appended_entries}")
    print(f"  deduped_entries: {deduped_entries}")
    print(f"  updated_hash_keys: {updated_hash_keys}")
    print(f"  missing_hash_keys: {missing_hash_keys}")
    print(f"  dry_run: {args.dry_run}")


if __name__ == "__main__":
    main()

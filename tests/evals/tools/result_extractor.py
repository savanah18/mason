import redis
import sys
import json
import time
import os
from pathlib import Path

# TODO Prefix all information with test case id as well
def _find_workflow_key(r, workflow_id: str, persona: str | None):
    if persona:
        return f"workflow:{persona}:{workflow_id}"

    pattern = f"workflow:*:{workflow_id}"
    matched = list(r.scan_iter(match=pattern, count=100))
    if not matched:
        return None
    if len(matched) > 1:
        print(f"Multiple workflow keys matched {pattern}. Using first: {matched[0]}")
    return matched[0]


def main(
    workflow_id: str,
    timeout: int = 30,
    interval: int = 2,
    persona: str | None = None,
    run_date: str | None = None,
    session_id: str | None = None,
):
    try:
        # Connect to Redis
        r = redis.Redis(
            host="127.0.0.1",
            port=6379,
            password=None,
            decode_responses=True
        )

        print(
            f"Retrieving result for workflow_id={workflow_id}, "
            f"persona={persona or '*'} (timeout={timeout}s)..."
        )

        start = time.time()
        value = None
        key = None

        # Keep checking until timeout
        while time.time() - start < timeout:
            key = _find_workflow_key(r, workflow_id, persona)
            if not key:
                print("No matching workflow key yet, retrying...")
                time.sleep(interval)
                continue

            value = r.hgetall(key)
            if value:  # found something
                break
            print("No data yet, retrying...")
            time.sleep(interval)

        if not value:
            print(f"WARNING. No data found for {key} within {timeout} seconds.")
            return

        # Save to JSON file under: <date>/<session-id>/<workflow-id>.json
        out_date = run_date or os.environ.get("RUN_DATE")
        out_session = session_id or os.environ.get("SESSION_ID") or os.environ.get("TEST_ID")

        if out_date and out_session:
            output_dir = Path(out_date) / out_session
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{workflow_id}.json"
        else:
            # Backward-compatible fallback if run metadata was not provided.
            output_file = Path(f"{workflow_id}.json")

        with open(output_file, "w") as f:
            json.dump(value, f, indent=2)

        print(f"Saved result to {output_file}")

    except Exception as e:
        print(f"WARNING. Issue extracting results: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python result_extractor.py "
            "<WORKFLOW_ID> [timeout_seconds] [persona] [run_date] [session_id]"
        )
        sys.exit(1)
    workflow_id_arg = sys.argv[1]
    timeout_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    persona_arg = sys.argv[3] if len(sys.argv) > 3 else None
    run_date_arg = sys.argv[4] if len(sys.argv) > 4 else None
    session_id_arg = sys.argv[5] if len(sys.argv) > 5 else None
    main(
        workflow_id_arg,
        timeout_arg,
        persona=persona_arg,
        run_date=run_date_arg,
        session_id=session_id_arg,
    )

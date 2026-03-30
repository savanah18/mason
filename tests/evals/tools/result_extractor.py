import redis
import sys
import json
import time

def main(workflow_id: str, timeout: int = 30, interval: int = 2):
    try:
        # Connect to Redis
        r = redis.Redis(
            host="127.0.0.1",
            port=6379,
            password=None,
            decode_responses=True
        )

        key = "workflow:" + workflow_id
        print(f"Retrieving result for {key} (timeout={timeout}s)...")

        start = time.time()
        value = None

        # Keep checking until timeout
        while time.time() - start < timeout:
            value = r.hgetall(key)
            if value:  # found something
                break
            print("No data yet, retrying...")
            time.sleep(interval)

        if not value:
            print(f"WARNING. No data found for {key} within {timeout} seconds.")
            return

        # Save to JSON file
        output_file = f"{workflow_id}.json"
        with open(output_file, "w") as f:
            json.dump(value, f, indent=2)

        print(f"Saved result to {output_file}")

    except Exception as e:
        print(f"WARNING. Issue extracting results: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_redis.py <WORKFLOW_ID> [timeout_seconds]")
        sys.exit(1)
    workflow_id_arg = sys.argv[1]
    timeout_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    main(workflow_id_arg, timeout_arg)

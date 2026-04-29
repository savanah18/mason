import yaml
import subprocess
import os
import sys
import uuid
import re
from pathlib import Path
from datetime import datetime

def run_script(script: str, env: dict):
    """Run a multi-line shell script with given environment variables."""
    if not script.strip():
        return
    try:
        print("Running ", script)
        subprocess.run(script, shell=True, check=True, env=env)
    except subprocess.CalledProcessError as e:
        print(f"Script failed: {e}")
        raise

def run_workflow(yaml_file: str, test_id: str, date_str: str, workflow_ids_list: list, metadata_file: Path = None):
    """Run a workflow and save results to structured directory."""
    # Load YAML
    with open(yaml_file, "r") as f:
        workflow = yaml.safe_load(f)

    # Export YAML fields as environment variables
    env = os.environ.copy()
    WORKFLOW_ID = str(uuid.uuid4())
    
    # Create output directory structure root: <date>/<test-id>/
    output_dir = Path(date_str) / test_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save workflow ID to tracking list and append immediately to metadata file
    workflow_ids_list.append(WORKFLOW_ID)
    if metadata_file:
        with open(metadata_file, "a") as f:
            f.write(WORKFLOW_ID + "\n")
    
    env["CHAT_PROMPT"] = workflow.get("chat-prompt", "").replace("<WORKFLOW_ID>", str(WORKFLOW_ID))
    env["EXPECTED_EVENT_INPUT"] = workflow.get("expected-event-input", "")
    env["PRE_CONDITION_SCRIPT"] = workflow.get("pre-condition-script", "")
    env["EXECUTION_SCRIPT"] = workflow.get("execution-script", "")
    env["OUTPUT_RETRIEVAL_SCRIPT"] = workflow.get("output-retrieval-script", "")
    env["WORKFLOW_ID"] = WORKFLOW_ID
    env["EXPECTED_EXEC_TIME_SECONDS"] = workflow.get("expected-execution-time", "60")
    env["RUN_DATE"] = date_str
    env["TEST_ID"] = test_id
    env["SESSION_ID"] = test_id
    env["OUTPUT_DIR"] = str(output_dir)

    # Run scripts in order
    print(f"Running workflow {WORKFLOW_ID} in {output_dir}")
    print("Running pre-condition script...")
    print(workflow.get("pre-condition-script", ""))
    run_script(workflow.get("pre-condition-script", ""), env)

    workflow_error = None
    try:
        print("Running execution script...")
        run_script(workflow.get("execution-script", ""), env)

        print("Running output retrieval script...")
        run_script(workflow.get("output-retrieval-script", ""), env)
    except subprocess.CalledProcessError as e:
        workflow_error = e
    finally:
        try:
            print("Running post condition script...")
            run_script(workflow.get("post-condition-script", ""), env)
        except subprocess.CalledProcessError as post_err:
            if workflow_error is None:
                raise
            print(f"Post-condition script also failed: {post_err}")

    if workflow_error is not None:
        raise workflow_error


def find_matching_scenarios(regex_prefix: str):
    scenarios_root = Path(__file__).resolve().parent / "test_scenarios"
    matcher = re.compile(rf"^{regex_prefix}")
    scenario_files = sorted(scenarios_root.rglob("*.yaml"))

    return [
        str(path)
        for path in scenario_files
        if matcher.match(path.stem)
    ]


def load_completed_scenarios(checkpoint_file: Path) -> set:
    """Load the set of already completed scenarios from checkpoint file."""
    if not checkpoint_file.exists():
        return set()
    
    with open(checkpoint_file, "r") as f:
        return {line.strip() for line in f if line.strip()}


def append_completed_scenario(checkpoint_file: Path, scenario: str):
    """Append a completed scenario to the checkpoint file."""
    with open(checkpoint_file, "a") as f:
        f.write(scenario + "\n")


def main(argv):
    if len(argv) < 2:
        print(
            "Usage: python test_runner.py <workflow.yaml> [--test-id <test_id>]\n"
            "   or: python test_runner.py --regex-prefix <regex_prefix> [--test-id <test_id>] [--include-completed]"
        )
        return 1

    args = argv[1:]
    test_id = None
    include_completed = False

    if "--test-id" in args:
        idx = args.index("--test-id")
        if idx + 1 >= len(args):
            print("Missing value for --test-id")
            return 1
        test_id = args[idx + 1]
        del args[idx:idx + 2]

    if "--include-completed" in args:
        include_completed = True
        args.remove("--include-completed")

    if not args:
        print("Missing workflow file or --regex-prefix")
        return 1

    # Generate test ID and date for this test run
    if not test_id:
        test_id = str(uuid.uuid4())
    date_str = datetime.now().strftime("%Y%m%d")
    workflow_ids = []
    
    # Set up metadata file and checkpoint file for continuous appending
    metadata_dir = Path(date_str) / test_id
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = metadata_dir / "metadata"
    checkpoint_file = metadata_dir / "completed_scenarios"
    # Create empty files if they don't exist
    metadata_file.touch()
    checkpoint_file.touch()

    if args[0] == "--regex-prefix":
        if len(args) < 2:
            print("Missing value for --regex-prefix")
            return 1

        regex_prefix = args[1]
        scenario_files = find_matching_scenarios(regex_prefix)
        if not scenario_files:
            print(f"No scenario files matched prefix regex: {regex_prefix}")
            return 1

        # Load completed scenarios and filter them out (unless --include-completed)
        completed = load_completed_scenarios(checkpoint_file) if not include_completed else set()
        scenarios_to_run = [s for s in scenario_files if s not in completed]
        
        if completed:
            print(f"Skipping {len(completed)} already completed scenarios")
        print(f"Running {len(scenarios_to_run)} scenarios (total: {len(scenario_files)})")
        if include_completed:
            print("(--include-completed flag set, re-running all scenarios)")

        failures = 0
        for scenario in scenarios_to_run:
            print(f"\n=== Running scenario: {scenario} ===")
            try:
                run_workflow(scenario, test_id, date_str, workflow_ids, metadata_file)
                # Mark scenario as completed in checkpoint
                append_completed_scenario(checkpoint_file, scenario)
            except subprocess.CalledProcessError:
                failures += 1
                print(f"Scenario failed: {scenario}")
        
        print(
            f"\nCompleted {len(scenarios_to_run)} scenarios, "
            f"failures: {failures}"
        )
        print(f"Test ID: {test_id}")
        print(f"Results saved to: {metadata_dir}")
        print(f"Metadata file: {metadata_file}")
        print(f"Checkpoint file: {checkpoint_file}")
        return 1 if failures else 0

    # Single workflow run
    run_workflow(args[0], test_id, date_str, workflow_ids, metadata_file)
    
    print(f"Test ID: {test_id}")
    print(f"Results saved to: {metadata_dir}")
    print(f"Metadata file: {metadata_file}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

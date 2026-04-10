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

    print("Running execution script...")
    run_script(workflow.get("execution-script", ""), env)

    print("Running output retrieval script...")
    run_script(workflow.get("output-retrieval-script", ""), env)


def find_matching_scenarios(regex_prefix: str):
    scenarios_root = Path(__file__).resolve().parent / "test_scenarios"
    matcher = re.compile(rf"^{regex_prefix}")
    scenario_files = sorted(scenarios_root.rglob("*.yaml"))

    return [
        str(path)
        for path in scenario_files
        if matcher.match(path.stem)
    ]


def main(argv):
    if len(argv) < 2:
        print(
            "Usage: python test_runner.py <workflow.yaml>\n"
            "   or: python test_runner.py --regex-prefix <regex_prefix>"
        )
        return 1

    # Generate test ID and date for this test run
    test_id = str(uuid.uuid4())
    date_str = datetime.now().strftime("%Y%m%d")
    workflow_ids = []
    
    # Set up metadata file for continuous appending
    metadata_dir = Path(date_str) / test_id
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata_file = metadata_dir / "metadata"
    # Create empty metadata file
    metadata_file.touch()

    if argv[1] == "--regex-prefix":
        if len(argv) < 3:
            print("Missing value for --regex-prefix")
            return 1

        regex_prefix = argv[2]
        scenario_files = find_matching_scenarios(regex_prefix)
        if not scenario_files:
            print(f"No scenario files matched prefix regex: {regex_prefix}")
            return 1

        failures = 0
        for scenario in scenario_files:
            print(f"\n=== Running scenario: {scenario} ===")
            try:
                run_workflow(scenario, test_id, date_str, workflow_ids, metadata_file)
            except subprocess.CalledProcessError:
                failures += 1
                print(f"Scenario failed: {scenario}")
        
        print(
            f"\nCompleted {len(scenario_files)} scenarios, "
            f"failures: {failures}"
        )
        print(f"Test ID: {test_id}")
        print(f"Results saved to: {metadata_dir}")
        print(f"Metadata file: {metadata_file}")
        return 1 if failures else 0

    # Single workflow run
    run_workflow(argv[1], test_id, date_str, workflow_ids, metadata_file)
    
    print(f"Test ID: {test_id}")
    print(f"Results saved to: {metadata_dir}")
    print(f"Metadata file: {metadata_file}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

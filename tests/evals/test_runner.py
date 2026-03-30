import yaml
import subprocess
import os
import sys
import uuid

def run_script(script: str, env: dict):
    """Run a multi-line shell script with given environment variables."""
    if not script.strip():
        return
    try:
        print("Running ", script)
        subprocess.run(script, shell=True, check=True, env=env)
    except subprocess.CalledProcessError as e:
        print(f"Script failed: {e}")

def main(yaml_file):
    # Load YAML
    with open(yaml_file, "r") as f:
        workflow = yaml.safe_load(f)

    # Export YAML fields as environment variables
    env = os.environ.copy()
    WORKFLOW_ID = str(uuid.uuid4())
    env["CHAT_PROMPT"] = workflow.get("chat-prompt", "").replace("<WORKFLOW_ID>", str(WORKFLOW_ID))
    env["EXPECTED_EVENT_INPUT"] = workflow.get("expected-event-input", "")
    env["PRE_CONDITION_SCRIPT"] = workflow.get("pre-condition-script", "")
    env["EXECUTION_SCRIPT"] = workflow.get("execution-script", "")
    env["OUTPUT_RETRIEVAL_SCRIPT"] = workflow.get("output-retrieval-script", "")
    env["WORKFLOW_ID"] = WORKFLOW_ID
    env["EXPECTED_EXEC_TIME_SECONDS"] = workflow.get("expected-execution-time", "60")

    # Run scripts in order
    print("Running pre-condition script...")
    print(workflow.get("pre-condition-script", ""))
    run_script(workflow.get("pre-condition-script", ""), env)

    print("Running execution script...")
    run_script(workflow.get("execution-script", ""), env)

    print("Running output retrieval script...")
    run_script(workflow.get("output-retrieval-script", ""), env)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python runner.py workflow.yaml")
        sys.exit(1)
    main(sys.argv[1])

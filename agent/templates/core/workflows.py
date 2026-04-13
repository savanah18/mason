import os
import re
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
import json

import redis

from ..mixins.json import FromJsonMixin

@dataclass
class WorkflowExecution():
    session_id: str = None
    workflow_id: str = None
    task: str = ""
    result: str = ""
    function_calls: List = field(default_factory=list)
    function_executions: List = field(default_factory=list)
    all_tools_verified: bool = False
    workflow_latency: float = None
    model_generation_latency: float = None
    task_total_token_cost: int = None
    task_prompt_token_cost: int = None
    task_gen_token_cost: int = None
    ttft: float = None
    agent_type: str = "chat" # personas
    agent_mode: str = "dev" # prod, eval, dev
    # prompt reference
    system_prompt_ref: str = None

    def num_function_calls(self):
        return len(self.function_calls)

    def num_function_execs(self):
        return len(self.function_executions)

    def execution_success_rate(self):
        try:
            return self.num_function_execs() / self.num_function_calls()
        except ZeroDivisionError:
            return None

    def execution_failure_rate(self):
        try:
            return 1 - self.execution_success_rate()
        except ZeroDivisionError:
            return None
        except TypeError:
            return None



    def record_workflow_state(self):
        try:
            mem_client = redis.Redis(host="redis", port=6379, decode_responses=True)
            mem_client.hset(
                f"workflow:{self.agent_mode}:{self.agent_type}:{str(self.workflow_id)}",
                mapping={
                    "metadata": json.dumps({
                        "agent_type": self.agent_type,
                        "session_id": str(self.session_id),
                        "workflow_id": str(self.workflow_id),
                        "agent_mode": self.agent_mode
                    }),
                    "task": str(self.task),
                    "result": str(self.result),
                    "function_calls": json.dumps(self.function_calls),
                    "function_executions": json.dumps(self.function_executions),
                    "stats": json.dumps({
                        "all_tools_verified": self.all_tools_verified,
                        "num_function_execs": self.num_function_execs(),
                        "execution_success_rate": self.execution_success_rate(),
                        "execution_failure_rate": self.execution_failure_rate(),
                        "workflow_latency": self.workflow_latency,
                        "model_generation_latency": self.model_generation_latency,
                        "task_total_token_cost": self.task_total_token_cost,
                        "task_prompt_token_cost": self.task_prompt_token_cost,
                        "task_gen_token_cost": self.task_gen_token_cost,
                        "ttft": self.ttft,
                    }),
                    "optimization": json.dumps({
                        "prompt": "UNPROCESSED", # placeholder for future optimization logic
                        "reference": self.system_prompt_ref, # for potential future use in optimization
                    })

                }
            )
        except Exception as e:
            raise(e)


def verify_execution_status(exec_id, llm_result):
    r = redis.Redis(host="redis", port=6379, decode_responses=True)
    record = r.hgetall(f"tool_execution:{exec_id}")
    runtime_result = json.loads(record["result"])
    return runtime_result == llm_result

def extract_exec_id(message) -> bool:
    try:
        # Try checking if function call is traceable
        content = json.loads(message.get('content'))
        exec_id = content.get('exec_id', None)
        return exec_id
    except Exception as e:
        return None

#  process_workflow_execution
def process_workflow_execution(
    session_id, 
    workflow_id, 
    task="",  
    response_messages: List[Dict] = [],
    agent_type: str = "chat",
) -> WorkflowExecution:
    workflow_exec: WorkflowExecution = WorkflowExecution(
        session_id = session_id,
        workflow_id = workflow_id,
        task = task,
        agent_type = agent_type,
    )
    function_called = set()
    num_function_calls = 0
    for message in response_messages:
        if message.get('role') == "assistant": 
            # print("DEBUG!!!!", message)
            if 'function_id' in message.get('extra'):
                function_called.add(message.get('extra').get('function_id'))
                workflow_exec.function_calls.append(message)
                num_function_calls +=1
        if message.get('role') == "function" and 'function_id' in message.get('extra'):
            exec_id = extract_exec_id(message) # check if tool is traceable
            if exec_id:
                # for built-in, we attest.
                content = json.loads(message.get('content'))
                if verify_execution_status(exec_id, content):
                    function_called.remove(message.get('extra').get('function_id'))
                    workflow_exec.function_executions.append(message)
            else:
                # for non built-in we trust.
                function_called.remove(message.get('extra').get('function_id'))
                workflow_exec.function_executions.append(message)
    
    print("len(response_messages)", len(response_messages))
    workflow_exec.result = response_messages[-1].get('content','')
    workflow_exec.all_tools_verified = not(function_called)
    return workflow_exec


def sanitize_faux_tool_transcript(
    response_text: str,
    response_messages: List[Dict],
    has_verified_tool_evidence: bool = False,
) -> str:
    """
    Remove model-fabricated [TOOL_CALL]/[TOOL_RESPONSE] blocks when no real
    tool-role messages were emitted by the runtime.
    """
    if has_verified_tool_evidence or has_runtime_tool_evidence(response_messages):
        return response_text

    if "[TOOL_CALL]" not in response_text and "[TOOL_RESPONSE]" not in response_text:
        return response_text

    sanitized = re.sub(
        r"\[TOOL_CALL\][\s\S]*?(?=(\n\[TOOL_CALL\]|\n\[TOOL_RESPONSE\]|$))",
        "",
        response_text,
    )
    sanitized = re.sub(
        r"\[TOOL_RESPONSE\][\s\S]*?(?=(\n\[TOOL_CALL\]|\n\[TOOL_RESPONSE\]|$))",
        "",
        sanitized,
    )
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()

    warning = "\n\n[Warning] Tool transcript omitted because no verified tool event was emitted."
    return (sanitized + warning).strip() if sanitized else warning.strip()



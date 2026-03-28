from __future__ import annotations

import re
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
import json

import redis

from ..mixins.json import FromJsonMixin

@dataclass
class ToolExecutions():
    session_id: str = None
    workflow_id: str = None
    function_calls: List = field(default_factory=list)
    function_executions: List = field(default_factory=list)
    all_tools_verified: bool = False

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
                f"workflow:{str(self.workflow_id)}",
                mapping={
                    "session_id": str(self.session_id),
                    "workflow_id": str(self.workflow_id),
                    "function_calls": json.dumps(self.function_calls),
                    "function_executions": json.dumps(self.function_executions),
                    "stats": json.dumps({
                        "all_tools_verified": self.all_tools_verified,
                        "num_function_execs": self.num_function_execs(),
                        "execution_success_rate": self.execution_success_rate(),
                        "execution_failure_rate": self.execution_failure_rate(),
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

#  process_tool_executions
def process_tool_executions(session_id, workflow_id, response_messages: List[Dict]) -> ToolExecutions:
    tool_execs: ToolExecutions = ToolExecutions(
        session_id = session_id,
        workflow_id = workflow_id
    )
    function_called = set()
    num_function_calls = 0
    for message in response_messages:
        if message.get('role') == "assistant" and 'function_id' in message.get('extra'):
            function_called.add(message.get('extra').get('function_id'))
            tool_execs.function_calls.append(message)
            num_function_calls +=1
        if message.get('role') == "function" and 'function_id' in message.get('extra'):
            content = json.loads(message.get('content'))
            exec_id = content.get('exec_id')
            if exec_id:
                # for built-in, we attest.
                if verify_execution_status(exec_id, content):
                    function_called.remove(message.get('extra').get('function_id'))
                    tool_execs.function_executions.append(message)
            else:
                # for non built-in we trust.
                function_called.remove(message.get('extra').get('function_id'))
                tool_execs.function_executions.append(message)
    
    tool_execs.all_tools_verified = not(function_called)
    return tool_execs


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



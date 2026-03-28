from __future__ import annotations

import re
from typing import Dict, List, Tuple
import json
import redis


def verify_execution_status(exec_id, llm_result):
    r = redis.Redis(host="redis", port=6379, decode_responses=True)
    record = r.hgetall(f"tool_execution:{exec_id}")
    runtime_result = json.loads(record["result"])
    return runtime_result == llm_result

def has_runtime_tool_evidence(response_messages: List[Dict]) -> bool:
    function_called = set()
    for message in response_messages:
        if message.get('role') == "assistant" and 'function_id' in message.get('extra'):
            function_called.add(message.get('extra').get('function_id'))
        if message.get('role') == "function" and 'function_id' in message.get('extra'):
            print("DEBUG", message)
            print("DEBUG", message.get('content'))
            content = json.loads(message.get('content'))
            exec_id = content.get('exec_id')
            if exec_id:
                # for built-in, we attest.
                if verify_execution_status(exec_id, content):
                    function_called.remove(message.get('extra').get('function_id'))
            else:
                # for non built-in we trust.
                function_called.remove(message.get('extra').get('function_id'))
            
    return not(function_called), function_called # return true if there no existing functions to be called


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



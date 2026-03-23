from __future__ import annotations

import re
from typing import Dict, List, Tuple


def has_runtime_tool_evidence(response_messages: List[Dict]) -> bool:
    function_called = set()
    for message in response_messages:
        if message.get('role') == "assistant" and 'function_id' in message.get('extra'):
            function_called.add(message.get('extra').get('function_id'))
        if message.get('role') == "function" and 'function_id' in message.get('extra'):
            function_called.remove(message.get('extra').get('function_id'))
    return not(function_called) # return true if there no existing functions to be called

def tool_messages_contain_execution_id(response_messages: List[Dict], execution_id: str) -> bool:
    """Return True when execution_id appears in streamed structured payload."""
    if not execution_id:
        return False

    for msg in response_messages:
        if execution_id in str(msg):
            return True
    return False


def verify_and_sanitize_execution_ids(
    response_text: str,
    execution_cache: Dict[str, str],
) -> Tuple[str, List[str]]:
    """Mask unverified execution IDs in the response text."""
    pattern = r"exec-[a-zA-Z0-9\-]{20,}"
    matches = re.findall(pattern, response_text)

    if not matches:
        return response_text, []

    unverified: List[str] = []
    for exec_id in set(matches):
        if execution_cache.get(exec_id) != "SUCCESS":
            unverified.append(exec_id)

    if not unverified:
        return response_text, []

    filtered_response = response_text
    for exec_id in unverified:
        filtered_response = filtered_response.replace(exec_id, f"[UNVERIFIED-{exec_id[:8]}]")

    return filtered_response, unverified


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



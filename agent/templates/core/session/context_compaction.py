# TO BE DEPRECATED

from __future__ import annotations

from typing import Dict, List, Optional


def select_context_messages(messages: List[Dict], prune_intermediate_task_contexts: bool) -> List[Dict]:
    """Build LLM input context, optionally keeping only user/assistant summaries."""
    if prune_intermediate_task_contexts:
        return [m for m in messages if m.get("role") in ("user", "assistant")]
    return messages.copy()


def inject_execution_id_context(combined_messages: List[Dict], exec_context: str) -> List[Dict]:
    """Inject execution context only into the latest user message for LLM input."""
    if not combined_messages:
        return combined_messages

    patched = combined_messages.copy()
    last_user_idx: Optional[int] = None
    for idx in range(len(patched) - 1, -1, -1):
        if patched[idx].get("role") == "user":
            last_user_idx = idx
            break

    if last_user_idx is None:
        return patched

    patched[last_user_idx] = {
        **patched[last_user_idx],
        "content": patched[last_user_idx].get("content", "") + exec_context,
    }
    return patched


def compact_assistant_chunk_text(text: str, max_chars: int) -> str:
    """Compact streaming assistant text to a bounded size for context retention."""
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    if len(text) <= max_chars:
        return text

    tail = text[-max_chars:]
    return "[Compacted]\n" + tail


def prune_session_history(
    session_messages: List[Dict],
    user_index_flag: int,
    response_messages: List[Dict],
    response_text: str,
    compact_response_text: str,
) -> List[Dict]:
    """Keep full history up to the current user turn + final assistant summary."""
    assistant_summary = None
    if response_messages:
        for msg in reversed(response_messages):
            if msg.get("role") == "assistant":
                assistant_summary = {
                    "role": "assistant",
                    "content": msg.get("content", response_text),
                }
                break

    if assistant_summary is None:
        assistant_summary = {
            "role": "assistant",
            "content": compact_response_text if compact_response_text else response_text,
        }

    return session_messages[: user_index_flag + 1] + [assistant_summary]

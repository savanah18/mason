from __future__ import annotations

from datetime import datetime

from templates.core.config.goals import Goal, GoalConfig, GoalStatus
from templates.core.mixins.json import FromJsonMixin
from templates.core.prompts.prompt_manager import PromptUpdater, parse_params
from templates.core.session.context_compaction import (
    compact_assistant_chunk_text,
    inject_execution_id_context,
    prune_session_history,
    select_context_messages,
)
from templates.core.base import extract_think_tags, parse_think_tags_from_responses


def test_extract_think_tags_returns_thought_and_cleaned_content():
    thought, content = extract_think_tags("before <think>plan</think> after")

    assert thought == "before <think>plan</think>"
    assert content == "after"


def test_extract_think_tags_handles_missing_tag():
    thought, content = extract_think_tags("plain response")

    assert thought is None
    assert content == "plain response"


def test_parse_think_tags_from_responses_only_updates_assistant_messages():
    responses = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "before <think>plan</think> after"},
    ]

    parsed = parse_think_tags_from_responses(responses)

    assert parsed[0] == {"role": "user", "content": "hello"}
    assert parsed[1]["thought"] == "before <think>plan</think>"
    assert parsed[1]["content"] == "after"


def test_select_context_messages_filters_intermediate_roles():
    messages = [
        {"role": "system", "content": "skip"},
        {"role": "user", "content": "keep"},
        {"role": "assistant", "content": "keep"},
    ]

    assert select_context_messages(messages, prune_intermediate_task_contexts=True) == [
        {"role": "user", "content": "keep"},
        {"role": "assistant", "content": "keep"},
    ]
    assert select_context_messages(messages, prune_intermediate_task_contexts=False) == messages


def test_inject_execution_id_context_appends_to_last_user_message():
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "response"},
        {"role": "user", "content": "second"},
    ]

    patched = inject_execution_id_context(messages, "\nEXEC-123")

    assert patched[-1]["content"] == "second\nEXEC-123"
    assert patched[0]["content"] == "first"


def test_compact_assistant_chunk_text_truncates_long_text():
    compacted = compact_assistant_chunk_text("  abcdefghij  ", max_chars=4)

    assert compacted == "[Compacted]\nghij"


def test_prune_session_history_uses_latest_assistant_summary():
    session_messages = [
        {"role": "user", "content": "ask"},
        {"role": "assistant", "content": "old"},
        {"role": "user", "content": "current"},
    ]
    response_messages = [
        {"role": "assistant", "content": "final answer"},
        {"role": "tool", "content": "ignored"},
    ]

    pruned = prune_session_history(
        session_messages=session_messages,
        user_index_flag=2,
        response_messages=response_messages,
        response_text="fallback",
        compact_response_text="compact",
    )

    assert pruned == [
        {"role": "user", "content": "ask"},
        {"role": "assistant", "content": "old"},
        {"role": "user", "content": "current"},
        {"role": "assistant", "content": "final answer"},
    ]


def test_prune_session_history_falls_back_to_compact_response_text():
    pruned = prune_session_history(
        session_messages=[{"role": "user", "content": "ask"}],
        user_index_flag=0,
        response_messages=[],
        response_text="fallback",
        compact_response_text="compact",
    )

    assert pruned == [
        {"role": "user", "content": "ask"},
        {"role": "assistant", "content": "compact"},
    ]


def test_parse_params_accepts_dict_and_json_string():
    assert parse_params({"a": 1}) == {"a": 1}
    assert parse_params('{"a": 1}') == {"a": 1}
    assert parse_params("") == {}
    assert parse_params("not-json") == {}


def test_goal_state_transitions_and_timeout_check(monkeypatch):
    goal = Goal(
        config=GoalConfig(
            description="desc",
            base_prompt="prompt",
            timeout_seconds=1,
            updated_at=datetime.utcnow(),
        )
    )

    goal.start()
    assert goal.status == GoalStatus.RUNNING

    goal.complete("done")
    assert goal.status == GoalStatus.COMPLETED
    assert goal.result == "done"

    goal.fail("boom")
    assert goal.status == GoalStatus.FAILED
    assert goal.error == "boom"

    goal.cancel()
    assert goal.status == GoalStatus.CANCELLED

    monkeypatch.setattr(goal, "elapsed_second", lambda: 2)
    assert goal.is_timeout() is True


def test_from_json_mixin_parses_datetimes():
    from dataclasses import dataclass

    @dataclass
    class Example(FromJsonMixin):
        created_at: datetime
        name: str

    instance = Example.from_json({"created_at": "2026-07-03T10:11:12", "name": "sample"})

    assert instance.created_at == "2026-07-03T10:11:12"
    assert instance.name == "sample"
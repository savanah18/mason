from __future__ import annotations

from datetime import datetime
from unittest.mock import mock_open, patch

from agent.templates.chat.data_models import ChatHistory, ChatMessage, ChatRequest, ChatResponse, HealthResponse, SessionSummary
from templates.core.prompts.prompt_manager import PromptUpdater


def test_chat_request_and_response_models_validate():
    request = ChatRequest(message="hello", session_id="session-1", workflow_id="workflow-1")
    response = ChatResponse(
        session_id="session-1",
        response="ok",
        timestamp="2026-07-03T12:00:00Z",
        message_count=2,
        context_length=1,
        total_history=2,
        input_length=42,
        workflow_id="workflow-1",
    )

    assert request.message == "hello"
    assert response.session_id == "session-1"
    assert response.input_length == 42


def test_chat_history_wraps_messages():
    message = ChatMessage(
        role="user",
        content="hello",
        id="msg-1",
        created_at=datetime.utcnow(),
    )
    history = ChatHistory(session_id="session-1", messages=[message])

    assert history.session_id == "session-1"
    assert history.messages[0].content == "hello"


def test_health_and_session_summary_models_validate():
    health = HealthResponse(status="ok", mcp_tools_loaded=3, sessions_active=1, backend_version="1.0.0")
    summary = SessionSummary(session_id="session-1", timestamp=1.5, first_user_message="hi")

    assert health.status == "ok"
    assert summary.first_user_message == "hi"


def test_prompt_updater_uses_goal_yaml_for_chat(monkeypatch):
        yaml_text = """
spec:
    description: chat system prompt
    remarks:
        owner: platform
    feedback: keep it simple
"""
        updater = PromptUpdater(redis_host="localhost", redis_port=6379)

        with patch("builtins.open", mock_open(read_data=yaml_text)) as mocked_open:
                prompt, remarks, feedback = updater._load_system_prompt_from_goal_yaml("chat")

        mocked_open.assert_called_once()

        assert prompt == "chat system prompt"
        assert remarks == {"owner": "platform"}
        assert feedback == "keep it simple"
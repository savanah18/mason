from pydantic import BaseModel 
from typing import Optional, List
from datetime import datetime

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    id: 'str'  # unique identifier for the message
    created_at: datetime
    persisted_at: Optional[datetime] = None
    discrete_memory_extracted: Optional[str] = 'f'  # any structured memory extracted from this message


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    workflow_id: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str
    response: str
    timestamp: str
    message_count: int
    context_length: int  # Number of messages sent to LLM
    total_history: int   # Total messages in session
    input_length: int    # Character count of prompt sent to LLM
    workflow_id: Optional[str] = None

class ChatHistory(BaseModel):
    session_id: str
    messages: List[ChatMessage]
    # created_at: str


class SessionSummary(BaseModel):
    session_id: str
    timestamp: float
    first_user_message: Optional[str] = None
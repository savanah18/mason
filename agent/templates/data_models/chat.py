from pydantic import BaseModel 
from typing import Optional, List

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

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
    created_at: str
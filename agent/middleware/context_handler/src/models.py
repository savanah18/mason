from pydantic import BaseModel

class ChatRequest(BaseModel):
    session_id: str
    user_message: str
    max_tokens: int = 1024  # Lowered from 2048 to prevent repetition loops
    temperature: float = 0.7
    top_p: float = 0.9
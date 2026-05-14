from typing import Optional

from agent_memory_client import MemoryAPIClient
from agent_memory_client.models import WorkingMemory

from .session_store import MemorySessionStore


class MemoryManagementMixin:
    def _initialize_memory_manager(self) -> MemoryAPIClient :
        """Initialize Memory Manager."""
        return self._initialize_memory_store().memory_client

    def _initialize_memory_store(self) -> MemorySessionStore:
        """Create or reuse the session store backing memory operations."""
        store = getattr(self, "memory_store", None)
        if store is None:
            store = MemorySessionStore()
            self.memory_store = store
            self.memory_client = store.memory_client
            self.sessions = store.sessions
        return store

    async def create_session(self, user_id = None) -> str:
        """Create a new chat session."""
        store = self._initialize_memory_store()
        return await store.create_session(user_id=user_id, owner=self.__class__.__name__)

    async def get_session(self, session_id: str) -> tuple[bool, WorkingMemory]:
        """Get session by ID."""
        store = self._initialize_memory_store()
        return await store.get_session(session_id)
    
    def clear_session(self, session_id: str) -> bool:
        """Clear a chat session and cleanup execution cache for this session."""
        store = self._initialize_memory_store()
        return store.clear_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and cleanup execution cache."""
        store = self._initialize_memory_store()
        return store.delete_session(session_id)
    
# some utilities
def compact_assistant_chunk_text(text: str, max_chars: int) -> str:
    """Compact streaming assistant text to a bounded size for context retention."""
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    if len(text) <= max_chars:
        return text

    tail = text[-max_chars:]
    return "[Compacted]\n" + tail
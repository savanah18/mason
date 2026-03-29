import os
import uuid

# Memory Managment
from transformers import AutoTokenizer
from agent_memory_client import MemoryAPIClient, MemoryClientConfig
from agent_memory_client.models import WorkingMemory


class MemoryManagementMixin:
    def _initialize_memory_manager(self) -> MemoryAPIClient :
        """Initialize Memory Manager"""
        memory_client_config = MemoryClientConfig(
            base_url = os.getenv("AGENT_MEMORY_SERVER_URL", "http://agent-memory-server-api:8000"),
            default_namespace = "chat"
        )
        return MemoryAPIClient(memory_client_config)

    async def create_session(self, user_id = None) -> str:
        """Create a new chat session."""
        session_id = str(uuid.uuid4())
        print("Sessions: ", self.sessions)
        await self.memory_client.get_or_create_working_memory(
            session_id = session_id,
            user_id = user_id or self.__class__.__name__
        )
        self.sessions[session_id] =  {}
        
        print(f"📝 Created session: {session_id}")
        return session_id

    async def get_session(self, session_id: str) -> tuple[bool, WorkingMemory]:
        """Get session by ID."""
        created, session = await self.memory_client.get_or_create_working_memory(
            session_id = session_id
        )
        return created, session
    
    def clear_session(self, session_id: str) -> bool:
        """Clear a chat session and cleanup execution cache for this session."""
        if session_id in self.sessions:
            # TODO promote to long-term before 
            # self.sessions[session_id]["messages"] = []
            # self.sessions[session_id]["last_updated"] = datetime.utcnow().isoformat()
            print(f"🗑 Cleared session: {session_id}")
            return True
        return False

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and cleanup execution cache."""
        if session_id in self.sessions:
            # TODO promote to long-term before
            # del self.sessions[session_id]
            # print(f"🗑 Deleted session: {session_id}")
            return True
        return False
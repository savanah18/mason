"""Session storage wrapper for agent working-memory interactions."""

from __future__ import annotations

import os
import uuid
from typing import Dict, Optional, Tuple

from agent_memory_client import MemoryAPIClient, MemoryClientConfig
from agent_memory_client.models import WorkingMemory


class MemorySessionStore:
    """Thin wrapper around the external memory client plus local session bookkeeping."""

    def __init__(self, memory_client: Optional[MemoryAPIClient] = None):
        self.memory_client = memory_client or self._initialize_memory_manager()
        self.sessions: Dict[str, Dict] = {}

    def _initialize_memory_manager(self) -> MemoryAPIClient:
        memory_client_config = MemoryClientConfig(
            base_url=os.getenv("AGENT_MEMORY_SERVER_URL", "http://agent-memory-server-api:8000"),
            default_namespace="chat",
        )
        print(f"Initializing agent memory client with config \n {memory_client_config}")
        return MemoryAPIClient(memory_client_config)

    async def create_session(self, user_id: Optional[str] = None, owner: Optional[str] = None) -> str:
        session_id = str(uuid.uuid4())
        await self.memory_client.get_or_create_working_memory(
            session_id=session_id,
            user_id=user_id or owner or self.__class__.__name__,
        )
        self.sessions[session_id] = {}
        print(f"📝 Created session: {session_id}")
        return session_id

    async def get_session(self, session_id: str) -> Tuple[bool, WorkingMemory]:
        return await self.memory_client.get_or_create_working_memory(session_id=session_id)

    def clear_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            self.sessions[session_id] = {}
            print(f"🗑 Cleared session cache: {session_id}")
            return True
        return False

    def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            print(f"🗑 Deleted session cache: {session_id}")
            return True
        return False
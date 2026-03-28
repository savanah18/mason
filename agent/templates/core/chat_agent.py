import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI

# Model
from qwen_agent.agents import Assistant
from qwen_agent.tools.mcp_manager import MCPManager
from qwen_agent.utils.output_beautify import typewriter_print
from templates.core.context_compaction import (
    compact_assistant_chunk_text,
    inject_execution_id_context,
    prune_session_history,
    select_context_messages,
)


# Memory Managment
from transformers import AutoTokenizer
from agent_memory_client import MemoryAPIClient, MemoryClientConfig
from agent_memory_client.models import WorkingMemory

from templates.core.mcp_compat import apply_mcp_ping_compat_patch
from templates.core.tool_verification import (
    process_tool_executions,
    sanitize_faux_tool_transcript
)

class ChatAgentBackend:
    """Manages agent sessions and chat state."""

    def __init__(self, *args, **kwargs):
        self.sessions: Dict[str, Dict] = {}
        self.agent = None
        self.mcp_tools_count = 0
        self.prune_intermediate_task_contexts = kwargs.get("prune_intermediate_task_contexts", False)
        self.compact_chunk_max_chars = int(os.getenv("COMPACT_CHUNK_MAX_CHARS", "1800"))

        if self.prune_intermediate_task_contexts:
            print("[W] Prune Intermediate task contexts enabled...")
        self._initialize_agent(
            kwargs["llm_cfg_path"],
            kwargs["prompt_cfg_path"],
            kwargs["actuators"]
        )
        self.tokenizer = AutoTokenizer.from_pretrained("/mnt/checkpoint")

    @staticmethod
    def _apply_mcp_ping_compat_patch():
        """Allow MCP servers that do not implement ping (legacy stdio servers)."""
        apply_mcp_ping_compat_patch()
    
    def _initialize_agent(self, llm_cfg_path, prompt_cfg_path, actuators):
        """Initialize Qwen agent with MCP tools."""
        print("🔧 Initializing Qwen Agent...")
        
        # LLM Configuration
        llm_cfg =  self._initialize_llm_cfg(llm_cfg_path)
        # Prompts
        prompts = self._initialized_prompts(prompt_cfg_path)
        # Tools
        mcp_config = self._initialize_mcp_cfg(actuators)
        tools = self._load_mcp_tools(mcp_config)
        self.mcp_tools_count = len(tools)
        # Memory 
        self.memory_client = self._initialize_memory_manager()
        
        # Create agent
        # TODO Integrate to memory server
        system_prompt = prompts.get("system")
        self.agent = Assistant(
            llm=llm_cfg,
            system_message=system_prompt,
            function_list=tools + mcp_config["builtin-functions"],
            files=[]
        )

        print(f"Initializing agent with system prompt {system_prompt}")

    def _initialize_llm_cfg(self, config_path="./config/llm.yaml"):
        try:
            with open(config_path, "r") as f: 
                llm_cfg = yaml.safe_load(f)
        except Exception as e:
            llm_cfg = {
                'model': 'Qwen3-4B-Instruct',
                'model_server': os.getenv('LLM_SERVER', 'http://localhost:8001/v1'),
                'generate_cfg': {
                    "temperature": 0.8,
                    "top_p": 0.9,
                    "repetition_penalty": 1.1        
                }
            }
        print(f"✓ Qwen Agent initialized with the following llm config.\n {llm_cfg}")
        return llm_cfg
    
    def _initialized_prompts(self, config_path="./config/prompts"):
        try:
            with open(config_path, "r") as f: 
                prompts = yaml.safe_load(f)
        except Exception as e:
            prompts = {"system": ""}
        print(f"✓ Qwen Agent initialized with the following prompts.\n {prompts}")
        return prompts

    def _initialize_mcp_cfg(self, config_path="./config/actuators.yaml"):
        mcp_cfg = {}
        try:
            with open(config_path, "r") as f: 
                mcp_cfg = yaml.safe_load(f)["spec"]
        except Exception as e:
            pass
        print(f"✓ Qwen Agent initialized with the following mcp config.\n {mcp_cfg}")
        return mcp_cfg

    def _load_mcp_tools(self, mcp_config, timeout=None) -> List:
        """Load MCP tools with timeout."""
        timeout = timeout or int(os.getenv("MCP_INIT_TIMEOUT_SECONDS", "180"))
        result = {"tools": [], "error": None}
        mcp_config  = {
            "mcpServers" : mcp_config["mcp-servers"]
        }
        print("DEBUG", mcp_config)

        def _init():
            try:
                self._apply_mcp_ping_compat_patch()
                result["tools"] = MCPManager().initConfig(mcp_config)
                print(f"✓ Loaded {len(result['tools'])} MCP tools")
            except Exception as e:
                result["error"] = e
                print(f"⚠ Warning: Failed to initialize MCP servers: {e}")
        
        thread = threading.Thread(target=_init, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            print(f"⏱ MCP initialization timeout after {timeout}s")
            return []
        
        if result["error"]:
            return []
        
        print(f"✓ Qwen Agent initialized with {len(result['tools'])}")
        return result["tools"]

    def _initialize_memory_manager(self) -> MemoryAPIClient :
        """Initialize Memory Manager"""
        memory_client_config = MemoryClientConfig(
            base_url = os.getenv("AGENT_MEMORY_SERVER_URL", "http://agent-memory-server-api:8000"),
            default_namespace = "chat"
        )
        return MemoryAPIClient(memory_client_config)

    async def create_session(self) -> str:
        """Create a new chat session."""
        session_id = str(uuid.uuid4())
        # TO BE DEPRECATED
        # self.sessions[session_id] = {
        #     "messages": [],
        #     "created_at": datetime.utcnow().isoformat(),
        #     "last_updated": datetime.utcnow().isoformat(),
        # }
        print("Sessions: ", self.sessions)
        await self.memory_client.get_or_create_working_memory(
            session_id = session_id,
            user_id = self.__class__.__name__
        )
        self.sessions[session_id] =  {}
        
        print(f"📝 Created session: {session_id}")
        return session_id
    
    async def get_session(self, session_id: str) -> tuple[bool, WorkingMemory]:
        """Get session by ID."""
        created, session = await self.memory_client.get_or_create_working_memory(
            session_id = session_id,
            user_id = self.__class__.__name__,
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

    def compute_context_length(self, messages: List = []):
        # print(f"Computing context length for  {messages}")
        text = "".join([m.dict()["role"] + ": " + m.dict()["content"] for m in messages])
        tokens = self.tokenizer.encode(text)
        return len(tokens)
    
    async def send_message(self, session_id: str, user_message: str) -> tuple[str, int, int]:
        """Send a message and get response with execution verification. Returns (response_text, context_length, input_length)."""
        if not self.agent:
            raise ValueError("Agent not initialized")
        
        _, session  = await self.get_session(session_id)
        session : WorkingMemory
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        
        # Add user message to history
        session.messages.append({"role": "user", "content": user_message})
        messages = [m.dict() if type(m)!=dict else m for m in session.messages]
        user_index_flag = len(messages) - 1
        print(f"📝 After adding user message: {len(messages)} messages in history")
                

        tmp = ""
        assistant_response  = ""
        structure_responses: List[Dict] = []
        try:
            for response in self.agent.run(messages=messages):
                tmp = typewriter_print(response, tmp) # for visual purposes 

            structure_responses = response 
            print(structure_responses)
            assistant_response = response[-1]['content']
        except Exception as e:
            assistant_response = f"Error: {str(e)}"

        # Determine if tools called have response, record tool execcution details for evaluations
        tool_execs  = process_tool_executions(
            session_id = session_id,
            workflow_id = str(uuid.uuid4()),
            response_messages = structure_responses
        )

        if tool_execs.all_tools_verified:
            print("All tool calls verified!")
            print(tool_execs)
            tool_execs.record_workflow_state()
        else:
            assistant_response = f"Unverified Tool Calls Found!"

        # Add assistant responses to history
        if structure_responses:
            session.messages.extend(structure_responses[-1:]) #final answer only


        print(f"✅ After agent response: {len(session.messages)} total messages in session")
        updated_session =  await self.memory_client.put_working_memory(
            session_id = session_id,
            memory = session,
        )
        return assistant_response, self.compute_context_length(updated_session.messages), 0
    
    def get_health_status(self) -> Dict:
        """Get backend health status."""
        # cache_stats = {
        #     "total": len(self.execution_cache),
        #     "in_progress": sum(1 for v in self.execution_cache.values() if v == "IN_PROGRESS"),
        #     "success": sum(1 for v in self.execution_cache.values() if v == "SUCCESS"),
        #     "failed": sum(1 for v in self.execution_cache.values() if v == "FAILED"),
        # }
        return {
            "status": "healthy",
            "mcp_tools_loaded": self.mcp_tools_count,
            "sessions_active": len(self.sessions),
            # "execution_cache": cache_stats,
            "backend_version": "1.0.0",
        }
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
from templates.core.workflows import (
    process_workflow_execution,
    sanitize_faux_tool_transcript
)

from .base import BaseAgent
from ..memory.management.agent_memory_mixin import MemoryManagementMixin

class ChatAgentBackend(BaseAgent, MemoryManagementMixin):
    """Manages agent sessions and chat state."""

    def __init__(self, *args, **kwargs):
        self.sessions: Dict[str, Dict] = {}
        self.agent = None
        self.tools_count = 0
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
    
    def _initialize_agent(self, llm_cfg_path, prompt_cfg_path, actuators):
        """Initialize Qwen chat agent with MCP tools."""
        print("🔧 Initializing Qwen Chat Agent...")
        
        # LLM Configuration
        llm_cfg =  self._initialize_llm_cfg(llm_cfg_path)
        # Prompts
        # TODO Integrate system prompt to memory server
        prompts = self._initialized_prompts(prompt_cfg_path)
        system_prompt = prompts.get("system")

        # Tools
        mcp_config = self._initialize_mcp_cfg(actuators)
        exclude_tools = mcp_config.get('exclude-tools', [])
        mcp_tools = self._load_mcp_tools(mcp_config)
        function_tools = mcp_config['builtin-functions']
        self.tools_count = len(mcp_tools + function_tools)

        # Memory 
        self.memory_client = self._initialize_memory_manager()
        
        # Create agent
        self.agent = Assistant(
            llm=llm_cfg,
            system_message=system_prompt,
            function_list=mcp_tools + function_tools,
            files=[]
        )

        print(f"Initializing agent with system prompt {system_prompt}")
    
    def _initialized_prompts(self, config_path="./config/prompts"):
        try:
            with open(config_path, "r") as f: 
                prompts = yaml.safe_load(f)
        except Exception as e:
            prompts = {"system": ""}
        print(f"✓ Qwen Agent initialized with the following prompts.\n {prompts}")
        return prompts
    

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
        
        print("User message: ", user_message)
        # Add user message to history
        session.messages.append({"role": "user", "content": user_message})
        messages = [m.dict() if type(m)!=dict else m for m in session.messages]
        user_index_flag = len(messages) - 1
        print(f"📝 After adding user message: {len(messages)} messages in history")
                

        tmp = ""
        assistant_response  = ""
        structured_responses: List[Dict] = []
        try:
            for response in self.agent.run(messages=messages):
                tmp = typewriter_print(response, tmp) # for visual purposes 

            structured_responses = response 
            print(structured_responses)
            assistant_response = response[-1]['content']
        except Exception as e:
            assistant_response = f"Error: {str(e)}"

        # Determine if tools called have response, record tool execcution details for evaluations
        workflow_exec  = process_workflow_execution(
            session_id = session_id,
            workflow_id = str(uuid.uuid4()),
            task = user_message, 
            response_messages = structured_responses
        )

        workflow_exec.record_workflow_state()
        if workflow_exec.all_tools_verified:
            print("All tool calls verified!")
            print(workflow_exec)
        else:
            assistant_response = f"Unverified Tool Calls Found!"

        # Add assistant responses to history
        if structured_responses:
            session.messages.extend(structured_responses[-1:]) #final answer only


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
            "mcp_tools_loaded": self.tools_count,
            "sessions_active": len(self.sessions),
            # "execution_cache": cache_stats,
            "backend_version": "1.0.0",
        }
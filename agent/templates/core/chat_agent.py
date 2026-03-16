import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI

from qwen_agent.agents import Assistant
from qwen_agent.tools import mcp_manager as qwen_mcp_manager
from qwen_agent.tools.mcp_manager import MCPManager
from qwen_agent.utils.output_beautify import typewriter_print

class ChatAgentBackend:
    """Manages agent sessions and chat state."""

    def __init__(self, *args, **kwargs):
        self.sessions: Dict[str, Dict] = {}
        self.agent = None
        self.mcp_tools_count = 0
        # Execution cache: execution_id -> "IN_PROGRESS" | "SUCCESS" | "FAILED"
        self.execution_cache: Dict[str, str] = {}
        self._initialize_agent(
            kwargs["llm_cfg_path"],
            kwargs["prompt_cfg_path"],
            kwargs["actuators"]
        )

    def _has_tool_calls_in_response(self, response_messages: List[Dict]) -> bool:
        """Check if response contains actual tool calls."""
        for msg in response_messages:
            if msg.get("role") == "tool":
                return True
        return False

    def _verify_and_sanitize_execution_ids(self, response_text: str, current_execution_id: str) -> str:
        """
        Verify that execution_ids referenced in response are in cache with SUCCESS status.
        Remove or warn about unverified execution_ids.
        """
        import re
        # Find all execution_ids in response
        pattern = r'exec-[a-zA-Z0-9\-]{20,}'
        matches = re.findall(pattern, response_text)
        
        if not matches:
            return response_text
        
        unverified = []
        for exec_id in set(matches):
            # Check if execution_id exists in cache and has SUCCESS status
            status = self.execution_cache.get(exec_id)
            if status != "SUCCESS":
                unverified.append(exec_id)
        
        if unverified:
            # Filter out references to unverified execution_ids
            filtered_response = response_text
            for exec_id in unverified:
                filtered_response = filtered_response.replace(exec_id, f"[UNVERIFIED-{exec_id[:8]}]")
            print(f"⚠️  Unverified execution IDs: {unverified}")
            return filtered_response
        
        return response_text

    @staticmethod
    def _apply_mcp_ping_compat_patch():
        """Allow MCP servers that do not implement ping (legacy stdio servers)."""
        if getattr(qwen_mcp_manager.MCPClient, "_ping_compat_patched", False):
            return

        async def _execute_function_without_ping(self, tool_name, tool_args: dict):
            from mcp.types import TextResourceContents

            if tool_name == 'list_resources':
                try:
                    list_resources = await self.session.list_resources()
                    if list_resources.resources:
                        return '\n\n'.join(str(resource) for resource in list_resources.resources)
                    return 'No resources found'
                except Exception as e:
                    return f'Error: {e}'

            if tool_name == 'read_resource':
                try:
                    uri = tool_args.get('uri')
                    if not uri:
                        raise ValueError('URI is required for read_resource')
                    read_resource = await self.session.read_resource(uri)
                    texts = []
                    for resource in read_resource.contents:
                        if isinstance(resource, TextResourceContents):
                            texts.append(resource.text)
                    if texts:
                        return '\n\n'.join(texts)
                    return 'Failed to read resource'
                except Exception as e:
                    return f'Error: {e}'

            response = await self.session.call_tool(tool_name, tool_args)
            texts = []
            for content in response.content:
                if content.type == 'text':
                    texts.append(content.text)
            if texts:
                return '\n\n'.join(texts)
            return 'execute error'

        qwen_mcp_manager.MCPClient.execute_function = _execute_function_without_ping
        qwen_mcp_manager.MCPClient._ping_compat_patched = True
        print("✓ Applied MCP ping compatibility patch")
    
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
        
        # Create agent
        self.agent = Assistant(
            llm=llm_cfg,
            system_message=prompts.get("system"),
            function_list=tools + mcp_config["builtin-functions"],
            files=[]
        )

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

    def _load_mcp_tools(self, mcp_config, timeout=60) -> List:
        """Load MCP tools with timeout."""
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
    
    def create_session(self) -> str:
        """Create a new chat session."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "messages": [],
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
        }
        print(f"📝 Created session: {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID."""
        return self.sessions.get(session_id)
    
    def clear_session(self, session_id: str) -> bool:
        """Clear a chat session and cleanup execution cache for this session."""
        if session_id in self.sessions:
            self.sessions[session_id]["messages"] = []
            self.sessions[session_id]["last_updated"] = datetime.utcnow().isoformat()
            # Clean up execution cache entries for this session (they're scoped by session_id in the key)
            self.execution_cache = {
                k: v for k, v in self.execution_cache.items()
                if not k.startswith(session_id[:8])
            }
            print(f"🗑 Cleared session: {session_id}")
            return True
        return False

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and cleanup execution cache."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.execution_cache = {
                k: v for k, v in self.execution_cache.items()
                if not k.startswith(session_id[:8])
            }
            print(f"🗑 Deleted session: {session_id}")
            return True
        return False
    
    def send_message(self, session_id: str, user_message: str) -> tuple[str, int, int]:
        """Send a message and get response with execution verification. Returns (response_text, context_length, input_length)."""
        if not self.agent:
            raise ValueError("Agent not initialized")
        
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Generate execution ID for this turn and mark as IN_PROGRESS
        execution_id = f"exec-{session_id[:8]}-{uuid.uuid4().hex[:8]}"
        self.execution_cache[execution_id] = "IN_PROGRESS"
        print(f"🔐 Generated execution_id: {execution_id}")
        
        exec_context = f"\nNote: Include this execution_id in tool calls: {execution_id}"
        
        # Add user message to history
        messages = session["messages"]
        messages.append({"role": "user", "content": user_message})
        print(f"📝 After adding user message: {len(messages)} messages in history")
        
        # Use only user turns as model input to avoid replay bias from prior assistant tool summaries.
        combined_messages = [m for m in messages if m.get("role") == "user"]
        context_length = len(combined_messages)
        
        # Inject execution_id context into last message (for LLM only, not stored)
        if combined_messages:
            combined_messages = combined_messages.copy()
            combined_messages[-1] = {
                **combined_messages[-1],
                "content": combined_messages[-1].get("content", "") + exec_context
            }
        
        # Calculate actual input size (character count)
        input_length = sum(len(str(msg.get('content', ''))) for msg in combined_messages)
        print(f"📊 Context: {context_length} messages, {input_length} chars sent to LLM")
        
        response_text = ""
        response_messages: List[Dict] = []
        try:
            for response in self.agent.run(messages=combined_messages):
                response_text = typewriter_print(response, response_text)
                if isinstance(response, dict):
                    response_messages.append(response)
        except Exception as e:
            response_text = f"Error: {str(e)}"
            response_messages = [{"role": "assistant", "content": response_text}]
            self.execution_cache[execution_id] = "FAILED"

        # Check if tool response contains the execution_id (confirms successful execution)
        tool_response_content = str(response_text) + str(response_messages)
        if execution_id in tool_response_content:
            self.execution_cache[execution_id] = "SUCCESS"
            print(f"✅ Execution {execution_id} marked SUCCESS (execution_id found in response)")
        else:
            self.execution_cache[execution_id] = "FAILED"
            print(f"❌ Execution {execution_id} marked FAILED (execution_id not echoed back)")

        # Verify execution_ids before adding to history (sanitization point)
        verified_response = self._verify_and_sanitize_execution_ids(response_text, execution_id)
        if verified_response != response_text:
            print(f"⚠️  Filtered unverified execution IDs from response")
            response_text = verified_response

        # Add assistant/tool responses to history
        if response_messages:
            session["messages"].extend(response_messages)
        else:
            session["messages"].append(
                {
                    "role": "assistant",
                    "content": response_text,
                }
            )
        print(f"✅ After agent response: {len(session['messages'])} total messages in session")
        
        session["last_updated"] = datetime.utcnow().isoformat()
        
        return response_text, context_length, input_length

    def _has_tool_calls_in_response(self, response_messages: List[Dict]) -> bool:
        """Check if response contains actual tool calls."""
        for msg in response_messages:
            if msg.get("role") == "tool":
                return True
        return False

    def _verify_and_sanitize_execution_ids(self, response_text: str, current_execution_id: str) -> str:
        """
        Verify that execution_ids referenced in response are in cache with SUCCESS status.
        Remove or warn about unverified execution_ids.
        """
        import re
        # Find all execution_ids in response
        pattern = r'exec-[a-zA-Z0-9\-]{20,}'
        matches = re.findall(pattern, response_text)
        
        if not matches:
            return response_text
        
        unverified = []
        for exec_id in set(matches):
            # Check if execution_id exists in cache and has SUCCESS status
            status = self.execution_cache.get(exec_id)
            if status != "SUCCESS":
                unverified.append(exec_id)
        
        if unverified:
            # Filter out references to unverified execution_ids
            filtered_response = response_text
            for exec_id in unverified:
                filtered_response = filtered_response.replace(exec_id, f"[UNVERIFIED-{exec_id[:8]}]")
            print(f"⚠️  Unverified execution IDs: {unverified}")
            return filtered_response
        
        return response_text
        
        return response_text, context_length, input_length
    
    def get_health_status(self) -> Dict:
        """Get backend health status."""
        cache_stats = {
            "total": len(self.execution_cache),
            "in_progress": sum(1 for v in self.execution_cache.values() if v == "IN_PROGRESS"),
            "success": sum(1 for v in self.execution_cache.values() if v == "SUCCESS"),
            "failed": sum(1 for v in self.execution_cache.values() if v == "FAILED"),
        }
        return {
            "status": "healthy",
            "mcp_tools_loaded": self.mcp_tools_count,
            "sessions_active": len(self.sessions),
            "execution_cache": cache_stats,
            "backend_version": "1.0.0",
        }
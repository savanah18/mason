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
    
    def __init__(self, *args, **kwargs):
        self.sessions: Dict[str, Dict] = {}
        self.agent = None
        self.mcp_tools_count = 0
        self._initialize_agent(
            kwargs["llm_cfg_path"],
            kwargs["prompt_cfg_path"],
            kwargs["actuators"]
        )
    
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
        """Clear a chat session."""
        if session_id in self.sessions:
            self.sessions[session_id]["messages"] = []
            self.sessions[session_id]["last_updated"] = datetime.utcnow().isoformat()
            print(f"🗑 Cleared session: {session_id}")
            return True
        return False
    
    def send_message(self, session_id: str, user_message: str) -> tuple[str, int, int]:
        """Send a message and get response. Returns (response_text, context_length, input_length)."""
        if not self.agent:
            raise ValueError("Agent not initialized")
        
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Add user message to history
        messages = session["messages"]
        messages.append({"role": "user", "content": user_message})
        print(f"📝 After adding user message: {len(messages)} messages in history")
        
        # Get agent response
        combined_messages = messages.copy()
        context_length = len(combined_messages)
        
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

        # Add assistant/tool responses to history
        if response_messages:
            session["messages"].extend(response_messages)
        else:
            session["messages"].append({"role": "assistant", "content": response_text})
        print(f"✅ After agent response: {len(session['messages'])} total messages in session")
        
        session["last_updated"] = datetime.utcnow().isoformat()
        
        return response_text, context_length, input_length
    
    def get_health_status(self) -> Dict:
        """Get backend health status."""
        return {
            "status": "healthy",
            "mcp_tools_loaded": self.mcp_tools_count,
            "sessions_active": len(self.sessions),
            "backend_version": "1.0.0",
        }
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI

from qwen_agent.agents import Assistant
from qwen_agent.tools.mcp_manager import MCPManager
from qwen_agent.utils.output_beautify import typewriter_print
from templates.core.context_compaction import (
    compact_assistant_chunk_text,
    inject_execution_id_context,
    prune_session_history,
    select_context_messages,
)
from transformers import AutoTokenizer

from templates.core.mcp_compat import apply_mcp_ping_compat_patch
from templates.core.response_guardrails import (
    has_runtime_tool_evidence,
    sanitize_faux_tool_transcript,
    tool_messages_contain_execution_id,
    verify_and_sanitize_execution_ids,
)

class ChatAgentBackend:
    """Manages agent sessions and chat state."""

    def __init__(self, *args, **kwargs):
        self.sessions: Dict[str, Dict] = {}
        self.agent = None
        self.mcp_tools_count = 0
        self.prune_intermediate_task_contexts = kwargs.get("prune_intermediate_task_contexts", False)
        self.compact_chunk_max_chars = int(os.getenv("COMPACT_CHUNK_MAX_CHARS", "1800"))
        # Execution cache: execution_id -> "IN_PROGRESS" | "SUCCESS" | "FAILED"
        self.execution_cache: Dict[str, str] = {}
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

    def compute_context_length(self, messages: List = []):
        text = "".join([m["role"] + ": " + m["content"] for m in messages])
        tokens = self.tokenizer.encode(text)
        return len(tokens)
    
    def send_message(self, session_id: str, user_message: str) -> tuple[str, int, int]:
        """Send a message and get response with execution verification. Returns (response_text, context_length, input_length)."""
        if not self.agent:
            raise ValueError("Agent not initialized")
        
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Generate execution ID for this turn and mark as IN_PROGRESS
        # execution_id = f"exec-{session_id[:8]}-{uuid.uuid4().hex[:8]}"
        # self.execution_cache[execution_id] = "IN_PROGRESS"
        # print(f"🔐 Generated execution_id: {execution_id}")
        
        # exec_context = f"\nNote: Include this execution_id in tool calls: {execution_id}"
        
        # Add user message to history
        messages = session["messages"]
        messages.append({"role": "user", "content": user_message})
        user_index_flag = len(messages) - 1
        print(f"📝 After adding user message: {len(messages)} messages in history")
        
        # Keep concise conversational memory for planning continuity.
        # When pruning is enabled we retain only user + assistant summaries,
        # while omitting raw tool messages to reduce token churn.
        # combined_messages = select_context_messages(
        #     messages,
        #     self.prune_intermediate_task_contexts,
        # )
        # context_length = len(combined_messages)
        
        # # Inject execution_id context into the latest user message only (for LLM only, not stored)
        # combined_messages = inject_execution_id_context(combined_messages, exec_context)
        
        # # Calculate actual input size (character count)
        # input_length = sum(len(str(msg.get('content', ''))) for msg in combined_messages)
        # print(f"📊 Context: {context_length} messages, {input_length} chars sent to LLM")
        

        tmp = ""
        assistant_answer  = ""
        structured_messages: List[Dict] = []
        try:
            for response in self.agent.run(messages=session["messages"]):
                tmp = typewriter_print(response, tmp) # for visual purposes 

            assistant_answer = response[-1]['content']
            structured_messages = response    
            # print(f"final text message after every inference call {structured_messages}")
            # print(f"final structured message after every inference call {structured_messages}")
        except Exception as e:
            assistant_answer = f"Error: {str(e)}"

        # Determine if tools called have response.
        runtime_tool_evidence,unverified_function_calls  = has_runtime_tool_evidence(structured_messages)
        if runtime_tool_evidence:
            print("All tool calls verified!")
        else:
            assistant_answer = f"Unverified Tool Calls Found!"

        # Sanitize model-fabricated tool transcript tags only when no verified evidence exists.
        # response_text = sanitize_faux_tool_transcript(
        #     response_text,
        #     structured_messages,
        #     runtime_tool_evidence=runtime_tool_evidence,
        # )

        # Mark SUCCESS only when runtime evidence exists and execution_id appears
        # in structured tool/runtime messages.
        # execution_id_present = tool_messages_contain_execution_id(structured_messages, execution_id)
        # if runtime_tool_evidence and execution_id_present:
        #     self.execution_cache[execution_id] = "SUCCESS"
        #     print(f"✅ Execution {execution_id} marked SUCCESS (verified tool event)")
        # else:
        #     self.execution_cache[execution_id] = "FAILED"
        #     print(f"❌ Execution {execution_id} marked FAILED (no verified tool event)")

        # Verify execution_ids before adding to history (sanitization point)
        # TODO REDIS Cache
        # verified_response, unverified_ids = verify_and_sanitize_execution_ids(
        #     response_text,
        #     self.execution_cache,
        # )
        # if unverified_ids:
        #     print(f"⚠️  Unverified execution IDs: {unverified_ids}")
        # if verified_response != response_text:
        #     print(f"⚠️  Filtered unverified execution IDs from response")
        #     response_text = verified_response

        # Add assistant/tool responses to history
        if structured_messages:
            session["messages"].extend(structured_messages[-1:])

        # Memory pruning: keep full history up to current user turn + final assistant summary.
        # if self.prune_intermediate_task_contexts:
        #     print("Pruning intermediate memory. Keeping only user turn and final response...")
        #     session["messages"] = prune_session_history(
        #         session_messages=session["messages"],
        #         user_index_flag=user_index_flag,
        #         structured_messages=structured_messages,
        #         response_text=response_text,
        #         compact_response_text=compact_response_text,
        #     )

        print(f"✅ After agent response: {len(session['messages'])} total messages in session")
        
        session["last_updated"] = datetime.utcnow().isoformat()
        
        return assistant_answer, self.compute_context_length(session["messages"]), 0
    
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
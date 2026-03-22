import os
import re
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

    def _has_tool_calls_in_response(self, response_messages: List[Dict]) -> bool:
        """Check if response contains actual tool calls."""
        for msg in response_messages:
            if msg.get("role") == "tool":
                return True
        return False

    def _has_runtime_tool_evidence(self, response_messages: List[Dict]) -> bool:
        """Detect tool activity across common streamed message formats."""
        for msg in response_messages:
            if not isinstance(msg, dict):
                continue

            role = msg.get("role")
            if role in ("tool", "function"):
                return True

            if "tool_calls" in msg or "function_call" in msg:
                return True

            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") in (
                        "tool_call",
                        "tool_result",
                        "function_call",
                        "function_result",
                    ):
                        return True
        return False

    def _response_text_indicates_tool_flow(self, response_text: str) -> bool:
        """Detect tool-flow markers in streamed text output."""
        if not response_text:
            return False
        return "[TOOL_CALL]" in response_text and "[TOOL_RESPONSE]" in response_text

    def _verify_and_sanitize_execution_ids(self, response_text: str, current_execution_id: str) -> str:
        """
        Verify that execution_ids referenced in response are in cache with SUCCESS status.
        Remove or warn about unverified execution_ids.
        """
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

    def _tool_messages_contain_execution_id(self, response_messages: List[Dict], execution_id: str) -> bool:
        """Return True when execution_id appears in streamed structured payload."""
        if not execution_id:
            return False

        for msg in response_messages:
            if execution_id in str(msg):
                return True
        return False

    def _sanitize_faux_tool_transcript(
        self,
        response_text: str,
        response_messages: List[Dict],
        has_verified_tool_evidence: bool = False,
    ) -> str:
        """
        Remove model-fabricated [TOOL_CALL]/[TOOL_RESPONSE] blocks when no real
        tool-role messages were emitted by the agent runtime.
        """
        if has_verified_tool_evidence or self._has_runtime_tool_evidence(response_messages):
            return response_text

        if "[TOOL_CALL]" not in response_text and "[TOOL_RESPONSE]" not in response_text:
            return response_text

        sanitized = re.sub(
            r"\[TOOL_CALL\][\s\S]*?(?=(\n\[TOOL_CALL\]|\n\[TOOL_RESPONSE\]|$))",
            "",
            response_text,
        )
        sanitized = re.sub(
            r"\[TOOL_RESPONSE\][\s\S]*?(?=(\n\[TOOL_CALL\]|\n\[TOOL_RESPONSE\]|$))",
            "",
            sanitized,
        )
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()

        warning = "\n\n[Warning] Tool transcript omitted because no verified tool event was emitted."
        return (sanitized + warning).strip() if sanitized else warning.strip()

    def _compact_assistant_chunk_text(self, text: str) -> str:
        """Compact streaming assistant text to a bounded size for context retention."""
        if not isinstance(text, str):
            text = str(text)
        text = text.strip()
        if len(text) <= self.compact_chunk_max_chars:
            return text

        # Keep suffix because latest reasoning/tool outcomes are most useful for next turn.
        tail = text[-self.compact_chunk_max_chars :]
        return "[Compacted]\n" + tail

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
        user_index_flag = len(messages) - 1
        print(f"📝 After adding user message: {len(messages)} messages in history")
        
        # Keep concise conversational memory for planning continuity.
        # When pruning is enabled we retain only user + assistant summaries,
        # while omitting raw tool messages to reduce token churn.
        if self.prune_intermediate_task_contexts:
            combined_messages = [
                m for m in messages
                if m.get("role") in ("user", "assistant")
            ]
        else:
            combined_messages = messages.copy()
        context_length = len(combined_messages)
        
        # Inject execution_id context into the latest user message only (for LLM only, not stored)
        if combined_messages:
            combined_messages = combined_messages.copy()
            last_user_idx = None
            for idx in range(len(combined_messages) - 1, -1, -1):
                if combined_messages[idx].get("role") == "user":
                    last_user_idx = idx
                    break

            if last_user_idx is not None:
                combined_messages[last_user_idx] = {
                    **combined_messages[last_user_idx],
                    "content": combined_messages[last_user_idx].get("content", "") + exec_context
                }
        
        # Calculate actual input size (character count)
        input_length = sum(len(str(msg.get('content', ''))) for msg in combined_messages)
        print(f"📊 Context: {context_length} messages, {input_length} chars sent to LLM")
        
        response_text = ""
        compact_response_text = ""
        response_messages: List[Dict] = []
        try:
            for response in self.agent.run(messages=combined_messages):
                response_text = typewriter_print(response, response_text)
                if self.prune_intermediate_task_contexts:
                    compact_response_text = self._compact_assistant_chunk_text(response_text)
                if isinstance(response, dict):
                    response_messages.append(response)
        except Exception as e:
            response_text = f"Error: {str(e)}"
            compact_response_text = self._compact_assistant_chunk_text(response_text)
            response_messages = [{"role": "assistant", "content": response_text}]
            self.execution_cache[execution_id] = "FAILED"

        # Determine whether this turn has verified tool-flow evidence.
        runtime_tool_evidence = self._has_runtime_tool_evidence(response_messages)
        text_tool_evidence = self._response_text_indicates_tool_flow(response_text)
        has_verified_tool_evidence = runtime_tool_evidence or text_tool_evidence

        # Sanitize model-fabricated tool transcript tags only when no verified evidence exists.
        response_text = self._sanitize_faux_tool_transcript(
            response_text,
            response_messages,
            has_verified_tool_evidence=has_verified_tool_evidence,
        )

        # Mark SUCCESS when verified tool flow exists and this turn's execution_id appears.
        execution_id_present = (
            execution_id in response_text
            or self._tool_messages_contain_execution_id(response_messages, execution_id)
        )
        if has_verified_tool_evidence and execution_id_present:
            self.execution_cache[execution_id] = "SUCCESS"
            print(f"✅ Execution {execution_id} marked SUCCESS (verified tool event)")
        else:
            self.execution_cache[execution_id] = "FAILED"
            print(f"❌ Execution {execution_id} marked FAILED (no verified tool event)")

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

        # Memory pruning: keep full history up to current user turn + final assistant summary.
        if self.prune_intermediate_task_contexts:
            print("Pruning intermediate memory. Keeping only user turn and final response...")
            assistant_summary = None
            if response_messages:
                for msg in reversed(response_messages):
                    if msg.get("role") == "assistant":
                        assistant_summary = {
                            "role": "assistant",
                            "content": msg.get("content", response_text),
                        }
                        break
            if assistant_summary is None:
                assistant_summary = {
                    "role": "assistant",
                    "content": compact_response_text if compact_response_text else response_text,
                }

            session["messages"] = session["messages"][: user_index_flag + 1] + [assistant_summary]

        print(f"✅ After agent response: {len(session['messages'])} total messages in session")
        
        session["last_updated"] = datetime.utcnow().isoformat()
        
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
import os
import copy
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import yaml
import redis
from fastapi import FastAPI

# Model
from qwen_agent.agents import Assistant
from qwen_agent.llm.schema import Message
from qwen_agent.tools.mcp_manager import MCPManager
from qwen_agent.utils.tokenization_qwen import tokenizer as qwen_tokenizer
from qwen_agent.utils.utils import extract_text_from_message
from qwen_agent.utils.output_beautify import typewriter_print


# Memory Managment
from transformers import AutoTokenizer
from agent_memory_client import MemoryAPIClient, MemoryClientConfig
from agent_memory_client.models import WorkingMemory, MemoryMessage

from .prompts.prompt_manager import PromptUpdater
from .utils import apply_mcp_ping_compat_patch
from .workflows import (
    process_workflow_execution,
    sanitize_faux_tool_transcript
)

from .base import BaseAgent, parse_think_tags_from_responses
from ..memory.management.agent_memory_mixin import MemoryManagementMixin, compact_assistant_chunk_text


AGENT_MODE = os.getenv("AGENT_MODE","prod")

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
        # Prompts: prefer Redis latest; only read file when Redis missing
        prompt_updater = PromptUpdater()
        try:
            redis_prompt, remarks, feedback = prompt_updater.get_latest_system_prompt("chat")
        except Exception:
            redis_prompt = None

        if redis_prompt:
            self.system_prompt = redis_prompt
            self.system_prompt_status = {"success": True, "updated": False, "reason": "from-redis", "latest_key": None}
        else:
            # Fallback: read from file and historize in Redis
            prompts = self._initialized_prompts(prompt_cfg_path)
            self.system_prompt = prompts.get("system")
            self.system_prompt_status = prompt_updater.update_system_prompt_with_status("chat")

        # Tools
        mcp_config = self._initialize_mcp_cfg(actuators)
        exclude_tools = mcp_config.get('exclude-tools', [])
        mcp_tools = self._load_mcp_tools(mcp_config)
        function_tools = mcp_config['builtin-functions']
        self.tools_count = len(mcp_tools + function_tools)

        print(f"[PromptUpdater] system prompt status -> {self.system_prompt_status}")

        # Memory 
        self.memory_client = self._initialize_memory_manager()
        
        # Create agent
        self.agent = Assistant(
            llm=llm_cfg,
            system_message=self.system_prompt,
            function_list=mcp_tools + function_tools,
            files=[]
        )

        print(f"Initializing agent with system prompt {self.system_prompt}")
    
    def _initialized_prompts(self, config_path="./config/prompts"):
        # Prefer latest prompt from Redis (historized by PromptUpdater). Fallback to file.
        try:
            updater = PromptUpdater()
            prompt, remarks, feedback = updater.get_latest_system_prompt("chat")
            if prompt:
                return {"system": prompt}
        except Exception:
            pass

        try:
            with open(config_path, "r") as f: 
                prompts = yaml.safe_load(f)
        except Exception as e:
            prompts = {"system": ""}
        return prompts
    

    def compute_context_length(self, messages: List = []):
        # print(f"Computing context length for  {messages}")
        text = "".join([m.dict()["role"] + ": " + m.dict()["content"] for m in messages])
        tokens = self.tokenizer.encode(text)
        return len(tokens)

    def compute_prompt_token_length(self, messages: List[Dict], lang: str = "en") -> int:
        """Compute request prompt tokens after Qwen function-call preprocessing."""
        if not self.agent or not getattr(self.agent, "llm", None):
            return 0

        llm = self.agent.llm
        if not hasattr(llm, "_preprocess_messages"):
            return 0

        msg_dicts = [m.dict() if hasattr(m, "dict") else m for m in messages]
        if self.system_prompt and (not msg_dicts or msg_dicts[0].get("role") != "system"):
            msg_dicts = [{"role": "system", "content": self.system_prompt}] + msg_dicts

        msg_objs = [m if isinstance(m, Message) else Message(**m) for m in msg_dicts]
        functions = [func.function for func in self.agent.function_map.values()]
        generate_cfg = copy.deepcopy(getattr(llm, "generate_cfg", {}))

        try:
            preprocessed = llm._preprocess_messages(
                messages=msg_objs,
                lang=lang,
                generate_cfg=generate_cfg,
                functions=functions,
                use_raw_api=getattr(llm, "use_raw_api", False),
            )
        except Exception as e:
            print(f"[W] Prompt token preprocessing failed: {e}")
            return 0

        total = 0
        for msg in preprocessed:
            if msg.role == "assistant" and msg.function_call:
                total += qwen_tokenizer.count_tokens(f"{msg.function_call}")
            else:
                total += qwen_tokenizer.count_tokens(
                    extract_text_from_message(msg, add_upload_info=True)
                )
        return total

    async def get_latest_sessions(self, offset: int = 10) -> List[Dict[str, object]]:
        """Load latest working-memory session summaries by scanning Redis metadata timestamps."""
        if not self.memory_client or offset <= 0:
            return []


        namespace = getattr(getattr(self, "memory_client", None), "config", None)
        namespace = getattr(namespace, "default_namespace", "chat")
        user_id = self.__class__.__name__
        pattern = f"working_memory:{namespace}:{user_id}:*"

        try:
            redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)
            keys = list(redis_client.scan_iter(match=pattern))
        except Exception as e:
            print(f"[W] Failed to read working memory keys from Redis: {e}")
            return []

        # Python-side scan and sort for ReJSON keys only
        session_list = []
        for key in keys:
            try:
                key_type = redis_client.type(key)
                if key_type == b'ReJSON-RL' or key_type == 'ReJSON-RL':
                    json_obj = redis_client.json().get(key, '.')
                    last_updated = json_obj.get("updated_at") if isinstance(json_obj, dict) else 0.0
                    session_list.append({
                        "session_id": key.split(":")[-1],
                        "timestamp": float(last_updated) if last_updated else 0.0,
                    })
            except Exception as e:
                print(f"[W] Failed to fetch session for key {key}: {e}")
                continue

        latest_ids = [
            item["session_id"]
            for item in sorted(session_list, key=lambda x: x["timestamp"], reverse=True)[:offset]
        ]

        latest_sessions: List[Dict[str, object]] = []
        for session_id in latest_ids:
            first_user_message = None
            try:
                _, session = await self.get_session(session_id)
                if session and getattr(session, "messages", None):
                    for message in session.messages:
                        message_dict = message.dict() if hasattr(message, "dict") else message
                        if message_dict.get("role") == "user":
                            first_user_message = compact_assistant_chunk_text(
                                message_dict.get("content", ""),
                                120,
                            )
                            break
            except Exception as e:
                print(f"[W] Failed to load session contents for {session_id}: {e}")

            latest_sessions.append(
                {
                    "session_id": session_id,
                    "timestamp": next(
                        (item["timestamp"] for item in session_list if item["session_id"] == session_id),
                        0.0,
                    ),
                    "first_user_message": first_user_message,
                }
            )

        return latest_sessions

    def get_session_messages_as_dicts(self, session):
        """Return all messages as dicts for serialization/response."""
        if not session or not getattr(session, "messages", None):
            return []
        result = []
        for msg in session.messages:
            if hasattr(msg, 'dict'):
                result.append(msg.dict())
            elif isinstance(msg, dict):
                result.append(msg)
            else:
                try:
                    result.append(dict(msg))
                except Exception:
                    pass
        return result

    async def send_message(self, session_id: str, user_message: str, workflow_id: Optional[str] = None) -> tuple[str, int, int]:
        """Send a message and get response with execution verification. Returns (response_text, context_length, input_length)."""
        if not self.agent:
            raise ValueError("Agent not initialized")
        
        _, session  = await self.get_session(session_id)
        session : WorkingMemory
        if not session:
            raise ValueError(f"Session {session_id} not found")

        print("Using user generated workflow ID: ", workflow_id)
        workflow_id = workflow_id or str(uuid.uuid4())


        print("User message: ", user_message)
        # Add user message to history
        session.messages.append({"role": "user", "content": f"{user_message}. Double check if all tools are called correctly." })
        messages = [m.dict() if type(m)!=dict else m for m in session.messages]
        user_index_flag = len(messages) - 1
        print(f"📝 After adding user message: {len(messages)} messages in history")
                

        tmp = ""
        assistant_response  = ""
        structured_responses: List[Dict] = []
        task_total_token_cost = None
        task_prompt_token_cost = None
        task_gen_token_cost = None
        workflow_start_time = datetime.now()
        ttft = None
        try:
            # TODO Measure generation latency here
            # TODO Measure TTFT (time to first token)
            # TODO TEST Measure task cost (tokens)
            # TODO add token cost, latency, etc. in record
            gen_time = datetime.now()
            try:
                for response in self.agent.run(messages=messages):
                    if ttft is None:
                        ttft = datetime.now() - gen_time
                        print(f"⏱️ Time to first token: {ttft.seconds + ttft.microseconds/1e6} seconds")
                    tmp = typewriter_print(response, tmp) # for visual purposes 
            except Exception as e:
                print(f"Error during agent response generation: {e}")
                raise e
            gen_latency = datetime.now() - gen_time

            structured_responses = response
            # Parse and extract think tags from assistant responses
            structured_responses = parse_think_tags_from_responses(structured_responses)
            print("Raw structured response: ", structured_responses)

            print("DEBUG length of structured responses: ", len(structured_responses))
            task_prompt_token_cost = self.compute_prompt_token_length(messages=messages, lang="en")
            print(f"[TokenUsage] Prompt tokens: {task_prompt_token_cost}")
            assistant_responses = [r for r in structured_responses if r['role']=='assistant' ]
            task_gen_token_cost = self.compute_total_tokens(assistant_responses)
            task_total_token_cost = task_prompt_token_cost + task_gen_token_cost

            assistant_response = structured_responses[-1]['content']
        except Exception as e:
            assistant_response = f"Error: {str(e)}"
        workflow_latency = datetime.now() - workflow_start_time

        # Determine if tools called have response, record tool execcution details for evaluations
        print("DEBUG length of structured responses: ", len(structured_responses))
        workflow_exec  = process_workflow_execution(
            session_id = session_id,
            workflow_id = workflow_id,
            task = user_message, 
            response_messages = structured_responses,
            agent_type = "chat",
        )


        workflow_exec.task_total_token_cost = task_total_token_cost
        workflow_exec.task_gen_token_cost = task_gen_token_cost
        workflow_exec.task_prompt_token_cost = task_prompt_token_cost
        workflow_exec.ttft = ttft.seconds + ttft.microseconds/1e6 if ttft else None
        # workflow_exec.model_generation_latency = gen_latency.seconds + gen_latency.microseconds/1e6
        workflow_exec.workflow_latency = workflow_latency.seconds + workflow_latency.microseconds/1e6
        workflow_exec.system_prompt_ref = self.system_prompt_status.get("latest_key", None) if self.system_prompt_status else None
        workflow_exec.record_workflow_state()

        if workflow_exec.all_tools_verified:
            print("All tool calls verified!")
            print(workflow_exec)
        else:
            assistant_response = f"Unverified Tool Calls Found!"

        # Add assistant responses to history
        if structured_responses:
            try:
                memory_msgs = [MemoryMessage(role=sr['role'],content=sr['content']) for sr  in structured_responses[-1:]]
                session.messages.extend(memory_msgs) #final answer only
            except Exception as e:
                print(f"Error adding assistant response to session history: {e}")


        print(f"✅ After agent response: {len(session.messages)} total messages in session")
        updated_session =  await self.memory_client.put_working_memory(
            session_id = session_id,
            memory = session,
        )
        return assistant_response, self.compute_context_length(updated_session.messages), 0, workflow_id
    
    def get_health_status(self) -> Dict:
        """Get backend health status."""
        return {
            "status": "healthy",
            "mcp_tools_loaded": self.tools_count,
            "sessions_active": len(self.sessions),
            # "execution_cache": cache_stats,
            "backend_version": "1.0.0",
        }
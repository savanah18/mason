import asyncio
import importlib.util
import os
import copy
import uuid
from pathlib import Path
import yaml
import json
import threading
from typing import Dict, Iterator, List, Literal, Optional, Union, Any
from datetime import datetime

import redis


# Memory Managment
from transformers import AutoTokenizer
from agent_memory_client import MemoryAPIClient, MemoryClientConfig
from agent_memory_client.models import WorkingMemory, MemoryMessage

# Agent
from qwen_agent.agents import Assistant
from qwen_agent.llm.schema import Message
from qwen_agent.tools.base import BaseTool, register_tool 
from qwen_agent.tools.mcp_manager import MCPManager
from qwen_agent.utils.tokenization_qwen import tokenizer as qwen_tokenizer
from qwen_agent.utils.utils import extract_text_from_message
from qwen_agent.utils.output_beautify import typewriter_print

from templates.core.autonomous_agent import AutonomousAgent
from templates.core.base import BaseAgent, parse_think_tags_from_responses
from templates.core.sensor import Sensor, KafkaEventListener
from templates.mixins.json import FromJsonMixin
from templates.config.goals import GoalConfig, Goal
from templates.config.kafka import KafkaEventListenerConfig
from templates.core.context_compaction import (
    compact_assistant_chunk_text,
    inject_execution_id_context,
    prune_session_history,
    select_context_messages,
)
from templates.core.prompt_manager import PromptUpdater
from templates.core.mcp_compat import apply_mcp_ping_compat_patch
from templates.core.workflows import (
    process_workflow_execution,
    sanitize_faux_tool_transcript
)

from templates.memory.management.agent_memory_mixin import MemoryManagementMixin

from notifications.mailer import send_notification


# TODO create a function instead
PERSONA = os.getenv("PERSONA","deployer")
AGENT_MODE = os.getenv("AGENT_MODE","prod")

# Tools
from actions.tools.helm.tools import (
    HelmAddRepository,
    HelmRegistryLogin,
    HelmUpdateRepositories,
    HelmListRepositories,
    HelmRemoveRepository,
    HelmTemplate,
    HelmLint,
    HelmInstall,
    HelmUpgrade,
    HelmListReleases,
    HelmGetHistory,
    HelmGetValues,
    HelmRollback,
    HelmUninstall,
)
from actions.tools.kafka.tools import (
    KafkaProduceMessage
)
from actions.tools.resource_collector.tools import (
    ResourceCollector
)
from actions.tools.kubernetes.tools import (
    KubernetesListWorkloads,
    KubernetesGetNamespaceResourceQuota,
    KubernetesGetNamespaceEvents,
    KubernetesApplyResourceUpdate,
)

from actions.tools.prompt_optimization.tools import (
    PromptOptimizationRetrieveWorkflows
)


def _load_prompt_optimization_tools():
    """Load prompt optimization tools from a hyphenated path via importlib."""
    tool_path = Path(__file__).resolve().parent / "actions" / "tools" / "prompt-optimizaiton" / "tools.py"
    if not tool_path.exists():
        return

    spec = importlib.util.spec_from_file_location("actions.tools.prompt_optimizaiton.tools", tool_path)
    if spec is None or spec.loader is None:
        return

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


_load_prompt_optimization_tools()


class QwenOpsAgent(BaseAgent, AutonomousAgent,Assistant, FromJsonMixin, MemoryManagementMixin):
    # Redis client and section payload loader moved to `templates.core.base.BaseAgent`.

    @staticmethod
    def _initialize_sensors_from_payload(payload: dict[str, Any]) -> List[Sensor]:
        sensors: List[Sensor] = []
        for sensor in payload.get("spec", []):
            sensor_cls = globals().get(sensor.get("type"))
            config_cls = globals().get(sensor.get("config_type"))
            if sensor_cls is None or config_cls is None:
                raise ValueError(f"Unsupported sensor definition: {sensor}")
            sensors.append(sensor_cls(config=config_cls.from_json(sensor)))
        return sensors

    @staticmethod
    def _initialize_mcp_cfg_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return payload.get("spec", {}) if isinstance(payload, dict) else {}

    def __init__(
        self,
        goal: Union[Goal, Path, str],
        sensors: Union[List[Sensor], Path, str],
        actuators: Union[List[Any], Path, str],
        llm_cfg: Union[Dict, Path, str],
        prune_intermediate_task_contexts=False
    ):
        """Initialize Qwen chat agent with MCP tools."""
        print("🔧 Initializing Qwen Ops Agent...")

        # brain and reasoning
        if isinstance(llm_cfg, str) or isinstance(llm_cfg, Path):
            llm_cfg: Dict = self._initialize_llm_cfg(llm_cfg)

        # goals
        if isinstance(goal, str) or isinstance(goal, Path):
            goal: Goal = self._initialize_goal(goal)

        prompt_updater = PromptUpdater()

        # Prefer prompt from Redis; only read/write YAML when Redis has no latest
        try:
            redis_prompt, remarks, feedback = prompt_updater.get_latest_system_prompt(PERSONA)
        except Exception:
            redis_prompt = None

        if redis_prompt:
            self._resolved_system_prompt = redis_prompt
            self.system_prompt_status = {"success": True, "updated": False, "reason": "from-redis", "latest_key": None}
            print(f"[PromptUpdater] using redis latest prompt for persona={PERSONA}")
        else:
            # No redis prompt: load from file and historize it
            self.system_prompt_status = prompt_updater.update_system_prompt_with_status(PERSONA)
            print(f"[PromptUpdater] created/updated prompt from file for persona={PERSONA} -> {self.system_prompt_status}")
            try:
                redis_prompt, remarks, feedback = prompt_updater.get_latest_system_prompt(PERSONA)
            except Exception:
                redis_prompt = None
            self._resolved_system_prompt = redis_prompt if redis_prompt else f"{goal.description}"

        # sensory tools
        sensor_payload = self._load_section_payload_from_redis(PERSONA, "sensors")
        if isinstance(sensors, str) or isinstance(sensors, Path):
            sensors = self._initialize_sensors_from_payload(sensor_payload) if sensor_payload else self._initialize_sensors(sensors)

        # actuators
        actuator_payload = self._load_section_payload_from_redis(PERSONA, "actuators")
        mcp_tools: List[Any] = []
        function_tools: List[Any] = []
        if isinstance(actuators, str) or isinstance(actuators, Path):
            actuators = self._initialize_mcp_cfg_from_payload(actuator_payload) if actuator_payload else self._initialize_mcp_cfg(actuators)

        if isinstance(actuators, dict):
            exclude_tools = actuators.get('exclude-tools', [])
            mcp_tools = self._load_mcp_tools(actuators, exclude_tools)
            function_tools = actuators.get('builtin-functions', [])
            self.tools_count = len(mcp_tools + function_tools)

        # memory
        self.sessions = {} # PLACEHOLDER ONLY
        self.memory_client = self._initialize_memory_manager()

        # notification
        self.email_notification_enabled = os.getenv("EMAIL_NOTIFICATION_ENABLED", "false").lower() == "true"
        if self.email_notification_enabled:
            print("📧 Email notifications enabled. Loading email app password from file...")
            with open(os.getenv("EMAIL_APP_PASSWORD_FILE"), "r") as f:
                self.email_app_password = f.read().strip()

        # print(f"[I] Initializing {PERSONA} agent with goal \n {goal.description}")
        # Initialize AutonomousAgent
        AutonomousAgent.__init__(
            self,
            goal=goal, 
            sensors=sensors, 
            actuators=actuators
        )
        
        # Initialize Assistant        
        Assistant.__init__(
            self,
            llm=llm_cfg,
            system_message=self._resolved_system_prompt,
            function_list= function_tools + mcp_tools,
            files=[]
        )
        print("Initializing agent with the following system prompt")
        print("*"*20)
        print(f"{goal.description}")

    @staticmethod
    def _apply_mcp_ping_compat_patch():
        """Allow MCP servers that do not implement ping (legacy stdio servers)."""
        apply_mcp_ping_compat_patch()

    def compute_prompt_token_length(self, messages: List[Dict], lang: str = "en") -> int:
        """Compute request prompt tokens after Qwen function-call preprocessing."""
        if not getattr(self, "llm", None):
            return 0

        llm = self.llm
        if not hasattr(llm, "_preprocess_messages"):
            return 0

        msg_dicts = [m.dict() if hasattr(m, "dict") else m for m in messages]
        if self.system_message and (not msg_dicts or msg_dicts[0].get("role") != "system"):
            msg_dicts = [{"role": "system", "content": self.system_message}] + msg_dicts

        msg_objs = [m if isinstance(m, Message) else Message(**m) for m in msg_dicts]
        functions = [func.function for func in self.function_map.values()]
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

    async def reason(self, percepts=[], workflow_id=None):
        # Wrap reason with try except and add handling with memory management and workflow execution recording for evaluations
        #****************** START OF WORKFLOW ******************
        print("Perfoming reasoning.... ")
        workflow_start_time = datetime.now()
        try:
            print("Trying to extract workflow id from percepts")
            workflow_id: str = percepts[0]['data'].get('workflow_id', None) or str(uuid.uuid4())
            if workflow_id:
                print(f"Extracted {workflow_id} from percepts")
        except Exception as e:
            workflow_id = str(uuid.uuid4())

        # TODO Prompt should be dynamic, and base prompt should always be retrieved to accomodate prompt updates.
        prompt = {
            'role': 'user', 
            'content': f"""
                IMPORTANT! Your task is to **ALWAYS** execute necesary tools for the requested task, even if it task looks similar to a previous request.
                Do not assume prior execution is sufficient.
                Percepts: {json.dumps([p['data'] for p in percepts])}
                Current workflow ID: {workflow_id}
                Action: {self.goal.base_prompt}
            """
        }

        # THIS PROMPT IS FOR MOCK PLAN ONLY
        # prompt = {
        #     'role': 'user', 
        #     'content': f"""
        #         Percepts: {json.dumps([p['data'] for p in percepts])}
        #         Current workflow ID: {workflow_id}
        #         DO NOT execute any tools, this is a test workflow to verify agent planning capabilities.
        #         I repeat **DO NOT EXECUTE ANY TOOLS**. Just return the plan of which tools would have been executed in a structured format.
        #         **IMPORTANT** SKIP pre-checks tools when in Plan Mode.
        #         Action: Plan instructions from perceived event.
        #     """
        # }

        print(prompt)

        # Use a deterministic session per workflow to avoid cross-task history bleed.
        session_id = f"{PERSONA}:{workflow_id}"
        _, session = await self.get_session(session_id)
        session : WorkingMemory

        # Add user message to history
        session.messages.append(prompt)
        messages = [m.dict() if type(m)!=dict else m for m in session.messages]
        user_index_flag = len(messages) - 1
        print(f"📝 After adding user message: {len(messages)} messages in history")

        tmp = ""
        assistant_response  = ""
        structured_responses: List[Dict] = []
        thoughts: List[str] = []
        task_total_token_cost = None
        task_prompt_token_cost = None
        task_gen_token_cost = None
        ttft = None
        try:
            # TODO Measure generation latency here
            # TODO Measure TTFT (time to first token)
            gen_time = datetime.now()
            for response in self.run(messages=messages):
                if ttft is None:
                    ttft = datetime.now() - gen_time
                    print(f"⏱️ Time to first token: {ttft.seconds + ttft.microseconds/1e6} seconds")
                tmp = typewriter_print(response, tmp)
                # print("iterator response", type(response), response)
            gen_latency = datetime.now() - gen_time

            structured_responses = response
            # Parse and extract think tags from assistant responses
            structured_responses = parse_think_tags_from_responses(structured_responses)
            thoughts = [r.get("thought") for r in structured_responses if r.get("role") == "assistant" and r.get("thought")]
            task_prompt_token_cost = self.compute_prompt_token_length(messages=messages, lang="en")
            print(f"[TokenUsage] Prompt tokens: {task_prompt_token_cost}")
            assistant_responses = [r for r in structured_responses if r['role']=='assistant' ]
            task_gen_token_cost = self.compute_total_tokens(assistant_responses)
            task_total_token_cost = task_prompt_token_cost + task_gen_token_cost

            print(f"Assistant response: {assistant_response}")
            assistant_response = response[-1]['content'] # Most workflow agent answer are now in markdown format. 
            
        except Exception as e:
            assistant_response = f"Error: {type(e)} {str(e)}"
        #****************** END OF WORKFLOW ******************
        workflow_latency = datetime.now() - workflow_start_time

        #****************** START OF WORKFLOW STATS AND TRACEABILITY ******************
        # Determine if tools called have response, record tool execcution details for evaluations
        print("Processing workflow")
        workflow_exec  = process_workflow_execution(
            session_id = session_id,
            workflow_id = workflow_id,
            task = prompt['content'], 
            response_messages = structured_responses,
            agent_type = PERSONA,
            #TODO agent mode args
        )
        workflow_exec.task_total_token_cost = task_total_token_cost
        workflow_exec.task_prompt_token_cost = task_prompt_token_cost
        workflow_exec.task_gen_token_cost = task_gen_token_cost
        workflow_exec.ttft = ttft.seconds + ttft.microseconds/1e6 if ttft else None
        # workflow_exec.model_generation_latency = gen_latency.seconds + gen_latency.microseconds/1e6
        workflow_exec.workflow_latency = workflow_latency.seconds + workflow_latency.microseconds/1e6
        workflow_exec.system_prompt_ref = self.system_prompt_status.get("latest_key", None) if self.system_prompt_status else None
        workflow_exec.thoughts = thoughts

        if workflow_exec.all_tools_verified:
            print("All tool calls verified!")
        else:
            assistant_response = f"Unverified Tool Calls Found!"

        # record workflow
        print("Recording workflow state")
        workflow_exec.record_workflow_state()
        #****************** END OF WORKFLOW STATS AND TRACEABILITY *******************

        #****************** START OF NOTIFICATION ******************
        if self.email_notification_enabled:
            send_notification(
                recipient_email="aglubagerry@gmail.com",
                subject=f"Workflow Execution Complete - {workflow_id}",
                body=workflow_exec.result,
                app_password=self.email_app_password
            )



        #****************** START OF HISTORIZATION ******************
        print("Historization")
        # Add assistant responses to history
        if structured_responses:
            memory_msgs = [MemoryMessage(role=sr['role'],content=sr['content']) for sr  in structured_responses[-1:]]
            session.messages.extend(memory_msgs) #final answer only

        await self.memory_client.put_working_memory(
            session_id = session_id,
            memory = session
        )
        #****************** END OF HISTORIZATION ******************

async def main():
    inference_server_type = os.getenv("INFERENCE_SERVER_TYPE", "tensorrt-llm")
    agent = QwenOpsAgent(
        goal = f"./personas/{PERSONA}/goal.yaml",
        sensors = f"./personas/{PERSONA}/sensors.yaml",
        llm_cfg = f"./templates/llm/qwen.{inference_server_type}.yaml",
        actuators = f"./personas/{PERSONA}/actuators.yaml",
        prune_intermediate_task_contexts = True
    )
    # agent.session_id = await agent.create_session(PERSONA)
    await agent.launch()

if __name__ == "__main__":
    asyncio.run(main())
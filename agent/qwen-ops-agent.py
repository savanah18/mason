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
from templates.core.config.config import PersonaConfig
from templates.core.config.resolver import ConfigResolver
from templates.core.sensor import Sensor, KafkaEventListener, build_sensors_from_config
from templates.core.mixins.json import FromJsonMixin
from templates.core.config.goals import GoalConfig, Goal
from templates.core.config.kafka import KafkaEventListenerConfig
from templates.core.prompts.prompt_manager import PromptUpdater
from templates.core.utils import apply_mcp_ping_compat_patch
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

from templates.core.actuator import build_actuators_from_config


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


class QwenOpsAgent(BaseAgent, AutonomousAgent, Assistant, MemoryManagementMixin):
    def __init__(self, persona_config: PersonaConfig):
        """Initialize Qwen Ops Agent from resolved persona configuration."""
        print("🔧 Initializing Qwen Ops Agent...")

        self.persona_config = persona_config
        self.persona = persona_config.persona or PERSONA

        # LLM Configuration
        llm_cfg = persona_config.llm_cfg

        # Goals and System Prompts
        prompt_updater = PromptUpdater()
        self.system_prompt_status = prompt_updater.resolve_system_prompt(self.persona)
        self._resolved_system_prompt = self.system_prompt_status.get("prompt") or f"{persona_config.goal.description}"

        # Sensors and Actuators
        sensors = build_sensors_from_config(persona_config.sensors)
        actuators = build_actuators_from_config(persona_config.actuators)
        self.tools_count = len(actuators)

        # Memory Management
        self.memory_client = self._initialize_memory_manager()

        # Others
        self.email_notification_enabled = os.getenv("EMAIL_NOTIFICATION_ENABLED", "false").lower() == "true"
        if self.email_notification_enabled:
            print("📧 Email notifications enabled. Loading email app password from file...")
            with open(os.getenv("EMAIL_APP_PASSWORD_FILE"), "r") as f:
                self.email_app_password = f.read().strip()


        # Base class initializations
        AutonomousAgent.__init__(
            self,
            goal=persona_config.goal,
            sensors=sensors,
            actuators=actuators,
        )

        Assistant.__init__(
            self,
            llm=llm_cfg,
            system_message=self._resolved_system_prompt,
            function_list=actuators,
            files=[],
        )

        print("Initializing agent with the following system prompt")
        print("*" * 20)
        print(f"{persona_config.goal.description}")

    def _resolve_workflow_id(self, percepts: List[Dict], workflow_id: Optional[str] = None) -> str:
        if workflow_id:
            return workflow_id

        try:
            return percepts[0]["data"].get("workflow_id") or str(uuid.uuid4())
        except Exception:
            return str(uuid.uuid4())

    def _build_reasoning_prompt(self, percepts: List[Dict], workflow_id: str) -> Dict[str, str]:
        percept_data = [p.get("data", {}) for p in percepts]
        return {
            "role": "user",
            "content": f"""
                IMPORTANT! Your task is to **ALWAYS** execute necesary tools for the requested task, even if it task looks similar to a previous request.
                Do not assume prior execution is sufficient.
                Percepts: {json.dumps(percept_data)}
                Current workflow ID: {workflow_id}
                Action: {self.goal.base_prompt}
            """
        }

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

    async def _load_reasoning_session(self, workflow_id: str):
        session_id = f"{self.persona}:{workflow_id}"
        _, session = await self.get_session(session_id)
        return session_id, session

    def _execute_reasoning_turn(self, messages: List[Dict]) -> Dict[str, Any]:
        tmp = ""
        structured_responses: List[Dict] = []
        thoughts: List[str] = []
        task_total_token_cost = None
        task_prompt_token_cost = None
        task_gen_token_cost = None
        ttft = None
        gen_latency = None
        assistant_response = ""

        try:
            gen_time = datetime.now()
            response = None
            for response in self.run(messages=messages):
                if ttft is None:
                    ttft = datetime.now() - gen_time
                    print(f"⏱️ Time to first token: {ttft.seconds + ttft.microseconds/1e6} seconds")
                tmp = typewriter_print(response, tmp)

            gen_latency = datetime.now() - gen_time
            structured_responses = parse_think_tags_from_responses(response or [])
            thoughts = [
                r.get("thought")
                for r in structured_responses
                if r.get("role") == "assistant" and r.get("thought")
            ]
            # Keep execution focused: metrics are collected separately
            if response:
                assistant_response = response[-1].get("content", "")
        except Exception as e:
            assistant_response = f"Error: {type(e)} {str(e)}"

        return {
            "structured_responses": structured_responses,
            "assistant_response": assistant_response,
            "thoughts": thoughts,
            "task_total_token_cost": task_total_token_cost,
            "task_prompt_token_cost": task_prompt_token_cost,
            "task_gen_token_cost": task_gen_token_cost,
            "ttft": ttft,
            "gen_latency": gen_latency,
        }

    def _collect_reasoning_metrics(self, messages: List[Dict], structured_responses: List[Dict], ttft: Optional[datetime], gen_latency: Optional[datetime]) -> Dict[str, Any]:
        task_prompt_token_cost = None
        task_gen_token_cost = None
        task_total_token_cost = None

        try:
            task_prompt_token_cost = self.compute_prompt_token_length(messages=messages, lang="en")
            print(f"[TokenUsage] Prompt tokens: {task_prompt_token_cost}")
            assistant_responses = [r for r in structured_responses if r.get("role") == "assistant"]
            task_gen_token_cost = self.compute_total_tokens(assistant_responses)
            task_total_token_cost = (task_prompt_token_cost or 0) + (task_gen_token_cost or 0)
        except Exception as e:
            print(f"[W] Metrics collection failed: {e}")

        return {
            "task_prompt_token_cost": task_prompt_token_cost,
            "task_gen_token_cost": task_gen_token_cost,
            "task_total_token_cost": task_total_token_cost,
            "ttft": ttft,
            "gen_latency": gen_latency,
        }

    async def _record_workflow_execution(
        self,
        prompt: Dict[str, str],
        session_id: str,
        workflow_id: str,
        session: WorkingMemory,
        run_result: Dict[str, Any],
        workflow_start_time: datetime,
    ) -> Any:
        structured_responses = run_result.get("structured_responses") or []
        response_messages = structured_responses or [
            {"role": "assistant", "content": run_result.get("assistant_response", "")}
        ]

        print("Processing workflow")
        workflow_exec = process_workflow_execution(
            session_id=session_id,
            workflow_id=workflow_id,
            task=prompt["content"],
            response_messages=response_messages,
            agent_type=self.persona,
        )

        # Collect token/latency metrics using helper (if available)
        try:
            messages_for_metrics = [m.dict() if type(m) != dict else m for m in session.messages]
        except Exception:
            messages_for_metrics = []

        metrics = self._collect_reasoning_metrics(
            messages=messages_for_metrics,
            structured_responses=structured_responses,
            ttft=run_result.get("ttft"),
            gen_latency=run_result.get("gen_latency"),
        )

        workflow_exec.task_total_token_cost = metrics.get("task_total_token_cost")
        workflow_exec.task_prompt_token_cost = metrics.get("task_prompt_token_cost")
        workflow_exec.task_gen_token_cost = metrics.get("task_gen_token_cost")

        ttft = metrics.get("ttft")
        workflow_exec.ttft = ttft.seconds + ttft.microseconds / 1e6 if ttft else None
        gen_latency = metrics.get("gen_latency")
        workflow_exec.model_generation_latency = (
            gen_latency.seconds + gen_latency.microseconds / 1e6 if gen_latency else None
        )

        workflow_latency = datetime.now() - workflow_start_time
        workflow_exec.workflow_latency = workflow_latency.seconds + workflow_latency.microseconds / 1e6
        workflow_exec.system_prompt_ref = self.system_prompt_status.get("latest_key", None) if self.system_prompt_status else None
        workflow_exec.thoughts = run_result.get("thoughts", [])

        if workflow_exec.all_tools_verified:
            print("All tool calls verified!")
        else:
            print("Unverified Tool Calls Found!")

        print("Recording workflow state")
        workflow_exec.record_workflow_state()

        if self.email_notification_enabled:
            send_notification(
                recipient_email="aglubagerry@gmail.com",
                subject=f"Workflow Execution Complete - {workflow_id}",
                body=workflow_exec.result,
                app_password=self.email_app_password,
            )

        print("Historization")
        final_message = response_messages[-1]
        session.messages.append(
            MemoryMessage(role=final_message["role"], content=final_message["content"])
        )
        await self.memory_client.put_working_memory(
            session_id=session_id,
            memory=session,
        )

        return workflow_exec

    async def reason(self, percepts=[], workflow_id=None):
        print("Perfoming reasoning.... ")
        workflow_start_time = datetime.now()
        workflow_id = self._resolve_workflow_id(percepts, workflow_id)
        print(f"Extracted {workflow_id} from percepts")

        prompt = self._build_reasoning_prompt(percepts, workflow_id)
        print(prompt)

        session_id, session = await self._load_reasoning_session(workflow_id)
        session.messages.append(prompt)
        session_messages = [m.dict() if type(m) != dict else m for m in session.messages]
        print(f"📝 After adding user message: {len(session_messages)} messages in history")

        run_result = self._execute_reasoning_turn(session_messages)
        await self._record_workflow_execution(
            prompt=prompt,
            session_id=session_id,
            workflow_id=workflow_id,
            session=session,
            run_result=run_result,
            workflow_start_time=workflow_start_time,
        )

async def main():
    base_path = Path(__file__).resolve().parent
    resolver = ConfigResolver()
    persona_config = resolver.resolve(PERSONA, base_path)
    agent = QwenOpsAgent(persona_config=persona_config)
    await agent.launch()

if __name__ == "__main__":
    asyncio.run(main())
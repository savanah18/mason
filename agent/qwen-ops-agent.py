import asyncio
import os
import uuid
from pathlib import Path
import yaml
import json
import threading
from typing import Dict, Iterator, List, Literal, Optional, Union, Any
from datetime import datetime


from templates.core.autonomous_agent import AutonomousAgent
from templates.core.base import BaseAgent
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
from templates.core.mcp_compat import apply_mcp_ping_compat_patch
from templates.core.workflows import (
    process_workflow_execution,
    sanitize_faux_tool_transcript
)

from templates.memory.management.agent_memory_mixin import MemoryManagementMixin

from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool 
from qwen_agent.tools.mcp_manager import MCPManager
from qwen_agent.utils.output_beautify import typewriter_print

PERSONA = os.getenv("PERSONA","deployer")

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


class QwenOpsAgent(BaseAgent, AutonomousAgent,Assistant, FromJsonMixin, MemoryManagementMixin):
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

        # sensory tools
        if isinstance(sensors, str) or isinstance(sensors, Path):
            sensors: List[Sensor] = self._initialize_sensors(sensors)

        # actuators
        if isinstance(actuators, str) or isinstance(actuators, Path):
            actuators  = self._initialize_mcp_cfg(actuators)
            exclude_tools = actuators['exclude-tools']
            mcp_tools = self._load_mcp_tools(actuators, exclude_tools)
            function_tools = actuators['builtin-functions']
            self.tools_count = len(mcp_tools + function_tools)

        # memory
        self.sessions = {} # PLACEHOLDER ONLY
        self.memory_client = self._initialize_memory_manager()

        print(f"[I] Initializing {PERSONA} agent with goal \n {goal.description}")
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
            system_message=f"{goal.description}",
            function_list= function_tools + mcp_tools,
            files=[]
        )
        print("Initializing agent with the following system prompt")
        print("*"*20)
        print(f"{goal.description}")
        print(f"Agent has the following tools in its arsenal {mcp_tools + function_tools}")

    @staticmethod
    def _apply_mcp_ping_compat_patch():
        """Allow MCP servers that do not implement ping (legacy stdio servers)."""
        apply_mcp_ping_compat_patch()

    async def reason(self, percepts=[], workflow_id=None):
        #****************** START OF WORKFLOW ******************
        print("Perfoming reasoning.... ")
        workflow_start_time = datetime.now()
        # TODO Goal Life Cycle Management
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

        _, session = await self.get_session(self.session_id)
        session : WorkingMemory

        # Add user message to history
        session.messages.append(prompt)
        messages = [m.dict() if type(m)!=dict else m for m in session.messages]
        user_index_flag = len(messages) - 1
        print(f"📝 After adding user message: {len(messages)} messages in history")

        tmp = ""
        assistant_response  = ""
        structured_responses: List[Dict] = []
        task_total_token_cost = None
        task_gen_token_cost = None
        try:
            # TODO Measure generation latency here
            gen_time = datetime.now()
            for response in self.run(messages=messages):
                tmp = typewriter_print(response, tmp)
            gen_latency = datetime.now() - gen_time

            structured_responses = response
            # TODO TEST Measure task codes (tokens)
            # ---> system prompt + history + user prompt + tool call/response + final answer
            to_compute_tokens = [{"role": "system", "content": self.goal.description }] + messages + structured_responses
            task_total_token_cost = self.compute_total_tokens(to_compute_tokens)
            # TODO (exclude tooling input tokens from structured response)
            task_gen_token_cost = self.compute_total_tokens(structured_responses)

            assistant_response = response[-1]['content'] # Most workflow agent answer are now in markdown format. 
            # print(structured_responses)
        except Exception as e:
            assistant_response = f"Error: {type(e)} {str(e)}"
        #****************** END OF WORKFLOW ******************
        workflow_latency = datetime.now() - workflow_start_time

        #****************** START OF WORKFLOW STATS AND TRACEABILITY ******************
        # Determine if tools called have response, record tool execcution details for evaluations
        workflow_exec  = process_workflow_execution(
            session_id = self.session_id, 
            workflow_id = workflow_id,
            task = prompt['content'], 
            response_messages = structured_responses
        )
        # TODO add token cost, latency, etc. and record
        workflow_exec.task_total_token_cost = task_total_token_cost
        workflow_exec.task_gen_token_cost = task_gen_token_cost
        workflow_exec.model_generation_latency = gen_latency.seconds + gen_latency.microseconds/1e6
        workflow_exec.workflow_latency = workflow_latency.seconds + workflow_latency.microseconds/1e6

        # record 
        workflow_exec.record_workflow_state()
        #****************** END OF WORKFLOW STATS AND TRACEABILITY ******************


        if workflow_exec.all_tools_verified:
            print("All tool calls verified!")
        else:
            assistant_response = f"Unverified Tool Calls Found!"


        #****************** START OF HISTORIZATION ******************
        # Add assistant responses to history
        if structured_responses:
            session.messages.extend(structured_responses[-1:]) #final answer only

        await self.memory_client.put_working_memory(
            session_id = self.session_id,
            memory = session
        )
        #****************** END OF HISTORIZATION ******************

async def main():
    agent = QwenOpsAgent(
        goal = f"./personas/{PERSONA}/goal.yaml",
        sensors = f"./personas/{PERSONA}/sensors.yaml",
        llm_cfg = "./templates/llm/qwen.yaml",
        actuators = f"./personas/{PERSONA}/actuators.yaml",
        prune_intermediate_task_contexts = True
    )
    agent.session_id = await agent.create_session(PERSONA)
    await agent.launch()

if __name__ == "__main__":
    asyncio.run(main())
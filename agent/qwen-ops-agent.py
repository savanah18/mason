import asyncio
import os
import uuid
from pathlib import Path
import yaml
import json
import threading
from typing import Dict, Iterator, List, Literal, Optional, Union, Any


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
        # self.session_id = await self.create_session()

        print(goal)
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

    async def reason(self, percepts=[]):
        print("Perfoming reasoning.... ")
        # TODO Goal Life Cycle Management
        workflow_id: str = (uuid.uuid4())
        prompt = {
            'role': 'user', 
            'content': f"""
                {self.goal.base_prompt} 
                Use the following information. 
                Use the following workflow_id, {workflow_id}.
                {json.dumps([percept['data'] for percept in percepts])}.
                
            """
        }
        # self.messages.append(prompt)
        # user_index_flag = len(self.messages) - 1
        # response_plain_text = ''
        # compact_response_text = ""
        # response_messages: List[Dict] = []
        # print("Debug.... ")

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
        try:
            for response in self.run(messages=messages):
                tmp = typewriter_print(response, tmp)

            structured_responses = response
            assistant_response = response[-1]['content'] # Most workflow agent answer are now in markdown format. 
            print(structured_responses)
        except Exception as e:
            assistant_response = f"Error: {type(e)} {str(e)}"

        # Determine if tools called have response, record tool execcution details for evaluations
        workflow_exec  = process_workflow_execution(
            session_id = self.session_id, 
            workflow_id = workflow_id,
            task = prompt['content'], 
            response_messages = structured_responses
        )
        workflow_exec.record_workflow_state()
        if workflow_exec.all_tools_verified:
            print("All tool calls verified!")
        else:
            assistant_response = f"Unverified Tool Calls Found!"

        # Add assistant responses to history
        if structured_responses:
            session.messages.extend(structured_responses[-1:]) #final answer only

        await self.memory_client.put_working_memory(
            session_id = self.session_id,
            memory = session
        )
        
async def main():
    agent = QwenOpsAgent(
        goal = f"./personas/{PERSONA}/goal.yaml",
        sensors = f"./personas/{PERSONA}/sensors.yaml",
        llm_cfg = "./templates/llm/qwen.yaml",
        actuators = f"./personas/{PERSONA}/actuators.yaml",
        prune_intermediate_task_contexts = True
    )
    agent.session_id = await agent.create_session()
    await agent.launch()

if __name__ == "__main__":
    asyncio.run(main())
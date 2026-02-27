

from pathlib import Path
from typing import Dict, Iterator, List, Literal, Optional, Union, Any
import yaml
import json

from templates.core.autonomous_agent import BaseAgent
from templates.core.sensor import Sensor, KafkaEventListener
from templates.mixins.json import FromJsonMixin
from templates.config.goals import GoalConfig, Goal
from templates.config.kafka import KafkaEventListenerConfig

from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool 
from qwen_agent.tools.mcp_manager import MCPManager
from qwen_agent.utils.output_beautify import typewriter_print

# Import Helm tools for Kubernetes package management
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



class QwenOpsAgent(BaseAgent, FromJsonMixin, Assistant):
    def __init__(
        self,
        goal: Union[Goal, Path, str],
        sensors: Union[List[Sensor], Path, str],
        actuators: Union[List[Any], Path, str],
        llm_cfg: Union[Dict, Path, str],
        prune_intermediate_task_contexts=False
    ):
        if isinstance(goal, str) or isinstance(goal, Path):
            with open(goal, "r") as f: 
                data = yaml.safe_load(f)
                goal = Goal(config=GoalConfig.from_json(data['spec']))
        if isinstance(sensors, str) or isinstance(sensors, Path):
            with open(sensors, "r") as f: 
                data = yaml.safe_load(f)
                # Resolve sensors agnostically
                sensors = [
                    globals()[sensor['type']](config=globals()[sensor['config_type']].from_json(sensor))
                    for sensor in data['spec']
                ]
        if isinstance(llm_cfg, str) or isinstance(llm_cfg, Path):
            with open(llm_cfg, "r") as f: 
                llm_cfg = yaml.safe_load(f)
        if isinstance(actuators, str) or isinstance(actuators, Path):
            with open(actuators, "r") as f: 
                data = yaml.safe_load(f)
                actuators = data['spec']


        print(f"[I] Initializing deployer agent with goal \n {goal.description}")
        print(f"[I] Configuring llm client ... \n{llm_cfg}")
        if prune_intermediate_task_contexts:
            print(f"[W] Prune Intermediate task contexts enabled...")
        self.prune_intermediate_task_contexts = prune_intermediate_task_contexts

        # Initialize BaseAgent
        BaseAgent.__init__(
            self,
            goal=goal, 
            sensors=sensors, 
            actuators=actuators
        )
        
        # Initialize Assistant (Qwen)
        exclude_tools = actuators['exclude-tools']
        mcp_tools = self.configure_mcp_tools(actuators['mcp-servers'], exclude_tools) if actuators else []
        function_tools = actuators['builtin-functions'] if actuators else []
        
        # Combine goal description, base_prompt, and playbook into system message
        system_message = f"{goal.description}"
        
        Assistant.__init__(
            self,
            llm=llm_cfg,
            system_message=system_message,
            function_list= function_tools + mcp_tools,
            files=[]
        )

    def configure_mcp_tools(self, mcpServers: dict ={}, exclude_tools: List[Any] = []):
        mcp_tools = []
        mcp_config = {"mcpServers": mcpServers}
        try:
            mcp_tools = MCPManager().initConfig(mcp_config)
            mcp_tools = [t for t in mcp_tools if t.name not in exclude_tools]
            print(f"[I] Successfully loaded {len(mcp_tools)} MCP tools")
        except Exception as e:
            print(f"[E] Failed to initialize MCP servers: {e}")
            print("  Continuing with limited functionality...")
        finally: 
            return mcp_tools


    def reason(self, percepts=[]):
        # TODO Goal Life Cycle Management
        print("Perfoming reasoning.... ")
        prompt = {
            'role': 'user', 
            'content': [
                {
                    'text': f"""
                        {self.goal.base_prompt}
                        {self.goal.playbook}
                        {json.dumps([percept['data'] for percept in percepts])}.
                    """
                },
            ]
        }
        self.messages.append(prompt)
        user_index_flag = len(self.messages) - 1
        response = []
        response_plain_text = ''
        for response in self.run(messages=self.messages):
            # Streaming output.
            response_plain_text = typewriter_print(response, response_plain_text)
        
        # Memory Pruning 
        if self.prune_intermediate_task_contexts:
            print("Pruning intermediate memory. Keeping only user and task summary...")
            self.messages = self.messages[:user_index_flag + 1] + [self.messages[-1]]


if __name__ == "__main__":
    agent = QwenOpsAgent(
        goal = "./personas/deployer/goal.yaml",
        sensors = "./personas/deployer/sensors.yaml",
        llm_cfg = "./templates/llm/qwen.yaml",
        actuators = "./personas/deployer/actuators.yaml",
        prune_intermediate_task_contexts = True
    )
    agent.launch()
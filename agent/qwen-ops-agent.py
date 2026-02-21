
from pathlib import Path
from typing import Dict, Iterator, List, Literal, Optional, Union
import yaml
import json

from templates.core.autonomous_agent import BaseAgent
from templates.core.sensor import Sensor, KafkaEventListener
from templates.mixins.json import FromJsonMixin
from templates.config.goals import GoalConfig, Goal
from templates.config.kafka import KafkaEventListenerConfig

from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool 
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
        llm_cfg: Union[Dict, Path, str]
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

        print(f"Initializing deployer agent with goal \n {goal.description}")
        print(f"Configuring llm client ... \n{llm_cfg}")

        # Initialize BaseAgent
        BaseAgent.__init__(
            self,
            goal=goal, 
            sensors=sensors, 
            actuators=None
        )
        
        # Initialize Assistant (Qwen)
        Assistant.__init__(
            self,
            llm=llm_cfg,
            system_message=goal.description,
            function_list=[
                # Helm Repository Management Tools
                'helm-add-repository',
                'helm-registry-login',
                'helm-update-repositories',
                'helm-list-repositories',
                'helm-remove-repository',
                # Helm Chart Validation Tools
                'helm-template',
                # 'helm-lint',
                # Helm Release Management Tools
                'helm-install',
                'helm-upgrade',
                # Helm Release Inspection Tools
                'helm-list-releases',
                'helm-get-history',
                'helm-get-values',
                # Helm Release Lifecycle Tools
                'helm-rollback',
                'helm-uninstall',
            ],
            files=[]
        )

    def reason(self, percepts=[]):
        print("Perfoming reasoning.... ")
        prompt = {
            'role': 'user', 
            'content': [
                {'text': f"Execute request in accordance to system prompt.\n Act based on the following context.\n {json.dumps([percept['data'] for percept in percepts])}"}, 
            ]
        }
        print(prompt)
        self.messages.append(prompt)
        response = []
        response_plain_text = ''
        for response in self.run(messages=self.messages):
            # Streaming output.
            response_plain_text = typewriter_print(response, response_plain_text)
        # Append the bot responses to the chat history.
        self.messages.extend(response)

if __name__ == "__main__":
    agent = QwenOpsAgent(
        goal = "./personas/deployer/goal.yaml",
        sensors = "./personas/deployer/sensors.yaml",
        llm_cfg = "./templates/llm/qwen.yaml"
    )
    agent.launch()
import os
import uuid
from pathlib import Path
from typing import Dict, Iterator, List, Literal, Optional, Union, Any
import yaml
import json

from templates.core.autonomous_agent import BaseAgent
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
from templates.core.response_guardrails import (
    has_runtime_tool_evidence,
    sanitize_faux_tool_transcript,
    tool_messages_contain_execution_id,
    verify_and_sanitize_execution_ids,
)

from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool 
from qwen_agent.tools.mcp_manager import MCPManager
from qwen_agent.utils.output_beautify import typewriter_print

PERSONA = os.getenv("PERSONA","deployer")

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


        print(f"[I] Initializing {PERSONA} agent with goal \n {goal.description}")
        print(f"[I] Configuring llm client ... \n{llm_cfg}")
        if prune_intermediate_task_contexts:
            print(f"[W] Prune Intermediate task contexts enabled...")
        self.prune_intermediate_task_contexts = prune_intermediate_task_contexts
        self.compact_chunk_max_chars = int(os.getenv("COMPACT_CHUNK_MAX_CHARS", "1800"))
        # Execution cache: execution_id -> "IN_PROGRESS" | "SUCCESS" | "FAILED"
        self.execution_cache: Dict[str, str] = {}

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
        print("Initializing agent with the following system prompt")
        print("*"*20)
        print(system_message)
        print(f"Agent has the following tools in its arsenal {mcp_tools + function_tools}")

    @staticmethod
    def _apply_mcp_ping_compat_patch():
        """Allow MCP servers that do not implement ping (legacy stdio servers)."""
        apply_mcp_ping_compat_patch()

    def configure_mcp_tools(self, mcpServers: dict ={}, exclude_tools: List[Any] = []):
        mcp_tools = []
        mcp_config = {"mcpServers": mcpServers}
        try:
            self._apply_mcp_ping_compat_patch()
            mcp_tools = MCPManager().initConfig(mcp_config)
            mcp_tools = [t for t in mcp_tools if t.name not in exclude_tools]
            print(f"[I] Successfully loaded {len(mcp_tools)} MCP tools")
        except Exception as e:
            print(f"[E] Failed to initialize MCP servers: {e}")
            print("  Continuing with limited functionality...")
        finally: 
            return mcp_tools


    def reason(self, percepts=[]):
        print("Perfoming reasoning.... ")
        # TODO Goal Life Cycle Management
        # execution_id = f"exec-ops-{uuid.uuid4().hex[:8]}-{uuid.uuid4().hex[:8]}"
        # self.execution_cache[execution_id] = "IN_PROGRESS"
        # print(f"🔐 Generated execution_id: {execution_id}")
        # exec_context = f"\nNote: Include this execution_id in tool calls: {execution_id}"

        prompt = {
            'role': 'user', 
            'content': f"""
                {self.goal.base_prompt} 
                Use the following information.
                {json.dumps([percept['data'] for percept in percepts])}.
                
            """
        }
        self.messages.append(prompt)
        user_index_flag = len(self.messages) - 1
        response_plain_text = ''
        compact_response_text = ""
        response_messages: List[Dict] = []
        print("Debug.... ")

        # Keep concise conversational memory for planning continuity.
        # When pruning is enabled we retain only user + assistant summaries,
        # while omitting raw tool messages to reduce token churn.
        # combined_messages = select_context_messages(
        #     self.messages,
        #     self.prune_intermediate_task_contexts,
        # )
        # combined_messages = inject_execution_id_context(combined_messages, exec_context)

        tmp = ""
        assistant_answer  = ""
        structured_messages: List[Dict] = []
        print("Debug.... ")
        print(self.messages)
        try:
            for response in self.run(messages=self.messages):
                tmp = typewriter_print(response, tmp)
                # Streaming output.
                # response_plain_text = typewriter_print(response, response_plain_text)
                # if self.prune_intermediate_task_contexts:
                #     compact_response_text = compact_assistant_chunk_text(
                #         response_plain_text,
                #         self.compact_chunk_max_chars,
                #     )
                # if isinstance(response, dict):
                #     response_messages.append(response)
                pass

            print("Debug.... ")
            assistant_answer = response[-1]['content'] # Most workflow agent answer are now in markdown format. 
            print(assistant_answer)

            structured_messages = response
        except Exception as e:
            assistant_answer = f"Error: {type(e)} {str(e)}"
            print("DEBUG", assistant_answer)


            # response_plain_text = f"Error: {str(e)}"
            # compact_response_text = compact_assistant_chunk_text(
            #     response_plain_text,
            #     self.compact_chunk_max_chars,
            # )
            # response_messages = [{"role": "assistant", "content": response_plain_text}]
            # self.execution_cache[execution_id] = "FAILED"

        # Determine whether this turn has verified tool-flow evidence.
        runtime_tool_evidence, unverified_function_calls = has_runtime_tool_evidence(structured_messages)
        if runtime_tool_evidence:
            print("All tool calls verified!")
        else:
            assistant_answer = f"Unverified Tool Calls Found!"
            print(assistant_answer)

        # Sanitize model-fabricated tool transcript tags only when no verified evidence exists.
        # response_plain_text = sanitize_faux_tool_transcript(
        #     response_plain_text,
        #     response_messages,
        #     has_verified_tool_evidence=has_verified_tool_evidence,
        # )

        # Mark SUCCESS only when runtime evidence exists and execution_id appears
        # in structured tool/runtime messages.
        # execution_id_present = tool_messages_contain_execution_id(response_messages, execution_id)
        # if has_verified_tool_evidence and execution_id_present:
        #     self.execution_cache[execution_id] = "SUCCESS"
        #     print(f"✅ Execution {execution_id} marked SUCCESS (verified tool event)")
        # else:
        #     self.execution_cache[execution_id] = "FAILED"
        #     print(f"❌ Execution {execution_id} marked FAILED (no verified tool event)")

        # # Verify execution_ids before adding to history (sanitization point)
        # verified_response, unverified_ids = verify_and_sanitize_execution_ids(
        #     response_plain_text,
        #     self.execution_cache,
        # )
        # if unverified_ids:
        #     print(f"⚠️  Unverified execution IDs: {unverified_ids}")
        # if verified_response != response_plain_text:
        #     print(f"⚠️  Filtered unverified execution IDs from response")
        #     response_plain_text = verified_response

        # Add assistant/tool responses to history
        # if response_messages:
        #     self.messages.extend(response_messages)
        # else:
        #     self.messages.append(
        #         {
        #             "role": "assistant",
        #             "content": response_plain_text,
        #         }
        #     )
        if structured_messages and runtime_tool_evidence:
            self.messages.extend(structured_messages[-1:])
        else:
            self.messages.append(
                {
                    "role": "assistant",
                    "content": assistant_answer,
                }
            )
        
        # Memory Pruning 
        # if self.prune_intermediate_task_contexts:
        #     print("Pruning intermediate memory. Keeping only user and task summary...")
        #     self.messages = prune_session_history(
        #         session_messages=self.messages,
        #         user_index_flag=user_index_flag,
        #         response_messages=response_messages,
        #         response_text=response_plain_text,
        #         compact_response_text=compact_response_text,
        #     )


if __name__ == "__main__":
    agent = QwenOpsAgent(
        goal = f"./personas/{PERSONA}/goal.yaml",
        sensors = f"./personas/{PERSONA}/sensors.yaml",
        llm_cfg = "./templates/llm/qwen.yaml",
        actuators = f"./personas/{PERSONA}/actuators.yaml",
        prune_intermediate_task_contexts = True
    )
    agent.launch()
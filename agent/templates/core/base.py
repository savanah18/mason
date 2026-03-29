import os
import yaml
import threading
from typing import Dict, Iterator, List, Literal, Optional, Union, Any

from transformers import AutoTokenizer
from qwen_agent.tools.mcp_manager import MCPManager

from .mcp_compat import apply_mcp_ping_compat_patch


class BaseAgent:
    def _initialize_llm_cfg(self, config_path):
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
        print(f"✓ Agent initialized with the following llm config.\n {llm_cfg}")
        return llm_cfg

    def _initialize_mcp_cfg(self, config_path):
        mcp_cfg = {}
        try:
            with open(config_path, "r") as f: 
                mcp_cfg = yaml.safe_load(f)["spec"]
        except Exception as e:
            pass
        print(f"✓ Qwen Agent initialized with the following mcp config.\n {mcp_cfg}")
        return mcp_cfg

    @staticmethod
    def _apply_mcp_ping_compat_patch():
        """Allow MCP servers that do not implement ping (legacy stdio servers)."""
        apply_mcp_ping_compat_patch()

    def _load_mcp_tools(self, mcpServers: Dict ={}, exclude_tools: List[Any] = [], timeout = None) -> List[Any]:
        """Load MCP tools with timeout."""
        print(mcpServers)
        timeout = timeout or int(os.getenv("MCP_INIT_TIMEOUT_SECONDS", "180"))
        mcp_tools = []
        mcp_config  = {
            "mcpServers" : mcpServers["mcp-servers"]
        }

        result = {"tools": [], "error": None}
        def _init():
            try:
                self._apply_mcp_ping_compat_patch()
                result["tools"] = MCPManager().initConfig(mcp_config)
                result["tools"] = [t for t in result["tools"] if t.name not in exclude_tools]
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
            print(f"MCP initialization issues encountered")
            return []

        print(f"✓ Qwen Agent initialized with {len(result["tools"])}")
        return result["tools"]

    # Metrics
    def compute_context_length(self, messages: List = []) -> int:
        tokenizer = AutoTokenizer.from_pretrained("/mnt/checkpoint")
        # print(f"Computing context length for  {messages}")
        total_tokens = sum(len(tokenizer.encode(msg["content"])) for msg in messages)
        return total_tokens
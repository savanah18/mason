import os
import threading
from typing import Dict, Iterator, List, Literal, Optional, Union, Any

from transformers import AutoTokenizer
from qwen_agent.tools.mcp_manager import MCPManager

#from .utils import apply_mcp_ping_compat_patch

def load_mcp_tools(mcpServers: Dict ={}, exclude_tools: List[Any] = [], timeout = None) -> List[Any]:
    """Load MCP tools with timeout."""
    timeout = timeout or int(os.getenv("MCP_INIT_TIMEOUT_SECONDS", "180"))
    mcp_tools = []
    mcp_config  = {
        "mcpServers" : mcpServers["mcp-servers"]
    }

    result = {"tools": [], "error": None}
    def _init():
        try:
            # self._apply_mcp_ping_compat_patch()
            result["tools"] = MCPManager().initConfig(mcp_config)
            result["tools"] = [t for t in result["tools"] if t.name not in exclude_tools]
            print(f"✓ Loaded {len(result['tools'])} MCP tools")
            print("Available tools:")
            for tool in result["tools"]:
                print(f"  - {tool.name}")
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

    print(f"✓ Qwen Agent initialized with {len(result['tools'])}")
    return result["tools"]


def build_actuators_from_config(actuator_config: Any) -> List[Any]:
    exclude_tools = actuator_config.get('exclude-tools', [])
    mcp_tools: List[Any] = load_mcp_tools(actuator_config, exclude_tools)
    function_tools: List[Any] = actuator_config.get('builtin-functions', [])
    return mcp_tools + function_tools
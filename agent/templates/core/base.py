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
                # llm_cfg["generate_cfg"]["temperature"] = 0.1 if os.getenv("AGENT_MODE","dev") == "eval" else llm_cfg["generate_cfg"].get("temperature", 0.8)
        except Exception as e:
            llm_cfg = {
                'model': 'Qwen3-4B-Instruct',
                'model_server': os.getenv('LLM_SERVER', 'http://localhost:8001/v1'),
                'generate_cfg': {
                    "temperature": 0.1 if os.getenv("AGENT_MODE","dev") == "eval" else 0.8,
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

        print(f"✓ Qwen Agent initialized with {len(result["tools"])}")
        return result["tools"]

    # Metrics
    def compute_total_tokens(self, messages: List = []) -> int:
        tokenizer = AutoTokenizer.from_pretrained("/mnt/checkpoint")
        # print(f"Computing context length for  {messages}")
        total_tokens = 0
        for msg in messages:
            # Count tokens from both thought and content fields
            if msg.get("thought"):
                total_tokens += len(tokenizer.encode(msg["thought"]))
            if msg.get("content"):
                total_tokens += len(tokenizer.encode(msg["content"]))
        # print("Total tokens:\t ", total_tokens)
        return total_tokens


def extract_think_tags(content: str) -> tuple[Optional[str], str]:
    """Extract think tags from assistant response content.
    
    Returns:
        (thought_text, cleaned_content) where thought_text is everything up to 
        and including </think>, and cleaned_content is everything after </think>.
        If no </think> found, returns (None, original_content).
    """
    if not content:
        return None, content
    
    think_end = content.find("</think>")
    if think_end == -1:
        return None, content
    
    thought = content[:think_end + len("</think>")].strip()
    final_answer = content[think_end + len("</think>"):].strip()
    
    return thought, final_answer


def parse_think_tags_from_responses(responses: List[Dict]) -> List[Dict]:
    """Parse think tags from all assistant responses and add thought field.
    
    Each response dict will gain a 'thought' field containing extracted reasoning,
    and the 'content' field will contain only the final answer.
    """
    parsed = []
    for resp in responses:
        resp_copy = resp.copy()
        if resp_copy.get("role") == "assistant" and resp_copy.get("content"):
            thought, cleaned_content = extract_think_tags(resp_copy["content"])
            resp_copy["thought"] = thought
            resp_copy["content"] = cleaned_content
        parsed.append(resp_copy)
    return parsed
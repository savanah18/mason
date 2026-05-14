from __future__ import annotations
import os
from qwen_agent.tools import mcp_manager as qwen_mcp_manager

DEFAULT_PERSONA = "chat"
DEFAULT_AGENT_MODE = "dev"

def get_persona():
    return os.getenv("PERSONA",DEFAULT_PERSONA)

def get_agent_mode():
    return os.getenv("AGENT_MODE",DEFAULT_AGENT_MODE)

def apply_mcp_ping_compat_patch() -> None:
    """Allow MCP servers that do not implement ping (legacy stdio servers)."""
    if getattr(qwen_mcp_manager.MCPClient, "_ping_compat_patched", False):
        return

    async def _execute_function_without_ping(self, tool_name, tool_args: dict):
        from mcp.types import TextResourceContents

        if tool_name == "list_resources":
            try:
                list_resources = await self.session.list_resources()
                if list_resources.resources:
                    return "\n\n".join(str(resource) for resource in list_resources.resources)
                return "No resources found"
            except Exception as e:
                return f"Error: {e}"

        if tool_name == "read_resource":
            try:
                uri = tool_args.get("uri")
                if not uri:
                    raise ValueError("URI is required for read_resource")
                read_resource = await self.session.read_resource(uri)
                texts = []
                for resource in read_resource.contents:
                    if isinstance(resource, TextResourceContents):
                        texts.append(resource.text)
                if texts:
                    return "\n\n".join(texts)
                return "Failed to read resource"
            except Exception as e:
                return f"Error: {e}"

        response = await self.session.call_tool(tool_name, tool_args)
        texts = []
        for content in response.content:
            if content.type == "text":
                texts.append(content.text)
        if texts:
            return "\n\n".join(texts)
        return "execute error"

    qwen_mcp_manager.MCPClient.execute_function = _execute_function_without_ping
    qwen_mcp_manager.MCPClient._ping_compat_patched = True
    print("✓ Applied MCP ping compatibility patch")

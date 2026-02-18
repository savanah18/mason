#!/usr/bin/env python3
"""
MCP Tool Discovery Agent - Python Implementation
Discovers and catalogs tools from kuberntest-mcp-server at localhost:8080
Uses persistent session to maintain MCP state across requests.
"""

import requests
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from colorama import Fore, Back, Style, init
from typing import Dict, List, Any, Optional
import re

# Initialize colorama for cross-platform colored output
init(autoreset=True)


class MCPToolDiscovery:
    """MCP Tool Discovery Agent using persistent session with Mcp-Session-Id header."""
    
    def __init__(self, base_url: str = "http://localhost:8080", timeout: int = 10):
        self.base_url = base_url
        self.timeout = timeout
        # Use session for connection persistence
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.session_id = None
        self.tools: List[Dict[str, Any]] = []
        
    def print_header(self):
        """Print formatted header."""
        print(f"\n{Fore.CYAN}{Style.BRIGHT}{'═' * 70}")
        print(f"   MCP Tool Discovery Agent")
        print(f"   Comprehensive Tool Enumeration & Analysis")
        print(f"{'═' * 70}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'═' * 70}{Style.RESET_ALL}\n")
    
    def health_check(self) -> bool:
        """Step 1: Health check."""
        print(f"{Fore.CYAN}{Style.BRIGHT}Step 1: Health Check{Style.RESET_ALL}")
        try:
            response = self.session.get(
                f"{self.base_url}/healthz",
                timeout=self.timeout
            )
            if response.status_code == 200:
                print(f"{Fore.GREEN}{Style.BRIGHT}✓{Style.RESET_ALL} {Fore.GREEN}Server is healthy{Style.RESET_ALL}")
                print()
                return True
            else:
                print(f"{Fore.RED}✗ Health check returned: {response.status_code}{Style.RESET_ALL}")
                return False
        except Exception as e:
            print(f"{Fore.RED}✗ Health check failed: {e}{Style.RESET_ALL}")
            return False
    
    def connect_mcp(self) -> bool:
        """Step 2: Connect to MCP server (session ID obtained from initialize)."""
        print(f"{Fore.CYAN}{Style.BRIGHT}Step 2: Connect to MCP Server{Style.RESET_ALL}")
        # Session ID will be set after initialize
        return True
    
    def send_message(self, method: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Send JSON-RPC message via POST /mcp and parse SSE response.
        Returns the result object from the response.
        Uses Mcp-Session-Id header to maintain server-side session state.
        """
        if params is None:
            params = {}
        
        request_body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        
        try:
            # Prepare headers with session ID if available
            headers = {
                "Content-Type": "application/json"
            }
            if self.session_id:
                headers["Mcp-Session-Id"] = self.session_id
            
            response = self.session.post(
                f"{self.base_url}/mcp",
                headers=headers,
                json=request_body,
                timeout=self.timeout
            )
            
            # Extract session ID from response header if not yet set
            if not self.session_id and "Mcp-Session-Id" in response.headers:
                self.session_id = response.headers["Mcp-Session-Id"]
            
            # Parse SSE format: "event: message\ndata: {json}"
            body = response.text
            
            for line in body.split('\n'):
                if line.startswith('data: '):
                    json_str = line[6:]  # Skip "data: "
                    json_response = json.loads(json_str)
                    
                    if "result" in json_response:
                        return json_response["result"]
                    elif "error" in json_response:
                        error = json_response["error"]
                        raise Exception(f"MCP error ({method}): {error}")
                    else:
                        raise Exception(f"Empty result in response ({method})")
            
            # Some messages may not return data (but this is OK)
            return {}
            
        except Exception as e:
            print(f"{Fore.RED}Error sending message ({method}): {e}{Style.RESET_ALL}")
            raise
    
    def initialize(self) -> bool:
        """Step 3: Initialize MCP session and capture session ID."""
        print(f"{Fore.CYAN}{Style.BRIGHT}Step 3: Initialize{Style.RESET_ALL}")
        try:
            result = self.send_message(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {
                        "name": "mcp-tool-discovery",
                        "version": "0.2.0"
                    }
                }
            )
            print(f"{Fore.GREEN}{Style.BRIGHT}✓{Style.RESET_ALL} {Fore.GREEN}Initialized{Style.RESET_ALL}")
            if self.session_id:
                print(f"{Fore.CYAN}Session: {self.session_id}{Style.RESET_ALL}")
            return True
        except Exception as e:
            print(f"{Fore.RED}✗ Initialization failed: {e}{Style.RESET_ALL}")
            return False
    
    def send_ready(self) -> bool:
        """Step 3b: Send ready to complete initialization."""
        print(f"{Fore.CYAN}{Style.BRIGHT}Step 3b: Send ready{Style.RESET_ALL}")
        try:
            self.send_message("initialized", {})
            print(f"{Fore.GREEN}{Style.BRIGHT}✓{Style.RESET_ALL} {Fore.GREEN}Ready{Style.RESET_ALL}")
            print()
            return True
        except Exception as e:
            print(f"{Fore.RED}✗ Ready failed: {e}{Style.RESET_ALL}")
            return False
    
    def discover_tools(self) -> bool:
        """Step 4: Discover available tools."""
        print(f"{Fore.BLUE}{'═' * 70}")
        print(f"{Style.BRIGHT}Tool Discovery{Style.RESET_ALL}{Fore.BLUE}")
        print(f"{'═' * 70}{Style.RESET_ALL}")
        
        try:
            result = self.send_message("tools/list", {})
            
            if "tools" in result:
                self.tools = result["tools"]
                print(f"{Style.BRIGHT}Total tools discovered: {Fore.GREEN}{len(self.tools)}{Style.RESET_ALL}")
                print()
                
                if self.tools:
                    self.display_tools_catalog()
                    self.export_tools_json()
                
                return True
            else:
                print(f"{Fore.YELLOW}No tools in response{Style.RESET_ALL}")
                return False
                
        except Exception as e:
            print(f"{Fore.RED}✗ Tool discovery failed: {e}{Style.RESET_ALL}")
            return False
    
    def display_tools_catalog(self):
        """Display tools in formatted table."""
        print(f"\n{Fore.BLACK}{'─' * 70}")
        print(f"{Fore.YELLOW}{Style.BRIGHT}🔧 Tool Catalog{Style.RESET_ALL}")
        print(f"{Fore.BLACK}{'─' * 70}{Style.RESET_ALL}")
        
        for idx, tool in enumerate(self.tools, 1):
            name = tool.get("name", "Unknown")
            description = tool.get("description", "No description")
            input_schema = tool.get("inputSchema", {})
            
            print(f"\n{Fore.GREEN}{Style.BRIGHT}[{idx}]{Style.RESET_ALL} {Fore.WHITE}{Style.BRIGHT}{name}{Style.RESET_ALL}")
            print(f"    {Fore.BLACK}{description}{Style.RESET_ALL}")
            
            if input_schema:
                self.display_schema(input_schema, indent_level=1)
        
        print(f"\n{Fore.BLACK}{'─' * 70}{Style.RESET_ALL}")
    
    def display_schema(self, schema: Dict[str, Any], indent_level: int = 0):
        """Display input schema in formatted way."""
        indent = "    " * indent_level
        
        if "type" in schema:
            print(f"{indent}{Fore.CYAN}Type: {schema['type']}{Style.RESET_ALL}")
        
        if "properties" in schema:
            properties = schema["properties"]
            required_fields = schema.get("required", [])
            
            print(f"{indent}{Fore.CYAN}Parameters:{Style.RESET_ALL}")
            
            for param_name, param_info in properties.items():
                is_required = param_name in required_fields
                req_marker = f"{Fore.RED}*required*{Style.RESET_ALL}" if is_required else f"{Fore.BLACK}optional{Style.RESET_ALL}"
                
                param_type = param_info.get("type", "unknown")
                print(f"{indent}  • {Fore.WHITE}{Style.BRIGHT}{param_name}{Style.RESET_ALL} ({req_marker})")
                print(f"{indent}    {Fore.CYAN}Type: {param_type}{Style.RESET_ALL}")
                
                if "description" in param_info:
                    print(f"{indent}    {Fore.BLACK}Description: {param_info['description']}{Style.RESET_ALL}")
                
                if "default" in param_info:
                    print(f"{indent}    {Fore.YELLOW}Default: {param_info['default']}{Style.RESET_ALL}")
                
                if "enum" in param_info:
                    print(f"{indent}    Allowed values: {param_info['enum']}")
    
    def export_tools_json(self):
        """Export tools to JSON file."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"tools_catalog_{timestamp}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(self.tools, f, indent=2)
            
            print(f"\n{Fore.GREEN}{Style.BRIGHT}📁{Style.RESET_ALL} Exported tool catalog to: {Fore.GREEN}{filename}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Failed to export tools: {e}{Style.RESET_ALL}")
    
    def run(self) -> bool:
        """Run the complete discovery workflow."""
        self.print_header()
        
        try:
            # Step 1: Health check
            if not self.health_check():
                return False
            
            # Step 2: Connect
            if not self.connect_mcp():
                return False
            
            # Step 3: Initialize (captures session ID)
            if not self.initialize():
                return False
            
            print()
            
            # Step 4: Discover tools (no "initialized" needed)
            if not self.discover_tools():
                return False
            
            # Success
            print(f"\n{Fore.GREEN}{Style.BRIGHT}✓ Discovery complete!{Style.RESET_ALL}\n")
            return True
            
        except Exception as e:
            print(f"\n{Fore.RED}{Style.BRIGHT}✗ Discovery failed: {e}{Style.RESET_ALL}\n")
            return False


def main():
    """Main entry point."""
    agent = MCPToolDiscovery()
    success = agent.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

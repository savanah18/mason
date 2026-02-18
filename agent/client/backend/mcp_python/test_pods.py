#!/usr/bin/env python3
"""
MCP Tool Test: Get All Pods in All Namespaces
Tests the pods_list tool via the MCP server to retrieve and display pods.
"""

import requests
import json
import sys
from datetime import datetime, timezone
from colorama import Fore, Style, init
from typing import Dict, List, Any, Optional

# Initialize colorama for cross-platform colored output
init(autoreset=True)


class MCPToolTest:
    """Test tool invocation via MCP server."""
    
    def __init__(self, base_url: str = "http://localhost:8080", timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.session_id = None
        
    def print_header(self):
        """Print formatted header."""
        print(f"\n{Fore.CYAN}{Style.BRIGHT}{'═' * 70}")
        print(f"   MCP Tool Test: List All Pods")
        print(f"{'═' * 70}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'═' * 70}{Style.RESET_ALL}\n")
    
    def health_check(self) -> bool:
        """Verify server is running."""
        try:
            response = self.session.get(f"{self.base_url}/healthz", timeout=self.timeout)
            return response.status_code == 200
        except Exception:
            return False
    
    def send_message(self, method: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Send MCP message and parse response."""
        if params is None:
            params = {}
        
        request_body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        
        try:
            headers = {"Content-Type": "application/json"}
            if self.session_id:
                headers["Mcp-Session-Id"] = self.session_id
            
            response = self.session.post(
                f"{self.base_url}/mcp",
                headers=headers,
                json=request_body,
                timeout=self.timeout
            )
            
            # Capture session ID from response
            if not self.session_id and "Mcp-Session-Id" in response.headers:
                self.session_id = response.headers["Mcp-Session-Id"]
            
            # Parse SSE response
            for line in response.text.split('\n'):
                if line.startswith('data: '):
                    json_str = line[6:]
                    json_response = json.loads(json_str)
                    
                    if "result" in json_response:
                        return json_response["result"]
                    elif "error" in json_response:
                        error = json_response["error"]
                        raise Exception(f"MCP error: {error.get('message', 'Unknown error')}")
            
            return {}
            
        except Exception as e:
            print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
            raise
    
    def initialize(self) -> bool:
        """Initialize MCP session."""
        try:
            self.send_message(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {
                        "name": "mcp-test-pods",
                        "version": "1.0.0"
                    }
                }
            )
            return True
        except Exception:
            return False
    
    def list_all_pods(self) -> bool:
        """Call pods_list tool to get all pods from all namespaces."""
        print(f"{Fore.CYAN}{Style.BRIGHT}Fetching all pods from all namespaces...{Style.RESET_ALL}")
        
        try:
            # Call pods_list with no namespace filter to get all namespaces
            result = self.send_message(
                "tools/call",
                {
                    "name": "pods_list",
                    "arguments": {}  # No namespace specified = all namespaces
                }
            )
            
            # Parse the result
            if "content" in result and len(result["content"]) > 0:
                content = result["content"][0]
                if "text" in content:
                    pods_text = content["text"]
                    self.display_pods(pods_text)
                    return True
                else:
                    print(f"{Fore.YELLOW}No text content in response{Style.RESET_ALL}")
                    return False
            else:
                print(f"{Fore.YELLOW}No content in response{Style.RESET_ALL}")
                return False
            
        except Exception as e:
            print(f"{Fore.RED}✗ Failed to list pods: {e}{Style.RESET_ALL}")
            return False
    
    def display_pods(self, pods_text: str):
        """Display pods output from kubectl-style text."""
        print(f"\n{Fore.BLACK}{'─' * 150}")
        print(f"{Fore.YELLOW}{Style.BRIGHT}📦 Kubernetes Pods (All Namespaces){Style.RESET_ALL}")
        print(f"{Fore.BLACK}{'─' * 150}{Style.RESET_ALL}\n")
        
        # Split into lines
        lines = pods_text.strip().split('\n')
        
        if not lines:
            print(f"{Fore.YELLOW}No pods found{Style.RESET_ALL}")
            return False
        
        # Display header (first line)
        print(f"{Fore.CYAN}{Style.BRIGHT}{lines[0]}{Style.RESET_ALL}")
        
        # Display each pod row with color coding
        pod_count = 0
        for line in lines[1:]:
            if not line.strip():
                continue
            
            # Color code based on status
            if "Running" in line:
                print(f"{Fore.GREEN}{line}{Style.RESET_ALL}")
            elif "Pending" in line or "ContainerCreating" in line:
                print(f"{Fore.YELLOW}{line}{Style.RESET_ALL}")
            elif "Failed" in line or "CrashLoopBackOff" in line or "Error" in line:
                print(f"{Fore.RED}{line}{Style.RESET_ALL}")
            else:
                print(line)
            
            pod_count += 1
        
        print(f"\n{Fore.BLACK}{'─' * 150}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{Style.BRIGHT}Total: {pod_count} pod(s){Style.RESET_ALL}\n")
        return True
    
    def calculate_age(self, timestamp: str) -> str:
        """Calculate age from timestamp."""
        if not timestamp:
            return "N/A"
        try:
            # Parse ISO timestamp
            created = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = now - created
            
            seconds = int(diff.total_seconds())
            if seconds < 60:
                return f"{seconds}s"
            elif seconds < 3600:
                return f"{seconds // 60}m"
            elif seconds < 86400:
                return f"{seconds // 3600}h"
            else:
                return f"{seconds // 86400}d"
        except Exception:
            return "N/A"
    
    def run(self) -> bool:
        """Run the test."""
        self.print_header()
        
        # Check health
        print(f"{Fore.CYAN}{Style.BRIGHT}Step 1: Health Check{Style.RESET_ALL}")
        if not self.health_check():
            print(f"{Fore.RED}✗ Server is not responding{Style.RESET_ALL}")
            return False
        print(f"{Fore.GREEN}{Style.BRIGHT}✓{Style.RESET_ALL} {Fore.GREEN}Server is healthy{Style.RESET_ALL}\n")
        
        # Initialize
        print(f"{Fore.CYAN}{Style.BRIGHT}Step 2: Initialize MCP{Style.RESET_ALL}")
        if not self.initialize():
            print(f"{Fore.RED}✗ Failed to initialize{Style.RESET_ALL}")
            return False
        print(f"{Fore.GREEN}{Style.BRIGHT}✓{Style.RESET_ALL} {Fore.GREEN}Initialized{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Session: {self.session_id}{Style.RESET_ALL}\n")
        
        # List pods
        print(f"{Fore.CYAN}{Style.BRIGHT}Step 3: List Pods{Style.RESET_ALL}")
        return self.list_all_pods()


def main():
    """Main entry point."""
    tester = MCPToolTest()
    success = tester.run()
    
    if success:
        print(f"{Fore.GREEN}{Style.BRIGHT}✓ Test completed successfully!{Style.RESET_ALL}\n")
        sys.exit(0)
    else:
        print(f"{Fore.RED}{Style.BRIGHT}✗ Test failed{Style.RESET_ALL}\n")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted{Style.RESET_ALL}")
        sys.exit(1)

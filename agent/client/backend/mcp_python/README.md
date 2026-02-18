# MCP Tool Discovery Agent - Python Implementation

A Python-based MCP (Model Context Protocol) client for discovering and cataloging Kubernetes tools from `kuberntest-mcp-server`.

## Overview

This agent discovers all available MCP tools from the kuberntest-mcp-server running at `localhost:8080`, parses their schemas, and exports them to a structured JSON catalog for further analysis and integration with LLM agents.

## Key Discovery

The MCP server uses **HTTP POST with SSE responses** and maintains session state via the `Mcp-Session-Id` header (not traditional HTTP sessions). This is the critical protocol detail that enables stateful tool discovery over HTTP.

**Protocol Flow:**
1. POST `/mcp` with initialize request → Returns `Mcp-Session-Id` header
2. POST `/mcp` with tools/list request + `Mcp-Session-Id` header → Lists all available tools

## Discovered Tools (22 Total)

Kubernetes management tools across multiple categories:

### Configuration
- `configuration_view` - View kubeconfig YAML

### Events & Logs  
- `events_list` - List cluster events
- `nodes_log` - Get node logs

### Resource Management
- `pods_get`, `pods_list`, `pods_delete`, `pods_exec` - Pod operations
- `deployments_get`, `deployments_list` - Deployment operations
- `services_get`, `services_list` - Service operations
- `resources_get`, `resources_list`, `resources_scale` - Generic resources

### Helm
- `helm_install`, `helm_list`, `helm_uninstall` - Helm chart management

### Monitoring
- `nodes_top`, `nodes_stats_summary` - Node resource metrics
- `pods_top` - Pod resource metrics

### Namespaces
- `namespaces_list` - List all namespaces

## Installation

```bash
pip install -r requirements.txt
```

### Requirements
- `requests>=2.31.0` - HTTP client with session support
- `colorama>=0.4.6` - Cross-platform colored terminal output
- `rich>=13.7.0` - Rich text rendering (optional, imported but not strictly required)
- `python-dateutil>=2.8.2` - Date handling utilities

## Usage

### Basic Discovery

```bash
python mcp_client.py
```

This runs the complete tool discovery workflow:
1. Health check to verify server connectivity
2. Initialize MCP session and capture `Mcp-Session-Id`
3. List all available tools
4. Display formatted tool catalog in terminal
5. Export tool catalog to JSON file: `tools_catalog_YYYYMMDD_HHMMSS.json`

### Output

**Terminal Output:**
- Formatted table of all discovered tools
- Tool names, descriptions, and input parameters
- Parameter types, required flags, and defaults
- Rich colored output for readability

**JSON Export:**
- Structured JSON with complete tool metadata
- Includes annotations (destructive hints, read-only flags)
- Full input schemas for LLM tool calling
- Timestamped filenames for version tracking

Example tool entry:
```json
{
  "name": "pods_get",
  "title": "Pods: Get",
  "description": "Get a Kubernetes Pod in the current or provided namespace with the provided name",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": {
        "type": "string",
        "description": "Name of the Pod to get"
      },
      "namespace": {
        "type": "string",
        "description": "Optional Namespace to retrieve the Pod from"
      }
    },
    "required": ["name"]
  },
  "annotations": {
    "readOnlyHint": true,
    "openWorldHint": true
  }
}
```

## Implementation Details

### Session Management

The key insight for HTTP-based MCP is the `Mcp-Session-Id` header:

```python
# Step 1: Get session ID
resp = session.post("/mcp", json={"method": "initialize", ...})
session_id = resp.headers["Mcp-Session-Id"]

# Step 2: Use session ID in subsequent requests
headers = {"Mcp-Session-Id": session_id}
resp = session.post("/mcp", headers=headers, json={"method": "tools/list", ...})
```

### Response Parsing

The server returns SSE (Server-Sent Events) formatted responses:

```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{...}}
```

Parser extracts JSON from `data:` lines:

```python
for line in response.split('\n'):
    if line.startswith('data: '):
        json_response = json.loads(line[6:])
```

### Colored Output

Uses `colorama` for cross-platform terminal colors:
- Green: Success indicators (✓)
- Blue: Section headers
- Yellow: Warnings and important info
- Red: Errors
- Black: Descriptions and details

## Architecture

```
mcp_client.py
├── MCPToolDiscovery class
│   ├── health_check() - Verify server availability
│   ├── connect_mcp() - Initialize connection
│   ├── initialize() - Establish MCP session
│   ├── discover_tools() - List and parse tools
│   ├── send_message() - Core MCP communication with session tracking
│   ├── display_tools_catalog() - Format output
│   └── export_tools_json() - Write catalog to file
├── run() - Main workflow orchestration
└── main() - Entry point
```

## Error Handling

- Health check failures with detailed error messages
- Graceful handling of missing session IDs
- JSON parsing errors with context
- File I/O errors for exports

## Future Enhancements

1. **Tool Invocation** - Execute tools with parameters via MCP
2. **LLM Integration** - Pass tool catalog to Triton-hosted Qwen3-VL for analysis
3. **Caching** - Cache tool catalog to reduce discovery overhead
4. **Filtering** - Filter tools by category, capability, or destructiveness
5. **Metrics** - Collect server metrics and performance statistics
6. **Async Support** - AsyncIO implementation for concurrent tool operations

## Comparison with Rust Implementation

| Aspect | Rust (Archived) | Python |
|--------|---|---|
| HTTP State Management | ✗ Blocked | ✓ Mcp-Session-Id header |
| WebSocket Support | ✗ HTTP 400 | ✗ HTTP 400 |
| Implementation Complexity | High (async/tokio) | Low (requests session) |
| Discovery Success | ✗ Failed | ✓ 22 tools discovered |
| Execution Time | N/A | ~2 seconds |

## Troubleshooting

**Server not responding:**
- Verify kuberntest-mcp-server is running on `localhost:8080`
- Check health endpoint: `curl http://localhost:8080/healthz`

**Tool discovery failing:**
- Ensure session ID is being captured from initialize response
- Verify `Mcp-Session-Id` header is passed in subsequent requests
- Check server logs for protocol errors

**JSON export failing:**
- Verify write permissions in current directory
- Check disk space availability

## Protocol Reference

**MCP Server Info:**
- Version: v0.0.57
- Capabilities: tools, resources, prompts, logging
- Endpoint: `http://localhost:8080/mcp`
- Protocol Version: 2024-11-05

**Session Lifecycle:**
1. `POST /mcp` with initialize → Response includes `Mcp-Session-Id` header
2. `POST /mcp` with tools/list + header → Returns tool list
3. Session expires after inactivity (server-side timeout)

## License

Part of the newbie-app MCP integration project.

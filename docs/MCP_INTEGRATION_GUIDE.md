# MCP Kubernetes Tool Integration Guide

**Status:** ✅ ACTIVE | **Version:** 1.0 | **Date:** February 1, 2026

## Overview

The Model Context Protocol (MCP) enables LLM agents to autonomously manage Kubernetes clusters through discovered tools. This guide covers the complete integration architecture.

## Quick Start

### 1. Verify MCP Server Running
```bash
curl http://localhost:8080/healthz
# Expected: {"status": "healthy", "version": "v0.0.57"}
```

### 2. Run Tool Discovery (Python)
```bash
cd agent/client/mcp_python
python mcp_client.py
```

### 3. Run Tool Discovery (Rust)
```bash
cd agent/client/mcp
cargo run --release
```

## Available Tools (22 Total)

### Pod Management
- `pods_list` - List pods with filtering
- `pods_get` - Get pod details
- `pods_delete` - Delete pod
- `pods_exec` - Execute command in pod
- `pods_log` - Get pod logs
- `pods_run` - Run new pod
- `pods_top` - Pod resource usage

### Deployment & Scaling
- `resources_scale` - Scale deployments/statefulsets
- `resources_create_or_update` - Create/update K8s resources
- `resources_delete` - Delete K8s resources
- `resources_get` - Get resource details
- `resources_list` - List resources

### Cluster Monitoring
- `nodes_top` - Node resource usage
- `nodes_log` - Node system logs
- `nodes_stats_summary` - Detailed node stats
- `namespaces_list` - List namespaces
- `events_list` - List cluster events

### Helm Management
- `helm_install` - Install Helm chart
- `helm_list` - List Helm releases
- `helm_uninstall` - Uninstall Helm chart

### Configuration
- `configuration_view` - Get kubeconfig

## Architecture

### Component Stack

```
┌─────────────────────────────┐
│   LLM Agent (Qwen3-VL)      │  ← User Query + Tool Context
│   (Triton @ 8000)           │
└──────────────┬──────────────┘
               │ Tool Call (JSON)
               ▼
┌─────────────────────────────┐
│  MCP Tool Executor          │  ← Python/Rust Implementation
│  (Validates + Executes)     │
└──────────────┬──────────────┘
               │ MCP Protocol (HTTP + Session ID)
               ▼
┌─────────────────────────────┐
│ kuberntest-mcp-server:8080  │  ← kubectl wrapper + K8s API
└──────────────┬──────────────┘
               │ kubectl commands
               ▼
┌─────────────────────────────┐
│  Kubernetes Cluster         │
└─────────────────────────────┘
```

## MCP Protocol Details

### Session Management
The MCP server maintains session state via HTTP header:

```
1. Initialize Request
   POST /mcp
   Body: {jsonrpc: "2.0", method: "initialize", ...}
   Response Header: Mcp-Session-Id: ABC123...

2. Subsequent Requests
   POST /mcp
   Header: Mcp-Session-Id: ABC123...
   Body: {jsonrpc: "2.0", method: "tools/list", ...}
```

### Response Format
Server-Sent Events (SSE) with JSON-RPC:

```
event: message
data: {"jsonrpc": "2.0", "id": 1, "result": {...}}
```

### Tool Invocation
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "pods_list",
    "arguments": {
      "fieldSelector": "status.phase=Failed",
      "namespace": "production"
    }
  }
}
```

## LLM Agent Integration

### System Prompt Format
```
You are a Kubernetes operator with access to these tools:

Tool 1: pods_list
  Description: List Kubernetes pods
  Parameters:
    - fieldSelector: Filter by field (e.g., status.phase=Failed)
    - labelSelector: Filter by label (e.g., app=web)
    - namespace: Target namespace

Tool 2: pods_delete
  Description: Delete a pod
  Parameters:
    - name: Pod name (required)
    - namespace: Pod namespace (required)

[... 20 more tools ...]

When the user asks about Kubernetes management, use these tools to:
1. Gather information (pods_list, resources_list, nodes_top)
2. Perform actions (pods_delete, resources_scale, helm_install)
3. Verify results (pods_list again, resources_get)
```

### Example Workflow: "Restart failed pods"

```
User: "All production pods are failing. Please investigate and restart them."

Agent Step 1: Gather Information
├─ Call: pods_list(fieldSelector="status.phase=Failed", namespace="production")
└─ Result: Found 3 failed pods with reasons (CrashLoopBackOff, ImagePullBackOff)

Agent Step 2: Analyze Root Cause
├─ Call: pods_log(name="app-xyz", namespace="production", tail=50)
├─ Call: nodes_stats_summary(name="worker-1")
└─ Result: Image pull failure due to registry credentials

Agent Step 3: Execute Fix
├─ Call: pods_delete(name="app-xyz", namespace="production")
├─ Call: pods_delete(name="app-abc", namespace="production")
└─ Result: Pods deleted, Kubernetes will restart them

Agent Step 4: Verify
├─ Call: pods_list(fieldSelector="status.phase=Running", namespace="production")
└─ Result: All 3 pods now running

Agent Summary: "Successfully restarted 3 failed pods. All are now in Running state."
```

## Implementation Files

### Python MCP Client
**File:** `/agent/client/mcp_python/mcp_client.py`

```python
class MCPToolDiscovery:
    def __init__(self, base_url="http://localhost:8080"):
        self.session = requests.Session()
        self.session_id = None
        
    async def send_message(self, method, params):
        # Captures Mcp-Session-Id from response
        # Includes it in subsequent requests
        ...
```

### Rust MCP Client
**File:** `/agent/client/mcp/src/main.rs`

```rust
struct MCPDiscoveryAgent {
    session_id: Option<String>,
    client: reqwest::Client,
    ...
}

impl MCPDiscoveryAgent {
    async fn send_message(&mut self, method: &str, params: Value) -> Result<Value> {
        // Async/await with tokio
        // HTTP header management for session ID
        ...
    }
}
```

### Tool Invocation Test
**File:** `/agent/client/mcp_python/test_pods.py`

Demonstrates:
- Session initialization
- Tool call execution (pods_list)
- Response parsing (text-based kubectl output)
- Result formatting

## Integration Checklist

- [x] MCP server running at localhost:8080
- [x] Tool discovery working (22 tools)
- [x] Session ID mechanism verified
- [x] Python client implementation complete
- [x] Rust client implementation complete
- [x] Tool invocation tests passing
- [ ] LLM system prompt integration
- [ ] Multi-turn agent loop
- [ ] Error handling & recovery
- [ ] Production deployment

## Troubleshooting

### Session ID Not Captured
**Issue:** "Mcp-Session-Id header missing"
**Solution:** Ensure initialize is called first; check response headers

### Tool Not Found
**Issue:** "method invalid" error
**Solution:** Verify tool name matches exactly; run discovery to see available tools

### Parameter Validation Failed
**Issue:** "Invalid parameters"
**Solution:** Check parameter types and required fields in tool schema

## Next Steps

1. **Integrate with LLM Agent**
   - Update Qwen3-VL system prompt with tool catalog
   - Implement tool call parsing from LLM output

2. **Implement Multi-turn Loop**
   - Tool result → LLM feedback → Next action
   - Conversation memory and context

3. **Add Observability**
   - Log all tool calls and results
   - Metrics: success rate, execution time, resource usage

4. **Production Hardening**
   - Rate limiting on MCP calls
   - Tool call audit logging
   - RBAC integration with Kubernetes

## References

- [MCP Server:** kuberntest-mcp-server v0.0.57
- [Protocol:** MCP 2024-11-05
- [Python Client:** `/agent/client/mcp_python/`
- [Rust Client:** `/agent/client/mcp/`
- [Tool Catalog:** `tools_catalog_*.json`

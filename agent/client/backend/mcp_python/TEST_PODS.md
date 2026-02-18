# MCP Tool Test: Get All Pods

A test script that demonstrates **tool invocation** through the MCP server to retrieve Kubernetes pods from all namespaces.

## Overview

This test shows how to:
1. Connect to kuberntest-mcp-server
2. Initialize an MCP session
3. **Call a discovered tool** via `tools/call` method
4. Parse and display the results

## Usage

```bash
python test_pods.py
```

## Output

Displays all Kubernetes pods across all namespaces in a formatted table:

```
NAMESPACE               APIVERSION   KIND   NAME                                      READY   STATUS
envoy-gateway-system    v1           Pod    envoy-gateway-94db945c8-4fzlg             1/1     Running
kube-system             v1           Pod    coredns-7d764666f9-chvg6                  1/1     Running
kube-system             v1           Pod    etcd-desktop-ck48g9r                      1/1     Running
...

Total: 9 pod(s)
```

## Key Implementation

### Tool Invocation Protocol

```python
# Call a tool via MCP
result = send_message(
    "tools/call",  # Special MCP method for tool execution
    {
        "name": "pods_list",              # Tool name from discovery
        "arguments": {}                    # Tool parameters
    }
)
```

### Response Format

The server returns tool output as **text content** (kubectl-style table format):

```python
{
  "content": [
    {
      "type": "text",
      "text": "NAMESPACE  NAME  READY  STATUS\n..."
    }
  ]
}
```

## Features

- ✅ Color-coded status output (Green for Running, Yellow for Pending, Red for Failed)
- ✅ Session-based MCP communication with `Mcp-Session-Id` header
- ✅ Error handling and server health checks
- ✅ Formatted table display with pod information
- ✅ Cross-platform colored terminal output

## Advanced Usage

### Call tools with parameters

```python
# Example: List pods in specific namespace
result = send_message(
    "tools/call",
    {
        "name": "pods_list",
        "arguments": {
            "namespace": "kube-system"  # Filter by namespace
        }
    }
)
```

### Other available tools to test

All 22 discovered tools can be invoked the same way:
- `pods_get` - Get single pod details
- `pods_delete` - Delete a pod
- `pods_exec` - Execute command in pod
- `deployments_list` - List deployments
- `helm_list` - List Helm releases
- `nodes_top` - Get node metrics
- ... and 16 more

## Error Handling

The test handles:
- Server connectivity failures
- MCP initialization errors
- Tool invocation failures
- Response parsing errors

## Next Steps

1. **Extend to other tools** - Try calling different tools (deployments, services, etc.)
2. **Add filtering** - Use tool parameters to filter results
3. **Integration with Qwen** - Send tool outputs to Triton Qwen3-VL for analysis
4. **Automation** - Create monitoring loops that repeatedly call tools
5. **Tool chaining** - Call multiple tools in sequence based on results

## Troubleshooting

**"Server is not responding"**
- Verify kuberntest-mcp-server is running: `curl http://localhost:8080/healthz`

**"Tool invocation failed"**
- Check that the tool name matches exactly from discovery
- Verify parameters are in correct format
- Check MCP session ID is being captured properly

**"Parsing failed"**
- The response might be in a different format
- Check raw response with: `print(json.dumps(result, indent=2))`

## Related Files

- [mcp_client.py](mcp_client.py) - Tool discovery agent
- [README.md](README.md) - Protocol documentation
- [tools_catalog_*.json](tools_catalog_*.json) - Discovered tools list

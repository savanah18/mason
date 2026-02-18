use anyhow::Result;
use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use crate::models::{ToolSchema, ToolCall, ToolResult};

// MCP Protocol structures
#[derive(Debug, Serialize, Deserialize)]
struct JsonRpcRequest {
    jsonrpc: String,
    id: u32,
    method: String,
    params: serde_json::Value,
}

#[derive(Debug, Serialize, Deserialize)]
struct JsonRpcResponse {
    jsonrpc: String,
    id: Option<u32>,
    result: Option<serde_json::Value>,
    error: Option<serde_json::Value>,
}

/// Registry of available MCP tools discovered from the server
pub struct ToolRegistry {
    base_url: String,
    client: reqwest::Client,
    session_id: Option<String>,
    tools: HashMap<String, ToolSchema>,
}

impl ToolRegistry {
    /// Create a new tool registry and discover tools from MCP server
    pub async fn new(base_url: &str) -> Result<Self> {
        let mut registry = Self {
            base_url: base_url.to_string(),
            client: reqwest::Client::new(),
            session_id: None,
            tools: HashMap::new(),
        };
        
        // Initialize MCP session and discover tools
        if let Err(e) = registry.initialize().await {
            eprintln!("[ToolRegistry] Failed to initialize: {}", e);
        }
        if let Err(e) = registry.discover_tools().await {
            eprintln!("[ToolRegistry] Failed to discover tools: {}", e);
        }
        
        Ok(registry)
    }
    
    /// Initialize MCP session
    async fn initialize(&mut self) -> Result<()> {
        let params = serde_json::json!({
            "protocolVersion": "2024-11-05",
            "capabilities": { "tools": {} },
            "clientInfo": {
                "name": "mcp-agent",
                "version": "0.3.0"
            }
        });
        
        self.send_message("initialize", params).await?;
        Ok(())
    }
    
    /// Send a message via MCP protocol
    async fn send_message(&mut self, method: &str, params: serde_json::Value) -> Result<serde_json::Value> {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: 1,
            method: method.to_string(),
            params,
        };

        let mut req_builder = self.client
            .post(format!("{}/mcp", self.base_url))
            .header("Content-Type", "application/json")
            .json(&request);

        if let Some(session_id) = &self.session_id {
            req_builder = req_builder.header("Mcp-Session-Id", session_id.clone());
        }

        let response = req_builder
            .timeout(std::time::Duration::from_secs(10))
            .send()
            .await?;

        // Capture session ID
        if self.session_id.is_none() {
            if let Some(session_header) = response.headers().get("Mcp-Session-Id") {
                if let Ok(session_str) = session_header.to_str() {
                    self.session_id = Some(session_str.to_string());
                }
            }
        }

        let body = response.text().await?;

        // Parse SSE response
        for line in body.lines() {
            if line.starts_with("data: ") {
                let json_str = &line[6..];
                let json_response: JsonRpcResponse = serde_json::from_str(json_str)?;

                if let Some(result) = json_response.result {
                    return Ok(result);
                } else if let Some(error) = json_response.error {
                    return Err(anyhow::anyhow!("MCP error: {:?}", error));
                }
            }
        }

        Err(anyhow::anyhow!("No SSE data in response"))
    }
    
    /// Discover tools from the MCP server
    async fn discover_tools(&mut self) -> Result<()> {
        let result = self.send_message("tools/list", serde_json::json!({})).await?;

        if let Some(tools_array) = result.get("tools").and_then(|t| t.as_array()) {
            for tool_value in tools_array {
                if let Ok(tool) = serde_json::from_value::<ToolSchema>(tool_value.clone()) {
                    self.tools.insert(tool.name.clone(), tool);
                }
            }
            
            println!("[ToolRegistry] Discovered {} tools", self.tools.len());
        }
        
        Ok(())
    }
    
    /// Get all available tools
    pub fn get_tools(&self) -> Vec<&ToolSchema> {
        self.tools.values().collect()
    }
    
    /// Get a specific tool by name
    pub fn get_tool(&self, name: &str) -> Option<&ToolSchema> {
        self.tools.get(name)
    }
    
    /// Validate a tool call against the schema
    pub fn validate_tool_call(&self, tool_call: &ToolCall) -> Result<()> {
        let tool_schema = self.get_tool(&tool_call.tool_name)
            .ok_or_else(|| anyhow::anyhow!("Unknown tool: {}", tool_call.tool_name))?;
        
        tool_schema.validate_parameters(&tool_call.parameters)
            .map_err(|e| anyhow::anyhow!("Parameter validation failed: {}", e))
    }
    
    /// Reload tools from server
    pub async fn refresh(&mut self) -> Result<()> {
        self.tools.clear();
        self.discover_tools().await
    }
    
    /// Get the current session ID
    pub fn session_id(&self) -> Option<&str> {
        self.session_id.as_deref()
    }
}

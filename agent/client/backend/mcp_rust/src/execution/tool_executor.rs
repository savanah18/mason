use anyhow::Result;
use std::time::Instant;
use serde::{Deserialize, Serialize};
use crate::models::{ToolCall, ToolResult};

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

/// Executor for MCP tool calls
pub struct ToolExecutor {
    base_url: String,
    client: reqwest::Client,
    session_id: Option<String>,
}

impl ToolExecutor {
    /// Create a new tool executor
    pub fn new(base_url: &str) -> Self {
        Self {
            base_url: base_url.to_string(),
            client: reqwest::Client::new(),
            session_id: None,
        }
    }
    
    /// Set session ID for reusing MCP sessions
    pub fn set_session_id(&mut self, session_id: String) {
        self.session_id = Some(session_id);
    }
    
    /// Execute a tool call via MCP protocol
    pub async fn execute(&mut self, tool_call: &ToolCall) -> Result<ToolResult> {
        let start = Instant::now();
        
        let params = serde_json::json!({
            "name": tool_call.tool_name,
            "arguments": tool_call.parameters,
        });
        
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: 1,
            method: "tools/call".to_string(),
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
            .timeout(std::time::Duration::from_secs(30))
            .send()
            .await;
        
        let duration_ms = start.elapsed().as_millis() as u64;
        
        match response {
            Ok(resp) => {
                if self.session_id.is_none() {
                    if let Some(session_header) = resp.headers().get("Mcp-Session-Id") {
                        if let Ok(session_str) = session_header.to_str() {
                            self.session_id = Some(session_str.to_string());
                        }
                    }
                }
                
                let body = resp.text().await?;
                
                for line in body.lines() {
                    if line.starts_with("data: ") {
                        let json_str = &line[6..];
                        let json_response: JsonRpcResponse = serde_json::from_str(json_str)?;

                        if let Some(result) = json_response.result {
                            return Ok(ToolResult::success(result, duration_ms));
                        } else if let Some(error) = json_response.error {
                            return Ok(ToolResult::failure(
                                format!("MCP error: {:?}", error),
                                duration_ms,
                            ));
                        }
                    }
                }
                
                Ok(ToolResult::failure("No data in MCP response", duration_ms))
            }
            Err(e) => {
                Ok(ToolResult::failure(format!("Request failed: {}", e), duration_ms))
            }
        }
    }
    
    /// Simulate tool execution (dry-run mode)
    pub async fn simulate(&self, tool_call: &ToolCall) -> Result<ToolResult> {
        let start = Instant::now();
        
        println!("[DRY-RUN] Would execute: {} {:?}", 
            tool_call.tool_name, 
            tool_call.parameters
        );
        
        tokio::time::sleep(tokio::time::Duration::from_millis(50)).await;
        
        let duration_ms = start.elapsed().as_millis() as u64;
        
        Ok(ToolResult::success(
            serde_json::json!({
                "dry_run": true,
                "tool": tool_call.tool_name,
                "message": "Simulated - no real changes made",
                "params": tool_call.parameters,
            }),
            duration_ms,
        ))
    }
}

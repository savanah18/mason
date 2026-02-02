// NOTE: This binary will be deprecated in favor of the autonomous agent system.
//       Use `cargo run --bin autonomous-agent` for the new goal-driven approach.
//       This tool discovery binary is kept for backward compatibility.

use serde::{Deserialize, Serialize};
use colored::*;
use chrono::Utc;
use anyhow::{Context, Result};
use reqwest::Client;
use std::time::Duration;
use std::fs::File;
use std::io::Write;

// Tool schema structures
#[derive(Debug, Serialize, Deserialize, Clone)]
struct ToolInfo {
    name: String,
    description: Option<String>,
    #[serde(rename = "inputSchema")]
    input_schema: Option<serde_json::Value>,
}

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

struct MCPDiscoveryAgent {
    base_url: String,
    client: Client,
    session_id: Option<String>,
    tools: Vec<ToolInfo>,
}

impl MCPDiscoveryAgent {
    fn new(base_url: &str) -> Self {
        Self {
            base_url: base_url.to_string(),
            client: Client::new(),
            session_id: None,
            tools: Vec::new(),
        }
    }

    fn print_header(&self) {
        println!("\n{}", "═".repeat(70).cyan().bold());
        println!("   {}", "MCP Tool Discovery Agent".cyan().bold());
        println!("   {}", "Comprehensive Tool Enumeration & Analysis".cyan());
        println!("{}", "═".repeat(70).cyan().bold());
        println!("{} {}", "Time:".cyan(), Utc::now().format("%Y-%m-%d %H:%M:%S UTC").to_string().cyan());
        println!("{}\n", "═".repeat(70).cyan().bold());
    }

    async fn health_check(&self) -> Result<bool> {
        println!("{}", "Step 1: Health Check".cyan().bold());
        
        let response = self.client
            .get(format!("{}/healthz", self.base_url))
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .context("Health check failed")?;

        if response.status().is_success() {
            println!("{} {}", "✓".green().bold(), "Server is healthy".green());
            println!();
            Ok(true)
        } else {
            println!("{} Health check returned: {}", "✗".red().bold(), response.status());
            Ok(false)
        }
    }

    async fn connect_mcp(&self) -> Result<bool> {
        println!("{}", "Step 2: Connect to MCP Server".cyan().bold());
        println!("{} {}", "✓".green().bold(), "Ready to initialize".green());
        println!();
        Ok(true)
    }

    async fn send_message(&mut self, method: &str, params: serde_json::Value) -> Result<serde_json::Value> {
        let request = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: 1,
            method: method.to_string(),
            params,
        };

        let mut req_builder = self.client.post(format!("{}/mcp", self.base_url))
            .header("Content-Type", "application/json")
            .json(&request);

        // Add session ID header if available
        if let Some(session_id) = &self.session_id {
            req_builder = req_builder.header("Mcp-Session-Id", session_id.clone());
        }

        let response = req_builder
            .timeout(Duration::from_secs(10))
            .send()
            .await
            .context(format!("Failed to send message ({})", method))?;

        // Capture session ID from response header if not yet set
        if self.session_id.is_none() {
            if let Some(session_header) = response.headers().get("Mcp-Session-Id") {
                if let Ok(session_str) = session_header.to_str() {
                    self.session_id = Some(session_str.to_string());
                }
            }
        }

        // Read and parse SSE response
        let body = response.text().await
            .context(format!("Failed to read response ({})", method))?;

        // Parse SSE format: "event: message\ndata: {json}"
        for line in body.lines() {
            if line.starts_with("data: ") {
                let json_str = &line[6..]; // Skip "data: "
                let json_response: JsonRpcResponse = serde_json::from_str(json_str)
                    .context(format!("Failed to parse JSON from SSE ({})", method))?;

                if let Some(result) = json_response.result {
                    return Ok(result);
                } else if let Some(error) = json_response.error {
                    return Err(anyhow::anyhow!("MCP error ({}): {:?}", method, error));
                }
            }
        }

        Err(anyhow::anyhow!("No SSE data in response ({})", method))
    }

    async fn initialize(&mut self) -> Result<bool> {
        println!("{}", "Step 3: Initialize".cyan().bold());
        
        let params = serde_json::json!({
            "protocolVersion": "2024-11-05",
            "capabilities": { "tools": {} },
            "clientInfo": {
                "name": "mcp-tool-discovery",
                "version": "0.3.0"
            }
        });

        self.send_message("initialize", params).await?;
        
        println!("{} {}", "✓".green().bold(), "Initialized".green());
        if let Some(session_id) = &self.session_id {
            println!("{} {}", "Session:".cyan(), session_id.cyan());
        }
        println!();
        
        Ok(true)
    }

    async fn discover_tools(&mut self) -> Result<bool> {
        println!("{}", "═".repeat(70).blue());
        println!("{}", "Tool Discovery".blue().bold());
        println!("{}\n", "═".repeat(70).blue());

        let result = self.send_message("tools/list", serde_json::json!({})).await?;

        if let Some(tools_array) = result.get("tools").and_then(|t| t.as_array()) {
            self.tools = tools_array
                .iter()
                .filter_map(|t| serde_json::from_value(t.clone()).ok())
                .collect();

            println!("{} {}",
                "Total tools discovered:".bold(),
                self.tools.len().to_string().green().bold()
            );
            println!();

            if !self.tools.is_empty() {
                self.display_tools_catalog();
                self.export_tools_json()?;
            }

            Ok(true)
        } else {
            println!("{}", "No tools in response".yellow());
            Ok(false)
        }
    }

    fn display_tools_catalog(&self) {
        println!("\n{}", "─".repeat(70).bright_black());
        println!("{}", "🔧 Tool Catalog".bright_yellow().bold());
        println!("{}\n", "─".repeat(70).bright_black());

        for (idx, tool) in self.tools.iter().enumerate() {
            println!(
                "{} {}",
                format!("[{}]", idx + 1).green().bold(),
                tool.name.bold().bright_white()
            );

            if let Some(desc) = &tool.description {
                println!("    {}", desc.bright_black());
            }

            if let Some(schema) = &tool.input_schema {
                self.display_schema(schema, 1);
            }

            println!();
        }

        println!("{}", "─".repeat(70).bright_black());
    }

    fn display_schema(&self, schema: &serde_json::Value, indent_level: usize) {
        let indent = "    ".repeat(indent_level);

        if let Some(schema_type) = schema.get("type").and_then(|v| v.as_str()) {
            println!("{}Type: {}", indent, schema_type.cyan());
        }

        if let Some(properties) = schema.get("properties").and_then(|v| v.as_object()) {
            println!("{}Parameters:", indent.cyan());

            let required_fields: Vec<String> = schema
                .get("required")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(String::from))
                        .collect()
                })
                .unwrap_or_default();

            for (name, prop) in properties {
                let is_required = required_fields.contains(name);
                let req_marker = if is_required {
                    "*required*".red()
                } else {
                    "optional".bright_black()
                };

                println!(
                    "{}  • {} ({})",
                    indent,
                    name.bold().bright_white(),
                    req_marker
                );

                if let Some(prop_obj) = prop.as_object() {
                    if let Some(prop_type) = prop_obj.get("type").and_then(|v| v.as_str()) {
                        println!("{}    Type: {}", indent, prop_type.cyan());
                    }

                    if let Some(desc) = prop_obj.get("description").and_then(|v| v.as_str()) {
                        println!("{}    Description: {}", indent, desc.bright_black());
                    }

                    if let Some(default) = prop_obj.get("default") {
                        println!("{}    Default: {}", indent, default.to_string().yellow());
                    }

                    if let Some(enum_vals) = prop_obj.get("enum").and_then(|v| v.as_array()) {
                        println!("{}    Allowed values: {:?}", indent, enum_vals);
                    }
                }
            }
        }
    }

    fn export_tools_json(&self) -> Result<()> {
        let filename = format!("tools_catalog_{}.json", Utc::now().format("%Y%m%d_%H%M%S"));

        let json = serde_json::to_string_pretty(&self.tools)?;
        let mut file = File::create(&filename)
            .context(format!("Failed to create file: {}", filename))?;
        file.write_all(json.as_bytes())
            .context(format!("Failed to write to file: {}", filename))?;

        println!(
            "\n{} {}",
            "📁".bold(),
            format!("Exported tool catalog to: {}", filename).green()
        );

        Ok(())
    }

    async fn run(&mut self) -> Result<bool> {
        self.print_header();

        if !self.health_check().await? {
            return Ok(false);
        }

        if !self.connect_mcp().await? {
            return Ok(false);
        }

        if !self.initialize().await? {
            return Ok(false);
        }

        if !self.discover_tools().await? {
            return Ok(false);
        }

        println!("\n{}", "✓ Discovery complete!".green().bold());
        println!();

        Ok(true)
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let mut agent = MCPDiscoveryAgent::new("http://localhost:8080");
    let success = agent.run().await?;

    std::process::exit(if success { 0 } else { 1 });
}
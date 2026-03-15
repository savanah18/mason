use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use std::collections::HashMap;

/// Tool schema from MCP discovery
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolSchema {
    /// Tool name (e.g., "pods_list")
    pub name: String,
    
    /// Human-readable description
    pub description: Option<String>,
    
    /// JSON schema for input parameters
    #[serde(rename = "inputSchema")]
    pub input_schema: Option<serde_json::Value>,
}

/// Represents a tool call to be executed
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    /// Tool name
    pub tool_name: String,
    
    /// Parameters for the tool
    pub parameters: HashMap<String, serde_json::Value>,
    
    /// When this tool call was created
    pub created_at: DateTime<Utc>,
    
    /// When this tool call started execution
    pub started_at: Option<DateTime<Utc>>,
    
    /// When this tool call completed
    pub completed_at: Option<DateTime<Utc>>,
    
    /// Result of the tool call
    pub result: Option<ToolResult>,
}

/// Result of a tool execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    /// Whether the tool executed successfully
    pub success: bool,
    
    /// Output data from the tool
    pub output: serde_json::Value,
    
    /// Error message if failed
    pub error: Option<String>,
    
    /// Duration in milliseconds
    pub duration_ms: u64,
    
    /// Metadata (HTTP status, etc.)
    pub metadata: Option<serde_json::Value>,
}

impl ToolCall {
    /// Create a new tool call
    pub fn new(tool_name: impl Into<String>, parameters: HashMap<String, serde_json::Value>) -> Self {
        Self {
            tool_name: tool_name.into(),
            parameters,
            created_at: Utc::now(),
            started_at: None,
            completed_at: None,
            result: None,
        }
    }
    
    /// Mark the tool call as started
    pub fn mark_started(&mut self) {
        self.started_at = Some(Utc::now());
    }
    
    /// Mark the tool call as completed with result
    pub fn mark_completed(&mut self, result: ToolResult) {
        self.completed_at = Some(Utc::now());
        self.result = Some(result);
    }
    
    /// Get duration in milliseconds (if completed)
    pub fn duration_ms(&self) -> Option<i64> {
        match (self.started_at, self.completed_at) {
            (Some(start), Some(end)) => Some((end - start).num_milliseconds()),
            _ => None,
        }
    }
    
    /// Check if the tool call succeeded
    pub fn is_success(&self) -> bool {
        self.result.as_ref().map_or(false, |r| r.success)
    }
}

impl ToolResult {
    /// Create a successful result
    pub fn success(output: serde_json::Value, duration_ms: u64) -> Self {
        Self {
            success: true,
            output,
            error: None,
            duration_ms,
            metadata: None,
        }
    }
    
    /// Create a failed result
    pub fn failure(error: impl Into<String>, duration_ms: u64) -> Self {
        Self {
            success: false,
            output: serde_json::Value::Null,
            error: Some(error.into()),
            duration_ms,
            metadata: None,
        }
    }
    
    /// Add metadata to the result
    pub fn with_metadata(mut self, metadata: serde_json::Value) -> Self {
        self.metadata = Some(metadata);
        self
    }
}

impl ToolSchema {
    /// Get required parameters from the schema
    pub fn required_parameters(&self) -> Vec<String> {
        self.input_schema
            .as_ref()
            .and_then(|schema| schema.get("required"))
            .and_then(|req| req.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default()
    }
    
    /// Get all parameter names from the schema
    pub fn all_parameters(&self) -> Vec<String> {
        self.input_schema
            .as_ref()
            .and_then(|schema| schema.get("properties"))
            .and_then(|props| props.as_object())
            .map(|obj| obj.keys().cloned().collect())
            .unwrap_or_default()
    }
    
    /// Validate parameters against the schema
    pub fn validate_parameters(&self, params: &HashMap<String, serde_json::Value>) -> Result<(), String> {
        // Check required parameters
        let required = self.required_parameters();
        for req_param in &required {
            if !params.contains_key(req_param) {
                return Err(format!("Missing required parameter: {}", req_param));
            }
        }
        
        // Check for unknown parameters
        let all_params = self.all_parameters();
        for param_name in params.keys() {
            if !all_params.contains(param_name) {
                return Err(format!("Unknown parameter: {}", param_name));
            }
        }
        
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_tool_call_creation() {
        let mut params = HashMap::new();
        params.insert("namespace".to_string(), serde_json::json!("default"));
        
        let tool_call = ToolCall::new("pods_list", params);
        assert_eq!(tool_call.tool_name, "pods_list");
        assert!(!tool_call.is_success());
    }
    
    #[test]
    fn test_tool_result() {
        let result = ToolResult::success(serde_json::json!({"status": "ok"}), 100);
        assert!(result.success);
        assert_eq!(result.duration_ms, 100);
    }
}

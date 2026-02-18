use anyhow::Result;
use std::collections::HashMap;
use crate::models::ToolCall;
use regex::Regex;

/// Parser for extracting tool calls from LLM output
pub struct ToolCallParser;

impl ToolCallParser {
    /// Parse tool calls from LLM-generated text
    pub fn parse(llm_output: &str) -> Result<Vec<ToolCall>> {
        let mut tool_calls = Vec::new();
        
        // Try to parse TOOL: format
        // Format: TOOL: tool_name(param1=value1, param2=value2)
        let tool_regex = Regex::new(r"TOOL:\s*(\w+)\((.*?)\)").unwrap();
        
        for caps in tool_regex.captures_iter(llm_output) {
            let tool_name = caps.get(1).unwrap().as_str().to_string();
            let params_str = caps.get(2).unwrap().as_str();
            
            let mut parameters = HashMap::new();
            
            // Parse parameters
            if !params_str.trim().is_empty() {
                for param_pair in params_str.split(',') {
                    let parts: Vec<&str> = param_pair.split('=').collect();
                    if parts.len() == 2 {
                        let key = parts[0].trim().to_string();
                        let value_str = parts[1].trim().trim_matches('"').trim_matches('\'');
                        
                        // Try to parse as JSON value
                        let value = if value_str == "true" {
                            serde_json::json!(true)
                        } else if value_str == "false" {
                            serde_json::json!(false)
                        } else if let Ok(num) = value_str.parse::<i64>() {
                            serde_json::json!(num)
                        } else if let Ok(num) = value_str.parse::<f64>() {
                            serde_json::json!(num)
                        } else {
                            serde_json::json!(value_str)
                        };
                        
                        parameters.insert(key, value);
                    }
                }
            }
            
            tool_calls.push(ToolCall::new(tool_name, parameters));
        }
        
        // Also try JSON format
        // Look for JSON objects with "tool" and "params" fields
        if let Ok(json_calls) = Self::parse_json_format(llm_output) {
            tool_calls.extend(json_calls);
        }
        
        Ok(tool_calls)
    }
    
    /// Parse tool calls from JSON format in the output
    fn parse_json_format(text: &str) -> Result<Vec<ToolCall>> {
        let mut tool_calls = Vec::new();
        
        // Find JSON objects in the text
        let json_regex = Regex::new(r#"\{[^{}]*"tool"[^{}]*\}"#).unwrap();
        
        for mat in json_regex.find_iter(text) {
            if let Ok(tool_call) = Self::parse_json(mat.as_str()) {
                tool_calls.push(tool_call);
            }
        }
        
        Ok(tool_calls)
    }
    
    /// Parse a single tool call from JSON
    pub fn parse_json(json_str: &str) -> Result<ToolCall> {
        let value: serde_json::Value = serde_json::from_str(json_str)?;
        
        let tool_name = value.get("tool")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing 'tool' field"))?;
        
        let params = value.get("params")
            .and_then(|v| v.as_object())
            .map(|obj| {
                obj.iter()
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect()
            })
            .unwrap_or_else(HashMap::new);
        
        Ok(ToolCall::new(tool_name, params))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_parse_tool_format() {
        let text = "I will call TOOL: pods_list(namespace=default)";
        let calls = ToolCallParser::parse(text).unwrap();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].tool_name, "pods_list");
    }
    
    #[test]
    fn test_parse_multiple_tools() {
        let text = "First TOOL: pods_list(namespace=default) then TOOL: pods_delete(name=test)";
        let calls = ToolCallParser::parse(text).unwrap();
        assert_eq!(calls.len(), 2);
    }
}

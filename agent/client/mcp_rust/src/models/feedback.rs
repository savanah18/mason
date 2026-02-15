use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};

/// Type of observation from the environment
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ObservationType {
    /// Tool execution result
    ToolResult,
    /// Cluster state change
    StateChange,
    /// Error or warning
    Error,
    /// LLM reasoning/decision
    LlmDecision,
    /// Context retrieval result
    ContextRetrieval,
}

/// Feedback from the environment or system
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Feedback {
    /// Type of feedback
    pub observation_type: ObservationType,
    
    /// Natural language description
    pub message: String,
    
    /// Structured data (JSON)
    pub data: Option<serde_json::Value>,
    
    /// When this feedback was created
    pub timestamp: DateTime<Utc>,
    
    /// Severity (0-100, higher = more important)
    #[serde(default)]
    pub severity: u8,
}

impl Feedback {
    /// Create new feedback
    pub fn new(observation_type: ObservationType, message: impl Into<String>) -> Self {
        Self {
            observation_type,
            message: message.into(),
            data: None,
            timestamp: Utc::now(),
            severity: 50,
        }
    }
    
    /// Create feedback with structured data
    pub fn with_data(
        observation_type: ObservationType,
        message: impl Into<String>,
        data: serde_json::Value,
    ) -> Self {
        Self {
            observation_type,
            message: message.into(),
            data: Some(data),
            timestamp: Utc::now(),
            severity: 50,
        }
    }
    
    /// Set severity level
    pub fn with_severity(mut self, severity: u8) -> Self {
        self.severity = severity;
        self
    }
    
    /// Create tool result feedback
    pub fn tool_result(tool_name: &str, success: bool, output: &str) -> Self {
        let message = if success {
            format!("Tool '{}' succeeded: {}", tool_name, output)
        } else {
            format!("Tool '{}' failed: {}", tool_name, output)
        };
        
        Self::new(ObservationType::ToolResult, message)
            .with_severity(if success { 30 } else { 70 })
    }
    
    /// Create error feedback
    pub fn error(message: impl Into<String>) -> Self {
        Self::new(ObservationType::Error, message).with_severity(80)
    }
    
    /// Create LLM decision feedback
    pub fn llm_decision(reasoning: impl Into<String>) -> Self {
        Self::new(ObservationType::LlmDecision, reasoning).with_severity(40)
    }
}

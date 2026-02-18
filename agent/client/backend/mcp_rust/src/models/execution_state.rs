use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use super::ToolCall;

/// Represents the execution state of a goal
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionState {
    /// Goal ID this state belongs to
    pub goal_id: String,
    
    /// Current iteration number (starts at 1)
    pub current_iteration: u32,
    
    /// History of all iterations
    pub iterations: Vec<Iteration>,
    
    /// Total number of tool calls made
    pub total_tool_calls: u32,
    
    /// Total number of successful tool calls
    pub successful_tool_calls: u32,
    
    /// Total number of failed tool calls
    pub failed_tool_calls: u32,
    
    /// Error log (for debugging)
    pub errors: Vec<ErrorRecord>,
    
    /// When this state was created
    pub created_at: DateTime<Utc>,
    
    /// When this state was last updated
    pub updated_at: DateTime<Utc>,
}

/// Represents a single iteration in the agent loop
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Iteration {
    /// Iteration number
    pub number: u32,
    
    /// When this iteration started
    pub started_at: DateTime<Utc>,
    
    /// When this iteration completed
    pub completed_at: Option<DateTime<Utc>>,
    
    /// Cluster context retrieved for this iteration
    pub context: Option<String>,
    
    /// LLM decision/reasoning for this iteration
    pub llm_decision: Option<String>,
    
    /// Tool calls made during this iteration
    pub tool_calls: Vec<ToolCall>,
    
    /// Observations/results from tool calls
    pub observations: Vec<String>,
    
    /// Whether this iteration succeeded
    pub success: bool,
    
    /// Error if iteration failed
    pub error: Option<String>,
}

/// Error record for tracking failures
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorRecord {
    /// When the error occurred
    pub timestamp: DateTime<Utc>,
    
    /// Iteration number where error occurred
    pub iteration: u32,
    
    /// Error message
    pub message: String,
    
    /// Error context (tool name, etc.)
    pub context: Option<String>,
}

impl ExecutionState {
    /// Create a new execution state for a goal
    pub fn new(goal_id: impl Into<String>) -> Self {
        let now = Utc::now();
        Self {
            goal_id: goal_id.into(),
            current_iteration: 0,
            iterations: Vec::new(),
            total_tool_calls: 0,
            successful_tool_calls: 0,
            failed_tool_calls: 0,
            errors: Vec::new(),
            created_at: now,
            updated_at: now,
        }
    }
    
    /// Start a new iteration
    pub fn start_iteration(&mut self) -> &mut Iteration {
        self.current_iteration += 1;
        let iteration = Iteration {
            number: self.current_iteration,
            started_at: Utc::now(),
            completed_at: None,
            context: None,
            llm_decision: None,
            tool_calls: Vec::new(),
            observations: Vec::new(),
            success: false,
            error: None,
        };
        self.iterations.push(iteration);
        self.updated_at = Utc::now();
        
        self.iterations.last_mut().unwrap()
    }
    
    /// Get the current iteration (mutable)
    pub fn current_iteration_mut(&mut self) -> Option<&mut Iteration> {
        self.iterations.last_mut()
    }
    
    /// Get the current iteration (immutable)
    pub fn current_iteration(&self) -> Option<&Iteration> {
        self.iterations.last()
    }
    
    /// Record a tool call
    pub fn record_tool_call(&mut self, tool_call: ToolCall) {
        self.total_tool_calls += 1;
        
        if tool_call.result.as_ref().map_or(false, |r| r.success) {
            self.successful_tool_calls += 1;
        } else {
            self.failed_tool_calls += 1;
        }
        
        if let Some(iteration) = self.current_iteration_mut() {
            iteration.tool_calls.push(tool_call);
        }
        
        self.updated_at = Utc::now();
    }
    
    /// Record an observation
    pub fn record_observation(&mut self, observation: impl Into<String>) {
        if let Some(iteration) = self.current_iteration_mut() {
            iteration.observations.push(observation.into());
        }
        self.updated_at = Utc::now();
    }
    
    /// Record an error
    pub fn record_error(&mut self, message: impl Into<String>, context: Option<String>) {
        let error = ErrorRecord {
            timestamp: Utc::now(),
            iteration: self.current_iteration,
            message: message.into(),
            context,
        };
        self.errors.push(error);
        self.updated_at = Utc::now();
    }
    
    /// Complete the current iteration
    pub fn complete_iteration(&mut self, success: bool, error: Option<String>) {
        if let Some(iteration) = self.current_iteration_mut() {
            iteration.completed_at = Some(Utc::now());
            iteration.success = success;
            iteration.error = error;
        }
        self.updated_at = Utc::now();
    }
    
    /// Get total execution time across all iterations
    pub fn total_execution_time_seconds(&self) -> i64 {
        self.iterations.iter()
            .filter_map(|i| i.completed_at.map(|end| (end - i.started_at).num_seconds()))
            .sum()
    }
    
    /// Get success rate of tool calls
    pub fn tool_call_success_rate(&self) -> f64 {
        if self.total_tool_calls == 0 {
            return 0.0;
        }
        (self.successful_tool_calls as f64) / (self.total_tool_calls as f64)
    }
}

impl Iteration {
    /// Get duration of this iteration in seconds
    pub fn duration_seconds(&self) -> Option<i64> {
        self.completed_at.map(|end| (end - self.started_at).num_seconds())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_execution_state_creation() {
        let state = ExecutionState::new("test-goal-id");
        assert_eq!(state.current_iteration, 0);
        assert_eq!(state.total_tool_calls, 0);
    }
    
    #[test]
    fn test_iteration_tracking() {
        let mut state = ExecutionState::new("test-goal-id");
        
        state.start_iteration();
        assert_eq!(state.current_iteration, 1);
        
        state.start_iteration();
        assert_eq!(state.current_iteration, 2);
        assert_eq!(state.iterations.len(), 2);
    }
}

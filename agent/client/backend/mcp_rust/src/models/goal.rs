use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use uuid::Uuid;

/// Goal status in the autonomous agent lifecycle
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum GoalStatus {
    /// Goal created but not yet started
    Pending,
    /// Goal is actively being executed
    Running,
    /// Goal completed successfully
    Completed,
    /// Goal execution failed
    Failed,
    /// Goal was cancelled by user
    Cancelled,
}

/// Represents a high-level goal for the autonomous agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Goal {
    /// Unique identifier
    pub id: String,
    
    /// Natural language description of the goal
    /// Example: "Restart all failed pods in production namespace"
    pub description: String,
    
    /// Current status
    pub status: GoalStatus,
    
    /// When the goal was created
    pub created_at: DateTime<Utc>,
    
    /// When the goal was last updated
    pub updated_at: DateTime<Utc>,
    
    /// When the goal completed (if applicable)
    pub completed_at: Option<DateTime<Utc>>,
    
    /// Maximum iterations before giving up
    #[serde(default = "default_max_iterations")]
    pub max_iterations: u32,
    
    /// Timeout in seconds for the entire goal execution
    #[serde(default = "default_timeout")]
    pub timeout_seconds: u64,
    
    /// If true, simulate tool execution without actually running them
    #[serde(default)]
    pub dry_run: bool,
    
    /// Optional success criteria (natural language)
    pub success_criteria: Option<String>,
    
    /// Optional constraints or requirements
    pub constraints: Option<serde_json::Value>,
    
    /// Result summary when goal completes
    pub result: Option<String>,
    
    /// Error message if goal failed
    pub error: Option<String>,
}

fn default_max_iterations() -> u32 {
    10
}

fn default_timeout() -> u64 {
    300 // 5 minutes
}

impl Goal {
    /// Create a new goal with default settings
    pub fn new(description: impl Into<String>) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4().to_string(),
            description: description.into(),
            status: GoalStatus::Pending,
            created_at: now,
            updated_at: now,
            completed_at: None,
            max_iterations: default_max_iterations(),
            timeout_seconds: default_timeout(),
            dry_run: false,
            success_criteria: None,
            constraints: None,
            result: None,
            error: None,
        }
    }
    
    /// Create a new goal with custom configuration
    pub fn with_config(
        description: impl Into<String>,
        max_iterations: u32,
        timeout_seconds: u64,
        dry_run: bool,
    ) -> Self {
        let mut goal = Self::new(description);
        goal.max_iterations = max_iterations;
        goal.timeout_seconds = timeout_seconds;
        goal.dry_run = dry_run;
        goal
    }
    
    /// Mark goal as running
    pub fn start(&mut self) {
        self.status = GoalStatus::Running;
        self.updated_at = Utc::now();
    }
    
    /// Mark goal as completed successfully
    pub fn complete(&mut self, result: impl Into<String>) {
        self.status = GoalStatus::Completed;
        self.result = Some(result.into());
        let now = Utc::now();
        self.completed_at = Some(now);
        self.updated_at = now;
    }
    
    /// Mark goal as failed
    pub fn fail(&mut self, error: impl Into<String>) {
        self.status = GoalStatus::Failed;
        self.error = Some(error.into());
        let now = Utc::now();
        self.completed_at = Some(now);
        self.updated_at = now;
    }
    
    /// Mark goal as cancelled
    pub fn cancel(&mut self) {
        self.status = GoalStatus::Cancelled;
        let now = Utc::now();
        self.completed_at = Some(now);
        self.updated_at = now;
    }
    
    /// Check if goal is in a terminal state
    pub fn is_terminal(&self) -> bool {
        matches!(
            self.status,
            GoalStatus::Completed | GoalStatus::Failed | GoalStatus::Cancelled
        )
    }
    
    /// Get elapsed time since creation
    pub fn elapsed_seconds(&self) -> i64 {
        (Utc::now() - self.created_at).num_seconds()
    }
    
    /// Check if goal has timed out
    pub fn is_timed_out(&self) -> bool {
        self.elapsed_seconds() > self.timeout_seconds as i64
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_goal_creation() {
        let goal = Goal::new("Test goal");
        assert_eq!(goal.status, GoalStatus::Pending);
        assert!(!goal.is_terminal());
        assert!(!goal.is_timed_out());
    }
    
    #[test]
    fn test_goal_lifecycle() {
        let mut goal = Goal::new("Test goal");
        
        goal.start();
        assert_eq!(goal.status, GoalStatus::Running);
        
        goal.complete("Success");
        assert_eq!(goal.status, GoalStatus::Completed);
        assert!(goal.is_terminal());
        assert!(goal.result.is_some());
    }
    
    #[test]
    fn test_goal_failure() {
        let mut goal = Goal::new("Test goal");
        goal.fail("Something went wrong");
        
        assert_eq!(goal.status, GoalStatus::Failed);
        assert!(goal.is_terminal());
        assert!(goal.error.is_some());
    }
}

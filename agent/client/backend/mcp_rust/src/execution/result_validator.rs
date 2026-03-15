use crate::models::ToolResult;

/// Validator for tool execution results
pub struct ResultValidator;

impl ResultValidator {
    /// Validate a tool result and suggest recovery strategies
    pub fn validate(result: &ToolResult) -> ValidationResult {
        if result.success {
            ValidationResult::Valid
        } else {
            // TODO: Implement intelligent validation logic - Feature 3.2
            ValidationResult::Failed {
                reason: result.error.clone().unwrap_or_else(|| "Unknown error".to_string()),
                retry_recommended: true,
            }
        }
    }
}

#[derive(Debug)]
pub enum ValidationResult {
    Valid,
    Failed {
        reason: String,
        retry_recommended: bool,
    },
}

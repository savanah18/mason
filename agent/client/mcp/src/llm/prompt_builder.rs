use crate::models::{Goal, ExecutionState, ToolSchema};

/// Builder for LLM prompts
pub struct PromptBuilder;

impl PromptBuilder {
    /// Create a new prompt builder
    pub fn new() -> Self {
        Self
    }
    
    /// Build a prompt for the LLM
    pub fn build_prompt(
        &self,
        goal: &Goal,
        context: &str,
        tools: &[&ToolSchema],
        state: &ExecutionState,
    ) -> String {
        let mut prompt = String::new();
        
        // System instruction
        prompt.push_str("You are a Kubernetes management agent.\n\n");
        
        // Goal
        prompt.push_str(&format!("GOAL: {}\n\n", goal.description));
        
        if let Some(criteria) = &goal.success_criteria {
            prompt.push_str(&format!("SUCCESS CRITERIA: {}\n\n", criteria));
        }
        
        // Current cluster state
        if !context.is_empty() {
            prompt.push_str(&format!("CLUSTER STATE:\n{}\n\n", context));
        }
        
        // Available tools
        prompt.push_str(&format!("AVAILABLE TOOLS ({} total):\n", tools.len()));
        for tool in tools {
            prompt.push_str(&format!("- {}", tool.name));
            if let Some(desc) = &tool.description {
                prompt.push_str(&format!(": {}", desc));
            }
            prompt.push_str("\n");
        }
        prompt.push_str("\n");
        
        // Execution history
        if state.current_iteration > 0 {
            prompt.push_str(&format!(
                "PROGRESS: Iteration {}/{} | Tool calls: {} ({}% success)\n\n",
                state.current_iteration,
                goal.max_iterations,
                state.total_tool_calls,
                (state.tool_call_success_rate() * 100.0) as u32,
            ));
            
            // Recent observations
            if let Some(last_iter) = state.iterations.last() {
                if !last_iter.observations.is_empty() {
                    prompt.push_str("RECENT OBSERVATIONS:\n");
                    for obs in &last_iter.observations {
                        prompt.push_str(&format!("- {}\n", obs));
                    }
                    prompt.push_str("\n");
                }
            }
        }
        
        // Instructions
        prompt.push_str("INSTRUCTIONS:\n");
        prompt.push_str("1. Analyze the current cluster state and goal\n");
        prompt.push_str("2. Decide which tool(s) to call (if any)\n");
        prompt.push_str("3. Format tool calls as: TOOL: tool_name(param1=value1, param2=value2)\n");
        prompt.push_str("4. If goal is complete, state 'GOAL COMPLETE' in your response\n\n");
        
        prompt.push_str("Your decision:\n");
        
        prompt
    }

    /// Build a prompt to select perception tools (read-only state gathering)
    pub fn build_perception_prompt(
        &self,
        goal: &Goal,
        tools: &[&ToolSchema],
        state: &ExecutionState,
    ) -> String {
        let mut prompt = String::new();

        prompt.push_str("You are selecting READ-ONLY tools to perceive Kubernetes state.\n");
        prompt.push_str("Do NOT choose tools that create, delete, or modify resources.\n\n");

        prompt.push_str(&format!("GOAL: {}\n\n", goal.description));

        prompt.push_str(&format!("PERCEPTION TOOL CANDIDATES ({} total):\n", tools.len()));
        for tool in tools {
            prompt.push_str(&format!("- {}", tool.name));
            if let Some(desc) = &tool.description {
                prompt.push_str(&format!(": {}", desc));
            }
            prompt.push_str("\n");
        }
        prompt.push_str("\n");

        if state.current_iteration > 0 {
            prompt.push_str(&format!(
                "PROGRESS: Iteration {}/{} | Tool calls: {} ({}% success)\n\n",
                state.current_iteration,
                goal.max_iterations,
                state.total_tool_calls,
                (state.tool_call_success_rate() * 100.0) as u32,
            ));
        }

        prompt.push_str("INSTRUCTIONS:\n");
        prompt.push_str("1. Choose the minimal set of read-only tools needed to observe current cluster state for this goal.\n");
        prompt.push_str("2. Format tool calls as: TOOL: tool_name(param1=value1, param2=value2)\n");
        prompt.push_str("3. If no tools are needed, respond with: NO TOOL CALLS\n\n");

        prompt.push_str("Your perception plan:\n");

        prompt
    }
}

impl Default for PromptBuilder {
    fn default() -> Self {
        Self::new()
    }
}

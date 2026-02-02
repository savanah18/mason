use anyhow::{Context, Result};
use colored::*;

use crate::models::{Goal, GoalStatus, ExecutionState, ToolSchema};
use crate::core::AgentConfig;
use crate::execution::{ToolExecutor, ToolRegistry};
use crate::storage::{GoalRepository, ObservationStore};
use crate::llm::{DecisionEngine, ContextRetriever, PromptBuilder};

/// Main agent that executes goals through perception-planning-action loops
pub struct AutonomousAgent {
    config: AgentConfig,
    tool_registry: ToolRegistry,
    tool_executor: ToolExecutor,
    decision_engine: DecisionEngine,
    context_retriever: ContextRetriever,
    prompt_builder: PromptBuilder,
    goal_repository: GoalRepository,
    observation_store: ObservationStore,
}

impl AutonomousAgent {
    /// Create a new agent
    pub async fn new(config: AgentConfig) -> Result<Self> {
        // Initialize components
        let tool_registry = ToolRegistry::new(&config.mcp_base_url).await?;
        let mut tool_executor = ToolExecutor::new(&config.mcp_base_url);
        
        // Share the session ID from registry to executor
        if let Some(session_id) = tool_registry.session_id() {
            tool_executor.set_session_id(session_id.to_string());
        }
        
        let decision_engine = DecisionEngine::new(&config.triton_url, &config);
        let context_retriever = ContextRetriever::new(&config.qdrant_url);
        let prompt_builder = PromptBuilder::new();
        let goal_repository = GoalRepository::new("./data/goals")?;
        let observation_store = ObservationStore::new(&config.qdrant_url);
        
        Ok(Self {
            config,
            tool_registry,
            tool_executor,
            decision_engine,
            context_retriever,
            prompt_builder,
            goal_repository,
            observation_store,
        })
    }
    
    /// Execute a goal
    pub async fn execute_goal(&mut self, mut goal: Goal) -> Result<Goal> {
        self.print_goal_header(&goal);
        
        // Initialize execution state
        let mut state = ExecutionState::new(&goal.id);
        
        // Mark goal as running
        goal.start();
        self.goal_repository.save(&goal)?;
        
        // Main agent loop: Perceive → Plan → Act → Observe
        while !self.should_stop(&goal, &state) {
            if self.config.verbose {
                println!("\n{} Iteration {}/{}", 
                    "→".cyan(), 
                    state.current_iteration + 1, 
                    goal.max_iterations
                );
            }
            
            // Start new iteration
            state.start_iteration();
            
            match self.execute_iteration(&mut goal, &mut state).await {
                Ok(should_continue) => {
                    state.complete_iteration(true, None);
                    
                    if !should_continue {
                        // Collect all tool results as the goal result
                        let results_summary = self.format_results_summary(&state);
                        goal.complete(&results_summary);
                        break;
                    }
                }
                Err(e) => {
                    let error_msg = format!("Iteration failed: {}", e);
                    state.complete_iteration(false, Some(error_msg.clone()));
                    state.record_error(&error_msg, None);
                    
                    // Check if we should retry or fail
                    if self.should_fail_goal(&state) {
                        goal.fail(&error_msg);
                        break;
                    }
                }
            }
        }
        
        // Check timeout
        if goal.is_timed_out() && !goal.is_terminal() {
            goal.fail("Goal timed out");
        }
        
        // Check max iterations
        if state.current_iteration >= goal.max_iterations && !goal.is_terminal() {
            goal.fail("Maximum iterations reached");
        }
        
        // Save final state
        self.goal_repository.save(&goal)?;
        self.save_execution_state(&goal.id, &state).await?;
        
        self.print_goal_summary(&goal, &state);
        
        Ok(goal)
    }
    
    /// Execute a single iteration of the agent loop
    async fn execute_iteration(&mut self, goal: &mut Goal, state: &mut ExecutionState) -> Result<bool> {
        // Step 1: PERCEIVE - Gather cluster context
        let context = self.perceive(goal, state).await
            .context("Failed to perceive environment")?;
        
        if let Some(iter) = state.current_iteration_mut() {
            iter.context = Some(context.clone());
        }
        
        // Step 2: PLAN - LLM decides what to do
        let decision = self.plan(goal, state, &context).await
            .context("Failed to plan action")?;
        
        if let Some(iter) = state.current_iteration_mut() {
            iter.llm_decision = Some(decision.reasoning.clone());
        }
        
        // Check if goal is complete
        if decision.goal_complete {
            if self.config.verbose {
                println!("{} Goal marked as complete", "✓".green().bold());
            }
            return Ok(false);
        }
        
        // Step 3: ACT - Execute tool calls
        if !decision.tool_calls.is_empty() {
            self.act(goal, state, decision.tool_calls).await
                .context("Failed to execute actions")?;
        }
        
        // Step 4: OBSERVE - Store results and check progress
        self.observe(goal, state).await
            .context("Failed to observe results")?;
        
        // Continue to next iteration
        Ok(true)
    }
    
    /// PERCEIVE: Gather relevant context from the environment
    async fn perceive(&mut self, goal: &Goal, state: &mut ExecutionState) -> Result<String> {
        if self.config.verbose {
            println!("  {} Perceiving cluster state...", "👁".bright_white());
        }

        let mut context_sections: Vec<String> = Vec::new();

        // Perception via MCP tools (LLM decides which tools to call)
        match self.perceive_with_tools(goal, state).await {
            Ok(tool_context) => {
                if !tool_context.trim().is_empty() {
                    context_sections.push(format!("TOOL-BASED PERCEPTION:\n{}", tool_context));
                }
            }
            Err(e) => {
                eprintln!("[Perceive] Tool-based perception failed: {}", e);
            }
        }

        // Supplementary retrieval-based context (best-effort)
        match self.context_retriever
            .retrieve_context(&goal.description, self.config.context_top_k)
            .await
        {
            Ok(retrieved) => {
                if !retrieved.trim().is_empty() {
                    if self.config.verbose {
                        println!("  {} Retrieved {} context chunks", "✓".green(), retrieved.len());
                    }
                    context_sections.push(format!("RETRIEVAL CONTEXT:\n{}", retrieved));
                }
            }
            Err(e) => {
                eprintln!("[Perceive] Retrieval context failed: {}", e);
            }
        }

        Ok(context_sections.join("\n\n"))
    }

    /// Use MCP tools to perceive environment state (LLM selects tools)
    async fn perceive_with_tools(&mut self, goal: &Goal, state: &mut ExecutionState) -> Result<String> {
        let tools = self.tool_registry.get_tools();
        let candidates = self.perception_candidates(&tools);

        if candidates.is_empty() {
            return Ok(String::new());
        }

        let prompt = self.prompt_builder.build_perception_prompt(goal, &candidates, state);
        if self.config.verbose {
            println!("\n{} Perception Prompt:\n{}\n", "🔎".bright_white(), prompt);
        }
        let decision = self.decision_engine.make_decision(&prompt).await?;

        if decision.tool_calls.is_empty() {
            return Ok(String::new());
        }

        let mut context = String::new();

        for mut tool_call in decision.tool_calls {
            if let Err(e) = self.tool_registry.validate_tool_call(&tool_call) {
                state.record_error(format!("Invalid perception tool call: {}", e), Some(tool_call.tool_name.clone()));
                continue;
            }

            let result = if goal.dry_run {
                self.tool_executor.simulate(&tool_call).await?
            } else {
                self.tool_executor.execute(&tool_call).await?
            };

            tool_call.mark_completed(result.clone());
            state.record_tool_call(tool_call.clone());

            context.push_str(&format!("Tool: {}\n", tool_call.tool_name));

            if !tool_call.parameters.is_empty() {
                if let Ok(params_str) = serde_json::to_string(&tool_call.parameters) {
                    context.push_str(&format!("Parameters: {}\n", params_str));
                }
            }

            if result.success {
                let output_str = serde_json::to_string_pretty(&result.output)
                    .unwrap_or_else(|_| format!("{:?}", result.output));
                context.push_str("Output:\n");
                for line in output_str.lines() {
                    context.push_str(&format!("  {}\n", line));
                }
            } else {
                context.push_str(&format!("Error: {}\n", result.error.as_deref().unwrap_or("Unknown error")));
            }

            context.push('\n');
        }

        Ok(context)
    }

    /// Filter tools likely to be safe for environment state retrieval
    fn perception_candidates<'a>(&self, tools: &'a [&ToolSchema]) -> Vec<&'a ToolSchema> {
        let read_keywords = ["list", "get", "describe", "status", "info", "read", "fetch"];
        let write_keywords = ["create", "delete", "apply", "update", "patch", "scale", "restart", "rollout"];

        tools
            .iter()
            .copied()
            .filter(|tool| {
                let name = tool.name.to_lowercase();
                let desc = tool.description.as_deref().unwrap_or("").to_lowercase();

                let is_write = write_keywords.iter().any(|k| name.contains(k) || desc.contains(k));
                let is_read = read_keywords.iter().any(|k| name.contains(k) || desc.contains(k));

                is_read && !is_write
            })
            .collect()
    }
    
    /// PLAN: Use LLM to decide next actions
    async fn plan(&mut self, goal: &Goal, state: &ExecutionState, context: &str) -> Result<Decision> {
        if self.config.verbose {
            println!("  {} Planning next action...", "🧠".bright_white());
        }
        
        // Build prompt with goal, context, tools, and history
        let prompt = self.prompt_builder.build_prompt(
            goal,
            context,
            &self.tool_registry.get_tools(),
            state,
        );
        if self.config.verbose {
            println!("\n{} Decision Prompt:\n{}\n", "🧠".bright_white(), prompt);
        }
        
        // Get decision from LLM
        let decision = self.decision_engine.make_decision(&prompt).await?;
        
        if self.config.verbose {
            let msg = if decision.goal_complete {
                "Goal complete".to_string()
            } else {
                format!("{} tool calls", decision.tool_calls.len())
            };
            println!("  {} LLM decided: {}", "✓".green(), msg);
        }
        
        Ok(decision)
    }
    
    /// ACT: Execute tool calls
    async fn act(&mut self, goal: &Goal, state: &mut ExecutionState, tool_calls: Vec<crate::models::ToolCall>) -> Result<()> {
        if self.config.verbose {
            println!("  {} Executing {} tool(s)...", "⚙".bright_white(), tool_calls.len());
        }
        
        for mut tool_call in tool_calls {
            // Validate tool call
            if let Err(e) = self.tool_registry.validate_tool_call(&tool_call) {
                state.record_error(format!("Invalid tool call: {}", e), Some(tool_call.tool_name.clone()));
                continue;
            }
            
            // Execute tool (or simulate if dry-run)
            let result = if goal.dry_run {
                self.tool_executor.simulate(&tool_call).await?
            } else {
                self.tool_executor.execute(&tool_call).await?
            };
            
            tool_call.mark_completed(result.clone());
            state.record_tool_call(tool_call.clone());
            
            if self.config.verbose {
                let status = if result.success { "✓".green() } else { "✗".red() };
                println!("    {} {} ({}ms)", status, tool_call.tool_name, result.duration_ms);
            }
        }
        
        Ok(())
    }
    
    /// OBSERVE: Store observations and check progress
    async fn observe(&mut self, goal: &Goal, state: &ExecutionState) -> Result<()> {
        if self.config.verbose {
            println!("  {} Recording observations...", "📝".bright_white());
        }
        
        // Store observations in Qdrant for future context
        if let Some(iteration) = state.current_iteration() {
            for tool_call in &iteration.tool_calls {
                if let Some(result) = &tool_call.result {
                    self.observation_store.store_observation(
                        &goal.id,
                        state.current_iteration,
                        &tool_call.tool_name,
                        result,
                    ).await?;
                }
            }
        }
        
        Ok(())
    }
    
    /// Format execution results into a summary
    fn format_results_summary(&self, state: &ExecutionState) -> String {
        let mut summary = String::new();
        
        for (i, iteration) in state.iterations.iter().enumerate() {
            summary.push_str(&format!("Iteration {}:\n", i + 1));
            
            for tool_call in &iteration.tool_calls {
                summary.push_str(&format!("  - {}: ", tool_call.tool_name));
                
                if let Some(result) = &tool_call.result {
                    if result.success {
                        summary.push_str(&format!("✓ {}\n", 
                            serde_json::to_string_pretty(&result.output).unwrap_or_else(|_| "Success".to_string())
                        ));
                    } else {
                        summary.push_str(&format!("✗ {}\n", result.error.as_deref().unwrap_or("Unknown error")));
                    }
                } else {
                    summary.push_str("No result\n");
                }
            }
        }
        
        summary
    }
    
    /// Check if agent should stop executing
    fn should_stop(&self, goal: &Goal, state: &ExecutionState) -> bool {
        goal.is_terminal() 
            || state.current_iteration >= goal.max_iterations
            || goal.is_timed_out()
    }
    
    /// Check if goal should be marked as failed
    fn should_fail_goal(&self, state: &ExecutionState) -> bool {
        // Fail if too many consecutive errors
        let recent_failures = state.iterations.iter()
            .rev()
            .take(3)
            .filter(|i| !i.success)
            .count();
        
        recent_failures >= 3
    }
    
    /// Save execution state to disk
    async fn save_execution_state(&self, goal_id: &str, state: &ExecutionState) -> Result<()> {
        let path = format!("./data/goals/{}/execution_state.json", goal_id);
        std::fs::create_dir_all(format!("./data/goals/{}", goal_id))?;
        
        let content = serde_json::to_string_pretty(state)?;
        std::fs::write(&path, content)?;
        
        Ok(())
    }
    
    // Display helpers
    
    fn print_goal_header(&self, goal: &Goal) {
        println!("\n{}", "═".repeat(70).cyan().bold());
        println!("  {}", "Agent - Goal Execution".cyan().bold());
        println!("{}", "═".repeat(70).cyan().bold());
        println!("{} {}", "Goal ID:".cyan(), goal.id.bright_white());
        println!("{} {}", "Description:".cyan(), goal.description.bright_white());
        println!("{} {}", "Max Iterations:".cyan(), goal.max_iterations);
        println!("{} {}s", "Timeout:".cyan(), goal.timeout_seconds);
        println!("{} {}", "Dry Run:".cyan(), if goal.dry_run { "Yes".yellow() } else { "No".green() });
        println!("{}\n", "═".repeat(70).cyan().bold());
    }
    
    fn print_goal_summary(&self, goal: &Goal, state: &ExecutionState) {
        println!("\n{}", "═".repeat(70).blue());
        println!("  {}", "Execution Summary".blue().bold());
        println!("{}", "═".repeat(70).blue());
        
        let status_color = match goal.status {
            GoalStatus::Completed => "✓ Completed".green().bold(),
            GoalStatus::Failed => "✗ Failed".red().bold(),
            GoalStatus::Cancelled => "⊘ Cancelled".yellow().bold(),
            _ => "...".white(),
        };
        
        println!("{} {}", "Status:".bold(), status_color);
        println!("{} {}", "Iterations:".bold(), state.current_iteration);
        println!("{} {}", "Tool Calls:".bold(), state.total_tool_calls);
        println!("{} {:.1}%", "Success Rate:".bold(), state.tool_call_success_rate() * 100.0);
        println!("{} {}s", "Total Time:".bold(), state.total_execution_time_seconds());
        
        if let Some(result) = &goal.result {
            println!("{} {}", "Result:".green().bold(), result);
        }
        
        if let Some(error) = &goal.error {
            println!("{} {}", "Error:".red().bold(), error);
        }
        
        println!("{}\n", "═".repeat(70).blue());
    }
}

/// Decision from the LLM
pub struct Decision {
    /// Reasoning/explanation
    pub reasoning: String,
    
    /// Tool calls to execute
    pub tool_calls: Vec<crate::models::ToolCall>,
    
    /// Whether the goal is complete
    pub goal_complete: bool,
}

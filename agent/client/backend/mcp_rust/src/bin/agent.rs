use anyhow::Result;
use colored::*;
use mcp_agent::{AutonomousAgent, AgentConfig, Goal};

#[tokio::main]
async fn main() -> Result<()> {
    println!("\n{}", "═".repeat(70).cyan().bold());
    println!("   {}", "Agent - Goal-Driven Execution".cyan().bold());
    println!("{}", "═".repeat(70).cyan().bold());
    println!();
    
    // Load configuration
    let config = AgentConfig::from_env();
    
    println!("{} Configuration loaded:", "✓".green().bold());
    println!("  MCP Server: {}", config.mcp_base_url);
    println!("  LLM API URL: {}", config.llm_api_url);
    println!("  Qdrant URL: {}", config.qdrant_url);
    println!();
    
    // Initialize agent
    println!("{} Initializing agent...", "→".cyan());
    let mut agent = match AutonomousAgent::new(config).await {
        Ok(agent) => {
            println!("{} Agent initialized successfully\n", "✓".green().bold());
            agent
        }
        Err(e) => {
            eprintln!("{} Failed to initialize agent: {}", "✗".red().bold(), e);
            return Err(e);
        }
    };
    
    // Example: Create and execute a goal
    let goal = Goal::with_config(
        "List all namespaces",
        5,     // max_iterations
        120,   // timeout_seconds
        false, // dry_run (disabled - will make real MCP calls)
    );
    
    println!("{} Executing goal...", "→".cyan());
    println!();

    match agent.execute_goal(goal).await {
        Ok(completed_goal) => {
            println!("\n{} Goal execution finished!", "✓".green().bold());
            println!("Status: {:?}", completed_goal.status);
            
            if let Some(result) = &completed_goal.result {
                println!("Result: {}", result);
            }
            
            if let Some(error) = &completed_goal.error {
                eprintln!("Error: {}", error);
            }
        }
        Err(e) => {
            eprintln!("\n{} Goal execution failed: {}", "✗".red().bold(), e);
            return Err(e);
        }
    }
    
    println!("\n{}", "═".repeat(70).cyan().bold());
    println!();
    
    Ok(())
}

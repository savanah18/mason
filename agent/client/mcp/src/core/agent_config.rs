use serde::{Deserialize, Serialize};

/// Configuration for the autonomous agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentConfig {
    /// MCP server base URL
    pub mcp_base_url: String,
    
    /// Triton inference server URL
    pub triton_url: String,
    
    /// Qdrant vector database URL
    pub qdrant_url: String,
    
    /// Default maximum iterations per goal
    #[serde(default = "default_max_iterations")]
    pub default_max_iterations: u32,
    
    /// Default timeout in seconds
    #[serde(default = "default_timeout")]
    pub default_timeout_seconds: u64,
    
    /// Enable verbose logging
    #[serde(default)]
    pub verbose: bool,
    
    /// Enable dry-run mode by default
    #[serde(default)]
    pub default_dry_run: bool,
    
    /// Temperature for LLM sampling
    #[serde(default = "default_temperature")]
    pub temperature: f32,
    
    /// Top-p for LLM sampling
    #[serde(default = "default_top_p")]
    pub top_p: f32,
    
    /// Maximum tokens to generate per LLM call
    #[serde(default = "default_max_tokens")]
    pub max_tokens: u32,
    
    /// Number of context chunks to retrieve from Qdrant
    #[serde(default = "default_top_k")]
    pub context_top_k: usize,
}

fn default_max_iterations() -> u32 {
    10
}

fn default_timeout() -> u64 {
    300
}

fn default_temperature() -> f32 {
    0.7
}

fn default_top_p() -> f32 {
    0.9
}

fn default_max_tokens() -> u32 {
    512
}

fn default_top_k() -> usize {
    5
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            mcp_base_url: "http://localhost:8080".to_string(),
            triton_url: "http://localhost:8000".to_string(),
            qdrant_url: "http://localhost:6333".to_string(),
            default_max_iterations: default_max_iterations(),
            default_timeout_seconds: default_timeout(),
            verbose: false,
            default_dry_run: false,
            temperature: default_temperature(),
            top_p: default_top_p(),
            max_tokens: default_max_tokens(),
            context_top_k: default_top_k(),
        }
    }
}

impl AgentConfig {
    /// Create config from environment variables
    pub fn from_env() -> Self {
        Self {
            mcp_base_url: std::env::var("MCP_BASE_URL")
                .unwrap_or_else(|_| "http://localhost:8080".to_string()),
            triton_url: std::env::var("TRITON_URL")
                .unwrap_or_else(|_| "http://localhost:8000".to_string()),
            qdrant_url: std::env::var("QDRANT_URL")
                .unwrap_or_else(|_| "http://localhost:6333".to_string()),
            default_max_iterations: std::env::var("DEFAULT_MAX_ITERATIONS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(default_max_iterations()),
            default_timeout_seconds: std::env::var("DEFAULT_TIMEOUT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(default_timeout()),
            verbose: std::env::var("VERBOSE")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(false),
            default_dry_run: std::env::var("DEFAULT_DRY_RUN")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(false),
            temperature: std::env::var("TEMPERATURE")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(default_temperature()),
            top_p: std::env::var("TOP_P")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(default_top_p()),
            max_tokens: std::env::var("MAX_TOKENS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(default_max_tokens()),
            context_top_k: std::env::var("CONTEXT_TOP_K")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(default_top_k()),
        }
    }
    
    /// Load config from JSON file
    pub fn from_file(path: &str) -> anyhow::Result<Self> {
        let content = std::fs::read_to_string(path)?;
        let config = serde_json::from_str(&content)?;
        Ok(config)
    }
    
    /// Save config to JSON file
    pub fn save_to_file(&self, path: &str) -> anyhow::Result<()> {
        let content = serde_json::to_string_pretty(self)?;
        std::fs::write(path, content)?;
        Ok(())
    }
}

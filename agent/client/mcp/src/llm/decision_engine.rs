use anyhow::Result;
use serde::{Deserialize, Serialize};
use crate::core::{AgentConfig, Decision};
use crate::llm::ToolCallParser;
use uuid::Uuid;

#[derive(Debug, Serialize)]
struct TritonInferRequest {
    inputs: Vec<TritonInput>,
    outputs: Vec<TritonOutput>,
}

#[derive(Debug, Serialize)]
struct TritonInput {
    name: String,
    shape: Vec<usize>,
    datatype: String,
    data: Vec<String>,
}

#[derive(Debug, Serialize)]
struct TritonOutput {
    name: String,
}

#[derive(Debug, Deserialize)]
struct TritonInferResponse {
    outputs: Vec<TritonOutputData>,
}

#[derive(Debug, Deserialize)]
struct TritonOutputData {
    name: String,
    data: Vec<String>,
}

/// Decision engine that uses LLM to make decisions
pub struct DecisionEngine {
    triton_url: String,
    model_name: String,
    client: reqwest::Client,
    config: AgentConfig,
    session_id: String,
}

impl DecisionEngine {
    /// Create a new decision engine
    pub fn new(triton_url: &str, config: &AgentConfig) -> Self {
        Self {
            triton_url: triton_url.to_string(),
            model_name: "qwen3-vl".to_string(),
            client: reqwest::Client::new(),
            config: config.clone(),
            session_id: Uuid::new_v4().to_string(),
        }
    }
    
    /// Get the current session ID
    pub fn session_id(&self) -> &str {
        &self.session_id
    }
    
    /// Reset session (clears KV cache on server)
    pub fn reset_session(&mut self) {
        self.session_id = Uuid::new_v4().to_string();
        println!("[DecisionEngine] Reset session to: {}", self.session_id);
    }
    
    /// Make a decision based on the prompt
    pub async fn make_decision(&self, prompt: &str) -> Result<Decision> {
        match self.call_triton(prompt).await {
            Ok(response_text) => {
                let tool_calls = ToolCallParser::parse(&response_text)?;
                
                let goal_complete = response_text.to_lowercase().contains("goal complete")
                    || response_text.to_lowercase().contains("task completed")
                    || response_text.to_lowercase().contains("objective achieved");
                
                Ok(Decision {
                    reasoning: response_text,
                    tool_calls,
                    goal_complete,
                })
            }
            Err(e) => {
                eprintln!("[DecisionEngine] Triton call failed: {}", e);
                Ok(Decision {
                    reasoning: format!("LLM error: {}", e),
                    tool_calls: Vec::new(),
                    goal_complete: false,
                })
            }
        }
    }
    
    /// Call Triton inference server
    async fn call_triton(&self, prompt: &str) -> Result<String> {
        let url = format!("{}/v2/models/{}/infer", self.triton_url, self.model_name);
        
        let request = TritonInferRequest {
            inputs: vec![
                TritonInput {
                    name: "message".to_string(),
                    shape: vec![1, 1],
                    datatype: "BYTES".to_string(),
                    data: vec![prompt.to_string()],
                },
                TritonInput {
                    name: "mode".to_string(),
                    shape: vec![1, 1],
                    datatype: "BYTES".to_string(),
                    data: vec!["generate".to_string()],
                },
                TritonInput {
                    name: "session_id".to_string(),
                    shape: vec![1, 1],
                    datatype: "BYTES".to_string(),
                    data: vec![self.session_id.clone()],
                },
            ],
            outputs: vec![
                TritonOutput {
                    name: "response".to_string(),
                },
            ],
        };
        
        let response = self.client
            .post(&url)
            .header("Content-Type", "application/json")
            .json(&request)
            .timeout(std::time::Duration::from_secs(60))
            .send()
            .await?;
        
        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(anyhow::anyhow!("Triton error: {}", error_text));
        }
        
        let triton_response: TritonInferResponse = response.json().await?;
        
        let response_text = triton_response.outputs
            .iter()
            .find(|o| o.name == "response")
            .and_then(|o| o.data.first())
            .ok_or_else(|| anyhow::anyhow!("No response in Triton output"))?;
        
        Ok(response_text.clone())
    }
}

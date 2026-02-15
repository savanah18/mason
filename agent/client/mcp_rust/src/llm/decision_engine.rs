use anyhow::Result;
use serde::{Deserialize, Serialize};
use crate::core::{AgentConfig, Decision};
use crate::llm::ToolCallParser;
use uuid::Uuid;

#[derive(Debug, Serialize)]
struct OpenAIRequest {
    model: String,
    messages: Vec<OpenAIMessage>,
    #[serde(skip_serializing_if = "Option::is_none")]
    temperature: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    max_tokens: Option<u32>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct OpenAIMessage {
    role: String,
    content: String,
}

#[derive(Debug, Deserialize)]
struct OpenAIResponse {
    choices: Vec<OpenAIChoice>,
}

#[derive(Debug, Deserialize)]
struct OpenAIChoice {
    message: OpenAIMessage,
}

/// Decision engine that uses LLM to make decisions
pub struct DecisionEngine {
    api_url: String,
    model_name: String,
    client: reqwest::Client,
    config: AgentConfig,
    session_id: String,
    api_key: Option<String>,
    conversation_history: Vec<OpenAIMessage>,
}

impl DecisionEngine {
    /// Create a new decision engine
    pub fn new(api_url: &str, config: &AgentConfig) -> Self {
        let api_key = std::env::var("OPENAI_API_KEY").ok();
        Self {
            api_url: api_url.to_string(),
            model_name: std::env::var("OPENAI_MODEL").unwrap_or_else(|_| "gpt-4".to_string()),
            client: reqwest::Client::new(),
            config: config.clone(),
            session_id: Uuid::new_v4().to_string(),
            api_key,
            conversation_history: Vec::new(),
        }
    }
    
    /// Get the current session ID
    pub fn session_id(&self) -> &str {
        &self.session_id
    }
    
    /// Reset session (clears conversation history)
    pub fn reset_session(&mut self) {
        self.session_id = Uuid::new_v4().to_string();
        self.conversation_history.clear();
        println!("[DecisionEngine] Reset session to: {}", self.session_id);
    }
    
    /// Make a decision based on the prompt
    pub async fn make_decision(&mut self, prompt: &str) -> Result<Decision> {
        match self.call_openai(prompt).await {
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
                eprintln!("[DecisionEngine] OpenAI API call failed: {}", e);
                Ok(Decision {
                    reasoning: format!("LLM error: {}", e),
                    tool_calls: Vec::new(),
                    goal_complete: false,
                })
            }
        }
    }
    
    /// Call OpenAI-compatible API
    async fn call_openai(&mut self, prompt: &str) -> Result<String> {
        let url = format!("{}/v1/chat/completions", self.api_url);
        
        // Add user message to conversation history
        self.conversation_history.push(OpenAIMessage {
            role: "user".to_string(),
            content: prompt.to_string(),
        });
        
        let request = OpenAIRequest {
            model: self.model_name.clone(),
            messages: self.conversation_history.clone(),
            temperature: Some(0.7),
            max_tokens: Some(2048),
        };
        
        let mut request_builder = self.client
            .post(&url)
            .header("Content-Type", "application/json")
            .json(&request)
            .timeout(std::time::Duration::from_secs(120));
        
        // Add API key if available
        if let Some(ref api_key) = self.api_key {
            request_builder = request_builder.header("Authorization", format!("Bearer {}", api_key));
        }
        
        let response = request_builder.send().await?;
        
        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(anyhow::anyhow!("OpenAI API error: {}", error_text));
        }
        
        let openai_response: OpenAIResponse = response.json().await?;
        
        let response_message = openai_response.choices
            .first()
            .ok_or_else(|| anyhow::anyhow!("No choices in OpenAI response"))?
            .message
            .clone();
        
        // Add assistant response to conversation history
        self.conversation_history.push(response_message.clone());
        
        Ok(response_message.content)
    }
}

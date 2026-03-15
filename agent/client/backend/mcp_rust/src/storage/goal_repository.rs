use anyhow::Result;
use std::path::Path;
use crate::models::Goal;

/// Repository for persisting goals
pub struct GoalRepository {
    storage_dir: String,
}

impl GoalRepository {
    /// Create a new goal repository
    pub fn new(storage_dir: &str) -> Result<Self> {
        std::fs::create_dir_all(storage_dir)?;
        Ok(Self {
            storage_dir: storage_dir.to_string(),
        })
    }
    
    /// Save a goal to disk
    pub fn save(&self, goal: &Goal) -> Result<()> {
        let path = Path::new(&self.storage_dir).join(format!("{}.json", goal.id));
        let content = serde_json::to_string_pretty(goal)?;
        std::fs::write(path, content)?;
        Ok(())
    }
    
    /// Load a goal by ID
    pub fn get_by_id(&self, id: &str) -> Result<Option<Goal>> {
        let path = Path::new(&self.storage_dir).join(format!("{}.json", id));
        
        if !path.exists() {
            return Ok(None);
        }
        
        let content = std::fs::read_to_string(path)?;
        let goal = serde_json::from_str(&content)?;
        Ok(Some(goal))
    }
    
    /// List all active goals (not completed/failed/cancelled)
    pub fn list_active(&self) -> Result<Vec<Goal>> {
        // TODO: Implement efficient listing - Feature 1.2
        Ok(Vec::new())
    }
    
    /// Delete a goal
    pub fn delete(&self, id: &str) -> Result<()> {
        let path = Path::new(&self.storage_dir).join(format!("{}.json", id));
        if path.exists() {
            std::fs::remove_file(path)?;
        }
        Ok(())
    }
}

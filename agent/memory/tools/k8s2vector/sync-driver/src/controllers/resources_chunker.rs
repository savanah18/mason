use serde_json::Value;
use sha2::{Digest, Sha256};

#[derive(Debug, Clone)]
pub struct ResourceChunk {
    pub id: String,
    pub resource: Value,
    pub uid: Option<String>,
}

pub struct ResourcesChunker;

impl ResourcesChunker {
    pub fn new() -> Self {
        Self
    }

    pub fn chunk_resources(&self, resources: &[Value]) -> Vec<ResourceChunk> {
        resources
            .iter()
            .map(|resource| self.chunk_resource(resource))
            .collect()
    }

    fn chunk_resource(&self, resource: &Value) -> ResourceChunk {
        let uid = extract_uid(resource);
        let canonical = canonicalize_value(resource);
        let canonical_str = serde_json::to_string(&canonical).unwrap_or_else(|_| "null".to_string());
        let id = compute_id(uid.as_deref().unwrap_or(""), &canonical_str);

        ResourceChunk {
            id,
            resource: resource.clone(),
            uid,
        }
    }
}

fn extract_uid(value: &Value) -> Option<String> {
    value
        .get("metadata")
        .and_then(|meta| meta.get("uid"))
        .and_then(|uid| uid.as_str())
        .map(|uid| uid.to_string())
}

fn canonicalize_value(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut keys: Vec<String> = map.keys().cloned().collect();
            keys.sort();

            let mut new_map = serde_json::Map::new();
            for key in keys {
                if let Some(child) = map.get(&key) {
                    new_map.insert(key, canonicalize_value(child));
                }
            }

            Value::Object(new_map)
        }
        Value::Array(items) => {
            Value::Array(items.iter().map(canonicalize_value).collect())
        }
        _ => value.clone(),
    }
}

fn compute_id(uid: &str, canonical_json: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(uid.as_bytes());
    hasher.update(b":");
    hasher.update(canonical_json.as_bytes());
    let digest = hasher.finalize();
    to_hex(&digest)
}

fn to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

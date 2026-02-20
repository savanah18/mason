mod controllers;

use serde_json::{to_string_pretty, to_value, Value};
use tracing::{info, debug};

use controllers::k8s_controllers::{K8sResourceCollector, ResourceEvent};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt::init();

    let collector = K8sResourceCollector::new().await?;

    // Option 1: Get initial full state
    info!("Collecting initial state...");
    let all_items = collector.collect_all().await?;
    debug!("{}", to_string_pretty(&all_items)?);

    let chunker = controllers::resources_chunker::ResourcesChunker::new();
    let chunks = chunker.chunk_resources(&all_items);
    info!("Total chunks created: {}", chunks.len());

    // Option 2: Watch for changes (only diffs)
    info!("Starting watch for resource changes...");
    let mut event_stream = collector.watch_changes_stream().await?;

    while let Some(event) = event_stream.recv().await {
        match event {
            ResourceEvent::Modified(resource) => {
                if let Some(name) = resource.get("metadata").and_then(|m| m.get("name")).and_then(|n| n.as_str()) {
                    let kind = resource.get("kind").and_then(|k| k.as_str()).unwrap_or("Unknown");
                    info!("Resource changed: {} {}", kind, name);
                    
                    // Chunk and process the changed resource
                    let chunk = chunker.chunk_resources(&[resource]);
                    info!("Chunk ID: {}", chunk[0].id);
                    
                    // TODO: Send to Triton for embedding, then upsert to Qdrant
                }
            }
            ResourceEvent::Added(resource) => {
                info!("Resource added: {:?}", resource.get("metadata").and_then(|m| m.get("name")));
            }
            ResourceEvent::Deleted(resource) => {
                info!("Resource deleted: {:?}", resource.get("metadata").and_then(|m| m.get("name")));
            }
        }
    }

    Ok(())
}
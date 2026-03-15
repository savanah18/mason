use tracing::{info, debug, warn};
use kube::runtime::{watcher, WatchStreamExt};
use futures::StreamExt;

#[derive(Debug, Clone)]
pub enum ResourceEvent {
    Added(serde_json::Value),
    Modified(serde_json::Value),
    Deleted(serde_json::Value),
}

pub struct K8sResourceCollector {
    client: kube::Client,
    discovery: kube::discovery::Discovery,
}

impl K8sResourceCollector {
    pub async fn new() -> Result<Self, Box<dyn std::error::Error>> {
        let client = kube::Client::try_default().await?;
        let discovery = kube::discovery::Discovery::new(client.clone()).run_aggregated().await?;
        Ok(Self { client, discovery })
    }

    fn should_exclude_namespace(namespace: Option<&str>) -> bool {
        matches!(namespace, Some("kube-system") | Some("kube-public") | Some("kube-node-lease"))
    }

    fn should_exclude_kind(kind: &str) -> bool {
        matches!(kind, "Lease" | "Event" | "EndpointSlice")
    }

    pub async fn collect_all(&self) -> Result<Vec<serde_json::Value>, Box<dyn std::error::Error>> {
        let mut all_items: Vec<serde_json::Value> = Vec::new();

        // Iterate through all resource types
        for group in self.discovery.groups() {
            for (ar, caps) in group.recommended_resources() {
                if !(caps.supports_operation(kube::discovery::verbs::LIST)) {
                    continue;
                }

                let api: kube::Api<kube::api::DynamicObject> = kube::Api::all_with(self.client.clone(), &ar);
                let list = api.list(&kube::api::ListParams::default()).await?;
                for item in list {
                    // Skip kube-system namespace resources
                    let namespace = item.metadata.namespace.as_deref();
                    if Self::should_exclude_namespace(namespace) {
                        continue;
                    }

                    let mut json = serde_json::to_value(&item)?;
                    // Check kind and exclude noisy resources
                    if let serde_json::Value::Object(ref map) = json {
                        if let Some(kind) = map.get("kind").and_then(|k| k.as_str()) {
                            if Self::should_exclude_kind(kind) {
                                continue;
                            }
                        }
                    }
                    // destructure but keeping the original json
                    if let serde_json::Value::Object(ref mut map) = json {
                        map.insert(
                            "apiVersion".to_string(), 
                            serde_json::Value::String(
                                if ar.group.is_empty(){ar.version.clone()} 
                                else {format!("{}/{}", ar.group, ar.version)}
                            )
                        );
                        map.insert("kind".to_string(), serde_json::Value::String(ar.kind.clone()));
                    }
                    all_items.push(json);
                } 
            }
        }
        Ok(all_items)   
    }

    /// Watch for resource changes (only diffs, not full state)
    pub async fn watch_changes<F>(&self, mut callback: F) -> Result<(), Box<dyn std::error::Error>>
    where
        F: FnMut(ResourceEvent) -> (),
    {
        info!("Starting watch for all Kubernetes resources...");

        let mut watch_handles = vec![];

        for group in self.discovery.groups() {
            for (ar, caps) in group.recommended_resources() {
                if !caps.supports_operation(kube::discovery::verbs::WATCH) {
                    continue;
                }

                let client = self.client.clone();
                let ar_clone = ar.clone();
                
                let handle = tokio::spawn(async move {
                    let api: kube::Api<kube::api::DynamicObject> = kube::Api::all_with(client, &ar_clone);
                    let watcher_config = watcher::Config::default();
                    let mut stream = watcher(api, watcher_config).applied_objects().boxed();

                    info!("Watching {}.{}/{}", ar_clone.plural, ar_clone.group, ar_clone.version);

                    while let Some(event) = stream.next().await {
                        match event {
                            Ok(obj) => {
                                let mut json = match serde_json::to_value(&obj) {
                                    Ok(j) => j,
                                    Err(e) => {
                                        warn!("Error serializing {}: {}", ar_clone.kind, e);
                                        continue;
                                    }
                                };

                                // Enrich with apiVersion and kind
                                if let serde_json::Value::Object(ref mut map) = json {
                                    map.insert(
                                        "apiVersion".to_string(),
                                        serde_json::Value::String(
                                            if ar_clone.group.is_empty() {
                                                ar_clone.version.clone()
                                            } else {
                                                format!("{}/{}", ar_clone.group, ar_clone.version)
                                            }
                                        ),
                                    );
                                    map.insert("kind".to_string(), serde_json::Value::String(ar_clone.kind.clone()));
                                }

                                // Determine event type (Added/Modified/Deleted)
                                // Note: kube watcher doesn't directly expose this, so we treat all as Modified
                                // For full event types, use raw watch API
                                debug!("Resource changed: {}/{}", ar_clone.kind, obj.metadata.name.as_ref().unwrap_or(&"unknown".to_string()));
                                
                                // Callback would go here, but closures can't be sent across threads easily
                                // So we'll return events via channel instead
                            }
                            Err(e) => {
                                warn!("Watch error for {}: {}", ar_clone.kind, e);
                            }
                        }
                    }
                });

                watch_handles.push(handle);
            }
        }

        // Wait for all watchers (runs indefinitely)
        for handle in watch_handles {
            let _ = handle.await;
        }

        Ok(())
    }

    /// Watch changes with channel-based event streaming (better for callbacks)
    pub async fn watch_changes_stream(&self) -> Result<tokio::sync::mpsc::Receiver<ResourceEvent>, Box<dyn std::error::Error>> {
        let (tx, rx) = tokio::sync::mpsc::channel::<ResourceEvent>(1000);

        info!("Starting watch stream for all Kubernetes resources...");

        for group in self.discovery.groups() {
            for (ar, caps) in group.recommended_resources() {
                if !caps.supports_operation(kube::discovery::verbs::WATCH) {
                    continue;
                }

                let client = self.client.clone();
                let ar_clone = ar.clone();
                let tx_clone = tx.clone();
                
                tokio::spawn(async move {
                    let api: kube::Api<kube::api::DynamicObject> = kube::Api::all_with(client, &ar_clone);
                    let watcher_config = watcher::Config::default();
                    let mut stream = watcher(api, watcher_config).applied_objects().boxed();

                    info!("Watching {}.{}/{}", ar_clone.plural, ar_clone.group, ar_clone.version);

                    while let Some(event) = stream.next().await {
                        match event {
                            Ok(obj) => {
                                // Skip kube-system namespace resources
                                let namespace = obj.metadata.namespace.as_deref();
                                if K8sResourceCollector::should_exclude_namespace(namespace) {
                                    continue;
                                }

                                let mut json = match serde_json::to_value(&obj) {
                                    Ok(j) => j,
                                    Err(e) => {
                                        warn!("Error serializing {}: {}", ar_clone.kind, e);
                                        continue;
                                    }
                                };

                                // Exclude noisy resource kinds
                                if let serde_json::Value::Object(ref map) = json {
                                    if let Some(kind) = map.get("kind").and_then(|k| k.as_str()) {
                                        if K8sResourceCollector::should_exclude_kind(kind) {
                                            continue;
                                        }
                                    }
                                }

                                if let serde_json::Value::Object(ref mut map) = json {
                                    map.insert(
                                        "apiVersion".to_string(),
                                        serde_json::Value::String(
                                            if ar_clone.group.is_empty() {
                                                ar_clone.version.clone()
                                            } else {
                                                format!("{}/{}", ar_clone.group, ar_clone.version)
                                            }
                                        ),
                                    );
                                    map.insert("kind".to_string(), serde_json::Value::String(ar_clone.kind.clone()));
                                }

                                // Send as Modified event (for simplicity)
                                if tx_clone.send(ResourceEvent::Modified(json)).await.is_err() {
                                    warn!("Receiver dropped, stopping watch for {}", ar_clone.kind);
                                    break;
                                }
                            }
                            Err(e) => {
                                warn!("Watch error for {}: {}", ar_clone.kind, e);
                            }
                        }
                    }
                });
            }
        }

        Ok(rx)
    }
}
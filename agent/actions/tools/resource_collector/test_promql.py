import google.auth
import google.auth.transport.requests
from prometheus_api_client import PrometheusConnect

# --- CONFIGURATION ---
PROJECT_ID = "gen-lang-client-0341576589"
REGION = "asia-southeast1"  # e.g., "us-central1" or "global"

# GKE Autopilot / Managed Service for Prometheus endpoint
ENDPOINT_URL = f"https://monitoring.googleapis.com/v1/projects/{PROJECT_ID}/location/{REGION}/prometheus"



if __name__ == "__main__":
    # 1. Get Google Application Default Credentials
    credentials, _ = google.auth.default(
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    
    # 2. Refresh the token
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    
    # 3. Initialize the Prometheus Client with Google Auth headers
    prom = PrometheusConnect(
        url=ENDPOINT_URL,
        headers={"Authorization": f"Bearer {credentials.token}"},
        disable_ssl=False
    )

    print(f"Connecting to: {ENDPOINT_URL}")

    # 4. Enumerate all metric names available from this endpoint.
    metrics = prom.all_metrics()
    print(f"Found {len(metrics)} metrics. First 20:")
    for m in sorted(metrics)[:20]:
        print(f"  - {m}")

    # 5. Run the user query, and if empty fallback to a discovered metric.
    promql_query = 'topk(5, max by (pod) (rate(container_cpu_usage_seconds_total{namespace="kube-system"}[5m])))'
    result = prom.custom_query(query=promql_query)
    print(f"\nPromQL Query: {promql_query}")
    print(f"Result: {result}")

    if not result and metrics:
        sample_metric = sorted(metrics)[0]
        fallback_query = f'topk(5, max_over_time({{__name__="{sample_metric}"}}[5m]))'
        fallback_result = prom.custom_query(query=fallback_query)
        print("\nPrimary query returned no data; trying fallback query with discovered metric name.")
        print(f"Fallback Query: {fallback_query}")
        print(f"Fallback Result: {fallback_result}")
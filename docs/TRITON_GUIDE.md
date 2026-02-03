# Triton Integration Guide

## Overview

This project uses **Triton Inference Server** for high-performance, GPU-accelerated model serving with dynamic batching support.

## Architecture

```
┌──────────────────────────────────────┐
│       Client Applications             │
│  (VS Code, Web, REST, gRPC)          │
└──────────────────┬────────────────────┘
                   │
        ┌──────────▼──────────┐
        │  Triton Server      │
        │  (8000/8001/8002)   │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │  Qwen3-VL Model     │
        │  (GPU-accelerated)   │
        └─────────────────────┘
```

## Directory Structure

```
newbie-app/
├── docker-compose.yml               # Service orchestration
├── requirements.txt                 # Dependencies
│
├── agent/
│   ├── memory/                      # RAG system
│   │   ├── config.py
│   │   ├── vector_store.py
│   │   ├── chunking.py
│   │   └── retriever.py
│   │
│   ├── serving/
│   │   └── triton/
│   │       ├── models/
│   │       │   └── qwen3-vl/
│   │       │       ├── config.pbtxt
│   │       │       └── 1/
│   │       │           └── model.py
│   │       │
│   │       └── docker/
│   │           ├── Dockerfile.triton
│   │           ├── nginx.conf
│   │           └── requirements-triton.txt
│   │
│   └── client/
│       ├── triton_client.py
│       └── extensions/vscode/
│
└── docs/
```

## Quick Start

### 1. Build and Start Services

```bash
cd /root/workspace/lnd/aiops/apps/newbie-app

# Build and start Triton
docker-compose up --build
```

### 2. Verify Services

Check Triton health:
```bash
curl http://localhost:8000/v2/health/ready
```

Check Triton model status:
```bash
curl http://localhost:8000/v2/models/qwen3-vl
```

### 3. Send Inference Request

**Using Python Client:**
```bash
python agent/client/triton_client.py
```

**Using cURL:**
```bash
# Check health
curl http://localhost:8000/v2/health/live
```

## Usage Guide

### Triton Server

Available at:
- **HTTP:** `http://localhost:8000`
- **gRPC:** `localhost:8001`
- **Metrics:** `http://localhost:8002`

**Using Python Client:**
```python
from agent.client.triton_client import TritonHttpClient

client = TritonHttpClient("localhost:8000")

if client.check_health():
    response, response_time = client.chat("What is a data structure?")
    print(f"Response: {response}")
    print(f"Time: {response_time:.2f}s")
```

**Using cURL:**
```bash
# Get model metadata
curl http://localhost:8000/v2/models/qwen3-vl

# Check health
curl http://localhost:8000/v2/health/live
```

## Configuration

### Environment Variables

Configure in `docker-compose.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_PATH` | `/root/workspace/lnd/aiops/vlm/Qwen/Qwen3-VL-8B-Instruct` | Model checkpoint path |
| `QUANTIZATION_TYPE` | `int4` | Quantization: none, int4, int8, awq, gptq |
| `ATTENTION_IMPL` | `sdpa` | Attention: eager, sdpa, flash_attention_2 |
| `MAX_HISTORY` | `5` | Conversation history size |
| `MAX_NEW_TOKENS` | `512` | Max tokens to generate |
| `TEMPERATURE` | `0.7` | Generation temperature |
| `TOP_P` | `0.9` | Top-p sampling parameter |

### Update Configuration

Edit `docker-compose.yml`:
```yaml
environment:
  - QUANTIZATION_TYPE=int8
  - MAX_NEW_TOKENS=256
```

Then restart:
```bash
docker-compose down
docker-compose up --build
```

## Performance Comparison

| Feature | Value |
|---------|-------|
| **Latency** | ~2-5s per request |
| **Throughput** | Dynamic batching (up to 4x) |
| **Dynamic Batching** | ✅ Enabled |
| **gRPC Support** | ✅ Available |
| **Model Management** | Automatic |
| **Metrics** | Prometheus-compatible |
| **Production Ready** | ✅ Yes |
| Throughput | Lower | Higher (batching) |
| Dynamic batching | ❌ | ✅ |
| Model state mgmt | Per-request | Per-instance |
| Easy debugging | ✅ | ⚠️ |
| Production-ready | ✅ | ✅ |

## Advanced Usage

## Batch Inference with Triton

```python
from agent.client.triton_client import TritonHttpClient
import concurrent.futures

client = TritonHttpClient("localhost:8000")

messages = [
    "What is a tree?",
    "What is a graph?",
    "What is a hash table?"
]

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(client.chat, msg) for msg in messages]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

for msg, (response, time) in zip(messages, results):
    print(f"Q: {msg}")
    print(f"A: {response}\n")
```

## Using gRPC for Lower Latency

```python
from agent.client.triton_client import TritonGrpcClient

client = TritonGrpcClient("localhost:8001")  # gRPC port
response, response_time = client.chat("Explain quicksort")
print(f"Response (gRPC): {response_time:.3f}s")
```

## Monitor Triton Metrics

```bash
# Prometheus metrics endpoint
curl http://localhost:8002/metrics
```

## Troubleshooting

### Services won't start

```bash
# Check logs
docker-compose logs -f

# Check specific service
docker-compose logs triton-server
```

### Out of Memory (OOM)

Reduce model size or adjust memory settings in `docker-compose.yml`:
```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          device_ids: ['0']  # Specific GPU
          capabilities: [gpu]
```

### Model not loading in Triton

1. Check model path exists and is readable
2. Verify `config.pbtxt` is properly formatted
3. Check Triton logs: `docker-compose logs triton-server`
4. Ensure model.py has no syntax errors:
   ```bash
   docker exec triton-ai-server python -m py_compile /models/qwen3-vl/1/model.py
   ```

### Slow inference

Enable dynamic batching (already configured in `config.pbtxt`). For more details, see [TRITON_PERFORMANCE.md](TRITON_PERFORMANCE.md).

## API Documentation

### Triton
- Model metadata: `http://localhost:8000/v2/models/qwen3-vl`
- Server status: `http://localhost:8000/v2`
- Metrics: `http://localhost:8002`

## Stopping Services

```bash
# Stop and remove containers
docker-compose down

# Keep volumes
docker-compose down -v

# View running containers
docker ps

# Stop specific service
docker-compose stop triton-server
```

## Next Steps

1. **Test with VS Code Extension** - See [agent/client/extensions/vscode/README.md](agent/client/extensions/vscode/README.md)
2. **Implement RAG features** - See [agent/memory/](agent/memory/) for RAG system
3. **Monitor Performance** - Check metrics at `http://localhost:8002`
4. **Scale to Production** - Deploy to Kubernetes with Helm
5. **Add Monitoring** - Integrate Prometheus + Grafana for metrics

## References

- [Triton Inference Server Docs](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/)
- [Python Backend Guide](https://github.com/triton-inference-server/python_backend)
- [Model Config Reference](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/model_configuration.html)
- [Triton Client Libraries](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/client.html)
- [Performance Optimization](TRITON_PERFORMANCE.md)

# Triton Integration - Quick Reference

## Key Files

- `agent/serving/triton/models/qwen3-vl/config.pbtxt` - Model configuration
- `agent/serving/triton/models/qwen3-vl/1/model.py` - Python backend
- `agent/serving/triton/docker/Dockerfile.triton` - Docker image
- `docker-compose.yml` - Service orchestration
- `agent/client/triton_client.py` - Python client

## Quick Commands

### Start Everything (Production Mode)
```bash
cd /root/workspace/lnd/aiops/apps/newbie-app
docker compose up --build
```

### Development Mode (Fast Iteration)
```bash
# For development, edit files and rebuild
BUILD_MODE=dev docker compose up --build triton-server
```

### Production Mode (Clean Build)
```bash
# For production deployments
BUILD_MODE=prod docker compose up --build triton-server
```

### Test Services
```bash
# Triton health check
curl http://localhost:8000/v2/health/ready
curl http://localhost:8000/v2/health/live

# Triton model metadata
curl http://localhost:8000/v2/models/qwen3-vl

# Test Triton Python client
python agent/client/triton_client.py
```

### View Logs
```bash
docker compose logs -f
docker compose logs triton-server  # Just Triton
```

### Stop Services
```bash
docker compose down
```

### Check Health Status
```bash
docker compose ps
docker inspect triton-ai-server --format='{{.State.Health.Status}}'
```

## Service Ports

| Service | Type | Port | URL |
|---------|------|------|-----|
| Triton | HTTP REST | 8000 | http://localhost:8000 |
| Triton | gRPC | 8001 | localhost:8001 |
| Triton | Metrics | 8002 | http://localhost:8002 |

## Build Modes

### Development Mode (`BUILD_MODE=dev`)
- Fast iteration during development
- Copies packages from host environment
- **Note**: Requires compatible Python versions

### Production Mode (`BUILD_MODE=prod`)
- Clean, reproducible builds
- Installs all packages via pip
- **Recommended** for deployments

## Key Features

✅ **Triton Server:**
- Python backend with custom model loading
- Dynamic batching (max_batch_size: 4)
- GPU acceleration
- gRPC & HTTP support
- Health checks and metrics
- Production ready

✅ **RAG Integration:**
- Qdrant vector database
- Redis caching
- Async retrieval
- Token-aware chunking

✅ **Complete Setup:**
- Docker multi-stage builds
- Service orchestration
- VS Code extension integration
- Comprehensive documentation

## Next Steps

1. **Verify Triton**: `curl http://localhost:8000/v2/health/ready`
2. **Test Inference**: `python agent/client/triton_client.py`
3. **Check VS Code Extension**: [agent/client/extensions/vscode/README.md](agent/client/extensions/vscode/README.md)
4. **Setup RAG**: [agent/memory/](agent/memory/) for knowledge base integration
5. **Optimize Performance**: [TRITON_PERFORMANCE.md](TRITON_PERFORMANCE.md)

For detailed documentation, see [TRITON_GUIDE.md](TRITON_GUIDE.md)

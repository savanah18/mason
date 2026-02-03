# Getting Started with Triton AI Chat

This guide walks you through installing and running the Triton AI Chat platform.

## Prerequisites

- **GPU**: NVIDIA GPU with CUDA support (8GB+ VRAM recommended for int4 quantization)
- **Python**: 3.12+ via Conda
- **Model**: Qwen3-VL-8B-Instruct (auto-downloaded on first run, or pre-download to `/root/workspace/lnd/aiops/vlm/Qwen/`)
- **Docker**: Docker and Docker Compose for services (Qdrant, Redis)
- **Disk**: ~25GB for model + embeddings

## Installation

### Step 1: Clone and Setup Environment

```bash
cd /root/workspace/lnd/aiops/apps/newbie-app

# Create Python 3.12 environment
conda create -n aiops-py312 python=3.12 -y
conda activate aiops-py312

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Start Services

```bash
# Create data directories
mkdir -p data/qdrant data/redis

# Start Qdrant (vector DB) and Redis (cache) with Docker
docker-compose up -d qdrant redis

# Verify services are healthy
curl http://localhost:6333/healthz          # Qdrant
redis-cli ping                               # Redis (should return PONG)
```

**Service Ports:**
- Qdrant HTTP: `http://localhost:6333`
- Qdrant gRPC: `localhost:6334`
- Redis: `localhost:6379`

### Step 3: Configure Environment

```bash
# Copy template configuration
cp .env.example .env
```

Edit `.env` with your preferences:

```bash
# Model loading
LOADING_STRATEGY=native           # native or vllm
QUANTIZATION_TYPE=int4            # int4 (recommended for <16GB RAM), int8, or none
MAX_NEW_TOKENS=512                # Tokens per response

# RAG services
ENABLE_RAG=true
QDRANT_HOST=localhost
QDRANT_PORT=6333
REDIS_HOST=localhost
REDIS_PORT=6379
```

### Step 4: Start Model Server

```bash
# This will download Qwen3-VL (~12GB) on first run
python agent/serving/model_server.py
```

Wait for the startup message:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Then verify it's working:
```bash
curl http://localhost:8000/health
```

### Step 5: Install VS Code Extension

**Option A: Build from Source**
```bash
cd agent/client/extensions/vscode
npm install
npm run compile
npm run package
```

Then in VS Code:
1. Open Extensions view (`Ctrl+Shift+X` / `Cmd+Shift+X`)
2. Click **Install from VSIX**
3. Select `triton-ai-chat-0.2.0.vsix`

**Option B: Pre-built Package**
```bash
# If available, copy the pre-built extension
cp agent/client/extensions/vscode/triton-ai-chat-0.2.0.vsix ~/Downloads/
```

Then install from VSIX file in VS Code.

### Step 6: Use the Extension

1. Open VS Code Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Run `Triton AI: Open Chat Assistant`
3. Check status shows "Model: Loaded"
4. Start asking questions!

---

## Configuration Guide

### Loading Strategies

Choose based on your system RAM:

#### Native Loading (Recommended for <16GB RAM)
```bash
LOADING_STRATEGY=native
QUANTIZATION_TYPE=int4            # 5-6GB VRAM, good quality
# or
QUANTIZATION_TYPE=int8            # 8-10GB VRAM, very good quality
# or
QUANTIZATION_TYPE=none            # 14-16GB VRAM, best quality
```

#### vLLM Loading (For 24GB+ RAM systems)
```bash
LOADING_STRATEGY=vllm
QUANTIZATION_TYPE=none            # Requires 15-19GB VRAM + 24-32GB system RAM
VLLM_GPU_MEMORY_UTILIZATION=0.9
```

### Key Parameters

```bash
# Model location
MODEL_PATH=/root/workspace/lnd/aiops/vlm/Qwen/Qwen3-VL-8B-Instruct

# Inference settings
MAX_NEW_TOKENS=512                # Higher = slower but more complete responses
ATTENTION_IMPL=sdpa               # eager, sdpa, or flash_attention_2
TEMPERATURE=0.7                   # Lower = more deterministic
TOP_P=0.9                        # Higher = more diverse

# RAG settings
TOP_K=3                          # Number of documents to retrieve
SCORE_THRESHOLD=0.7              # Minimum relevance score
```

---

## Troubleshooting

### Model Server Won't Start

**Error: CUDA out of memory**
```bash
# Solution: Use int4 quantization (5-6GB VRAM needed)
QUANTIZATION_TYPE=int4
python agent/serving/model_server.py
```

**Error: Model path not found**
```bash
# Solution: Check model location
ls /root/workspace/lnd/aiops/vlm/Qwen/Qwen3-VL-8B-Instruct

# If missing, download it or update MODEL_PATH in .env
```

**Error: CUDA not available**
```bash
# Solution: Check NVIDIA drivers
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"

# Install NVIDIA Container Toolkit for Docker
```

### Extension Can't Connect

**Error: "Cannot connect to server"**
```bash
# 1. Check if server is running
curl http://localhost:8000/health

# 2. Check port is accessible
netstat -tlnp | grep 8000

# 3. Check firewall
sudo ufw allow 8000  # Linux

# 4. View server logs
tail -f logs/model_server.log
```

### Out of Memory Errors

**Issue: OOM during inference**

Options:
1. **Reduce tokens**: `MAX_NEW_TOKENS=256` (faster, shorter responses)
2. **Enable quantization**: `QUANTIZATION_TYPE=int4` (saves ~50% VRAM)
3. **Close other GPU processes**: `nvidia-smi` to check
4. **Reduce batch size**: If running multiple requests

**Issue: OOM during model load**

Solutions:
- Use int4 quantization: `QUANTIZATION_TYPE=int4`
- Switch to vLLM (requires more system RAM but better throughput)
- Reduce MAX_HISTORY (fewer messages kept in memory)

### Slow Inference

**Issue: Inference takes >5 seconds**

Try these:
1. **Check GPU utilization**: `nvidia-smi`
2. **Reduce MAX_NEW_TOKENS**: `MAX_NEW_TOKENS=128` for 4x faster response
3. **Use vLLM for production**: Better optimized for throughput
4. **Check system RAM**: Low RAM causes swapping, slows inference

### Qdrant/Redis Connection Issues

**Error: Cannot connect to Qdrant (port 6333)**
```bash
# Check Docker containers
docker ps | grep -E "qdrant|redis"

# View logs
docker logs <container_id>

# Restart services
docker-compose restart qdrant redis
```

**Error: Redis connection refused**
```bash
# Test Redis
redis-cli ping  # Should return PONG

# Restart
docker restart <redis_container_id>
```

---

## Quick Reference

### Common Commands

```bash
# Check server status
curl http://localhost:8000/health

# View API documentation
# Open: http://localhost:8000/docs

# Check GPU memory
nvidia-smi

# View model server logs
tail -f logs/model_server.log

# Restart services
docker-compose restart qdrant redis

# Stop all services
docker-compose down
```

### Performance Targets

| Operation | Latency | Notes |
|-----------|---------|-------|
| Server startup | 30-60s | First run includes model download |
| Single inference | 0.5-2s | Depends on tokens and GPU |
| Batch (32) | 5-10s | Better throughput per request |
| Vector search | 10-20ms | From Qdrant |
| Cache hit | <5ms | Response from Redis |

---

## Next Steps

1. **Learn the System**: Read [ARCHITECTURE.md](ARCHITECTURE.md)
2. **Configure RAG**: See [RAG_INTEGRATION_PLAN.md](docs/RAG_INTEGRATION_PLAN.md)
3. **Optimize Performance**: Read [TRITON_PERFORMANCE.md](docs/TRITON_PERFORMANCE.md)
4. **Embeddings**: Check [docs/VLM2VEC_EMBEDDING_GUIDE.md](docs/VLM2VEC_EMBEDDING_GUIDE.md)
5. **K8s Sync**: Explore [docs/K8S_SYNC_DRIVER_GUIDE.md](docs/K8S_SYNC_DRIVER_GUIDE.md)

---

## Support

- API Docs: `http://localhost:8000/docs`
- GitHub: [Qwen3-VL](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct)
- Issues: Check logs in `logs/model_server.log`

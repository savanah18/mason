# Triton AI Chat - Production-Ready Inference Platform

> An intelligent **AI-powered VS Code assistant** with Triton Inference Server, Qdrant Vector DB, real-time Kubernetes synchronization, and **Model Context Protocol (MCP) tool orchestration**.

**Status:** ✅ Production-Ready | **Latest:** February 1, 2026


## Quick Start

```bash
# Setup
conda create -n aiops-py312 python=3.12 -y
conda activate aiops-py312
cd /root/workspace/lnd/aiops/apps/newbie-app
pip install -r requirements.txt

# Start services
mkdir -p data/qdrant data/redis
docker-compose up -d qdrant redis
python agent/serving/model_server.py
```

Then open VS Code → Command Palette → `Triton AI: Open Chat Assistant`

---

## What's New (Feb 1, 2026)

| Feature | Status | Description |
|---------|--------|-------------|
| **MCP Tool Discovery** | ✅ Complete | 22 Kubernetes management tools discovered and cataloged |
| **Python MCP Client** | ✅ Complete | HTTP-based session management with tool discovery |
| **Rust MCP Client** | ✅ Complete | Async/tokio implementation with feature parity to Python |
| **LLM Agent Integration** | 🔄 In Progress | System prompts with tool schemas ready for LLM injection |
| **K8s Sync Driver** | ✅ Active | Real-time Kubernetes resource monitoring with deterministic deduplication |
| **Triton Embeddings** | ✅ Active | Production-grade batch embeddings (50-100 items/sec) |

---

## System Architecture

```
Clients (VS Code, Web)
    ↓ REST API (port 8000)
    ↓
Qwen3-VL (int4, 5-6GB VRAM)
    ↓
├─ Qdrant Vector DB (RAG)
├─ Redis Cache (sub-5ms)
└─ K8s Sync Driver (Rust)
```

---

## Getting Started

| Topic | Document |
|-------|----------|
| **Installation & Setup** | [GETTING_STARTED.md](GETTING_STARTED.md) |
| **System Design** | [ARCHITECTURE.md](ARCHITECTURE.md) |
| **Embeddings (Local vs Triton)** | [docs/VLM2VEC_EMBEDDING_GUIDE.md](docs/VLM2VEC_EMBEDDING_GUIDE.md) |
| **K8s Real-Time Sync** | [docs/K8S_SYNC_DRIVER_GUIDE.md](docs/K8S_SYNC_DRIVER_GUIDE.md) |
| **Triton Server Deployment** | [TRITON_GUIDE.md](docs/TRITON_GUIDE.md) |
| **Performance Optimization** | [TRITON_PERFORMANCE.md](docs/TRITON_PERFORMANCE.md) |
| **RAG Integration** | [RAG_INTEGRATION_PLAN.md](docs/RAG_INTEGRATION_PLAN.md) |
| **Version History** | [CHANGELOG.md](CHANGELOG.md) |

---

## Configuration

Copy `.env.example` to `.env`:

```bash
LOADING_STRATEGY=native          # native or vllm
QUANTIZATION_TYPE=int4           # int4 (recommended), int8, or none
MAX_NEW_TOKENS=512
ENABLE_RAG=true
QDRANT_HOST=localhost
REDIS_HOST=localhost
```

---

## Inference Performance

| Strategy | VRAM | Speed | Best For |
|----------|------|-------|----------|
| Native + int4 | 5-6GB | Fast | Budget systems |
| Native + int8 | 8-10GB | Medium | Balanced |
| vLLM + none | 15-19GB | Very Fast | 24GB+ servers |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Model won't load | Check GPU: `nvidia-smi` (need 5-6GB) |
| Extension won't connect | Verify: `curl http://localhost:8000/health` |
| Out of memory | Use int4 quantization or reduce MAX_NEW_TOKENS |

See [GETTING_STARTED.md](GETTING_STARTED.md) for detailed troubleshooting.

---

## References

- [Qwen3-VL](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct) - Vision-Language Model
- [FastAPI](https://fastapi.tiangolo.com/) - REST API
- [Qdrant](https://qdrant.tech/) - Vector Database
- [Triton](https://github.com/triton-inference-server/server) - Inference Server

---

**Happy learning! 🚀**


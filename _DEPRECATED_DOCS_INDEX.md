# Documentation Index

**Updated:** February 1, 2026

## Core Documentation

### 🚀 Getting Started
- **[README.md](README.md)** - Project overview and quick start
- **[GETTING_STARTED.md](GETTING_STARTED.md)** - Complete installation guide
- **[CHANGELOG.md](CHANGELOG.md)** - Release history and milestones

### 🏗️ Architecture & Design
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and component architecture
- **[PROJECT_STATUS.md](PROJECT_STATUS.md)** - Feature status and deprecations

## Integration Guides

### 🔧 Kubernetes Management (NEW)
- **[MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md)** - Complete MCP setup
  - Tool discovery workflow
  - 22 Kubernetes tools reference
  - Protocol details and examples
  - LLM agent integration patterns

- **[docs/K8S_SYNC_DRIVER_GUIDE.md](docs/K8S_SYNC_DRIVER_GUIDE.md)** - Real-time K8s monitoring
  - Kubernetes sync driver setup
  - Resource vectorization
  - Qdrant integration

### 🤖 AI/ML Integration
- **[docs/VLM2VEC_EMBEDDING_GUIDE.md](docs/VLM2VEC_EMBEDDING_GUIDE.md)** - Vector embeddings
  - Embedding models
  - Dimension management
  - Batch processing

- **[TRITON_INTEGRATION_SUMMARY.md](TRITON_INTEGRATION_SUMMARY.md)** - Triton server setup
  - Model deployment
  - Performance tuning
  - Production configuration

- **[TRITON_QUICKSTART.md](TRITON_QUICKSTART.md)** - Quick Triton setup
- **[agent/serving/triton/docker/README.md](agent/serving/triton/docker/README.md)** - Docker deployment

## Client Implementation

### 🐍 Python MCP Client
- **[agent/client/mcp_python/README.md](agent/client/mcp_python/README.md)** - Protocol documentation
- **[agent/client/mcp_python/IMPLEMENTATION_SUMMARY.md](agent/client/mcp_python/IMPLEMENTATION_SUMMARY.md)** - Implementation details
- **[agent/client/mcp_python/TEST_PODS.md](agent/client/mcp_python/TEST_PODS.md)** - Tool invocation tests

### 🦀 Rust MCP Client
- **[agent/client/mcp/src/main.rs](agent/client/mcp/src/main.rs)** - Rust implementation (async/tokio)

### 🎨 VS Code Extension
- **[agent/client/extensions/vscode/README.md](agent/client/extensions/vscode/README.md)** - Extension development

## Component Guides

### Backend Services
- **[agent/serving/fastapi/](agent/serving/fastapi/)** - FastAPI REST API
  - Chat endpoint (`/chat`)
  - Embedding endpoint (`/embed`)
  - Health checks

### Kubernetes Integration
- **[agent/memory/k8s2vector/](agent/memory/k8s2vector/)** - Real-time K8s sync
  - Resource collection
  - Change detection
  - Vector DB updates

### Vector Database
- **[agent/memory/legacy/](agent/memory/legacy/)** - Embedding and retrieval
  - `embeddings.py` - Model implementations
  - `vector_store.py` - Qdrant integration
  - `retriever.py` - Search and filtering
  - `chunking.py` - Document preprocessing

## Deprecated / Archived

| Document | Reason | Replacement |
|----------|--------|-------------|
| `_DEPRECATED_RAG_INTEGRATION_PLAN.md` | Original planning doc | [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md) |
| `RAG_INTEGRATION_PLAN.md` | Superseded by MCP approach | [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md) |

## Quick Navigation

### By Role

**For DevOps/SRE:**
1. [GETTING_STARTED.md](GETTING_STARTED.md) - Setup
2. [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md) - K8s tool management
3. [docs/K8S_SYNC_DRIVER_GUIDE.md](docs/K8S_SYNC_DRIVER_GUIDE.md) - Monitoring

**For ML Engineers:**
1. [ARCHITECTURE.md](ARCHITECTURE.md) - System design
2. [docs/VLM2VEC_EMBEDDING_GUIDE.md](docs/VLM2VEC_EMBEDDING_GUIDE.md) - Embeddings
3. [TRITON_INTEGRATION_SUMMARY.md](TRITON_INTEGRATION_SUMMARY.md) - Model serving

**For Developers:**
1. [README.md](README.md) - Overview
2. [ARCHITECTURE.md](ARCHITECTURE.md) - Component details
3. [agent/client/mcp_python/README.md](agent/client/mcp_python/README.md) - MCP protocol
4. [agent/client/extensions/vscode/README.md](agent/client/extensions/vscode/README.md) - Extension dev

**For LLM/Agent Developers:**
1. [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md) - Tool integration
2. [agent/client/mcp_python/README.md](agent/client/mcp_python/README.md) - Protocol details
3. [PROJECT_STATUS.md](PROJECT_STATUS.md) - Current status

### By Topic

**Getting Oriented:**
- [README.md](README.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [PROJECT_STATUS.md](PROJECT_STATUS.md)

**Installation & Deployment:**
- [GETTING_STARTED.md](GETTING_STARTED.md)
- [TRITON_INTEGRATION_SUMMARY.md](TRITON_INTEGRATION_SUMMARY.md)
- [agent/serving/triton/docker/README.md](agent/serving/triton/docker/README.md)

**Kubernetes Integration:**
- [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md)
- [docs/K8S_SYNC_DRIVER_GUIDE.md](docs/K8S_SYNC_DRIVER_GUIDE.md)

**AI/ML Configuration:**
- [docs/VLM2VEC_EMBEDDING_GUIDE.md](docs/VLM2VEC_EMBEDDING_GUIDE.md)
- [TRITON_INTEGRATION_SUMMARY.md](TRITON_INTEGRATION_SUMMARY.md)

**Development & Testing:**
- [agent/client/mcp_python/](agent/client/mcp_python/) - MCP client implementation
- [agent/client/extensions/vscode/](agent/client/extensions/vscode/) - Extension code

## Key Features Overview

| Feature | Docs | Status |
|---------|------|--------|
| Qwen3-VL Inference | [ARCHITECTURE.md](ARCHITECTURE.md) | ✅ Production |
| Qdrant Vector DB | [docs/VLM2VEC_EMBEDDING_GUIDE.md](docs/VLM2VEC_EMBEDDING_GUIDE.md) | ✅ Production |
| K8s Sync Driver | [docs/K8S_SYNC_DRIVER_GUIDE.md](docs/K8S_SYNC_DRIVER_GUIDE.md) | ✅ Production |
| MCP Tool Discovery | [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md) | ✅ Complete |
| LLM Agent | [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md) | 🔄 In Progress |
| VS Code Extension | [agent/client/extensions/vscode/README.md](agent/client/extensions/vscode/README.md) | ✅ Beta |

## Search Tips

- **Kubernetes tools?** → See "Tool Catalog (22 Tools)" in [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md)
- **How does inference work?** → See "Inference Layer" in [ARCHITECTURE.md](ARCHITECTURE.md)
- **Session ID mechanism?** → See "Session Management" in [MCP_INTEGRATION_GUIDE.md](MCP_INTEGRATION_GUIDE.md)
- **Installation steps?** → See [GETTING_STARTED.md](GETTING_STARTED.md)
- **What changed recently?** → See [CHANGELOG.md](CHANGELOG.md)
- **Feature status?** → See [PROJECT_STATUS.md](PROJECT_STATUS.md)

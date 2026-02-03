# System Architecture

Triton AI Chat is a **disaggregated AI system** with clear separation between inference, memory, caching, and client layers.

## High-Level Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ CLIENT LAYER                                                   │
│ ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐│
│ │  VS Code Ext     │  │  Web UI (Future) │  │  CLI (Future)  ││
│ └────────┬─────────┘  └────────┬─────────┘  └────────┬────────┘│
└─────────┼──────────────────────┼──────────────────────┼────────┘
          │ REST API (port 8000)                        │
          │
      ┌───┴────────────────────────────────────────────┐
      │ FastAPI Backend (agent/serving/fastapi)        │
      │ - Chat endpoints (/chat, /embed)               │
      │ - Model server health checks                   │
      │ - Response formatting                          │
      └───┬────────────────────────────────────────────┘
          │
      ┌───┴────────────────────────────────────────────┐
      │ INFERENCE LAYER                                │
      │ ┌──────────────────────────────────────────────┤
      │ │ Qwen3-VL-8B Model                            │
      │ │ - 8 billion parameters                       │
      │ │ - Vision-Language understanding              │
      │ │ - int4 quantization (5-6GB VRAM)             │
      │ │ - GPU-accelerated inference                  │
      │ └──────────────────────────────────────────────┤
      └───┬────────────────────────────────────────────┘
          │
          ├─ Qdrant (Vector DB) ─ RAG Context Retrieval
          │  - 4096-dim embeddings
          │  - HNSW indexing
          │  - Scalar quantization (75% compression)
          │
          ├─ Redis (Cache) ─ Sub-5ms Responses
          │  - Embedding cache
          │  - Query results cache
          │  - LRU eviction
          │
          └─ K8s Sync Driver (Rust) ─ Live Resource Ingestion
             - Real-time cluster monitoring
             - Deterministic deduplication
             - Change detection
```

---

## Components

### 1. Client Layer

#### VS Code Extension (`agent/client/extensions/vscode`)
- TypeScript-based extension
- WebView for chat UI
- REST API communication with FastAPI backend
- Real-time health monitoring
- Message history management

### 2. FastAPI Backend (`agent/serving/fastapi`)

Thin REST API layer for client communication:

**Endpoints:**
- `POST /chat` - Chat with AI (single or batch messages)
- `POST /embed` - Get embeddings for text/images
- `GET /health` - Server health status
- `GET /docs` - Interactive API documentation

**Responsibilities:**
- Route requests to inference engine
- Aggregate responses from RAG system
- Format responses for clients
- Track performance metrics

### 3. Inference Layer

#### Model Loading (`agent/serving/model_server.py`)

**Strategies:**

| Strategy | Best For | VRAM | Speed |
|----------|----------|------|-------|
| Native (Transformers) | Development, budget systems | 5-16GB | Baseline |
| vLLM | Production, high throughput | 15-19GB | 3-5x faster |
| TensorRT-LLM | Optimized inference | Varies | Fastest |

**Quantization:**
- `int4` (BitsAndBytes): 5-6GB VRAM, good quality
- `int8` (BitsAndBytes): 8-10GB VRAM, very good quality
- `none`: 14-16GB VRAM, best quality
- `awq`/`gptq` (vLLM only): Requires pre-quantized model

#### Qwen3-VL-8B Model

**Capabilities:**
- Vision understanding (images via base64)
- Language generation (text)
- Embedding extraction (4096-dimensional vectors)
- Multimodal reasoning
- Tool orchestration via MCP integration

**Inference Modes:**
1. **Generate**: Text generation for chat responses
2. **Embed**: Vector extraction for RAG embeddings
3. **Tool Context**: Kubernetes management with MCP tools (NEW)

### 4. Tool Layer - Kubernetes Management (NEW)

#### MCP (Model Context Protocol) Integration

**Architecture:**
```
┌──────────────────────────────┐
│  Qwen3-VL + Tool Context     │  ← 22 K8s tools in system prompt
└──────────────────┬───────────┘
                   │ Structured tool calls
                   ▼
          ┌─────────────────────┐
          │ Tool Executor       │  ← Python/Rust MCP client
          │ (Validates params)  │
          └─────────────┬───────┘
                        │ HTTP + Session ID
                        ▼
          ┌──────────────────────────────┐
          │ kuberntest-mcp-server:8080   │  ← MCP server
          └─────────────┬────────────────┘
                        │ kubectl commands
                        ▼
          ┌──────────────────────────────┐
          │ Kubernetes Cluster API       │
          └──────────────────────────────┘
```

**Tool Catalog (22 Tools):**
- Pod operations: list, get, delete, exec, log, run, top
- Resource management: create, update, delete, get, list, scale
- Cluster monitoring: nodes (log, stats, top), events
- Helm charts: install, list, uninstall
- Configuration: kubeconfig access

**MCP Protocol:**
- HTTP POST with JSON-RPC
- Session state via `Mcp-Session-Id` header
- Server-Sent Events (SSE) response format
- Deterministic parameter validation

**Clients:**
- Python: `/agent/client/mcp_python/mcp_client.py` (requests library)
- Rust: `/agent/client/mcp/src/main.rs` (reqwest + tokio)

**Tool Flow Example:**
```
User: "Restart all failed pods"
  ↓
LLM: "Call pods_list(fieldSelector='status.phase=Failed')"
  ↓
Executor: Send to MCP server
  ↓
MCP Server: Execute kubectl, return pod list
  ↓
LLM: "Call pods_delete for each failed pod"
  ↓
Executor: Execute deletions
  ↓
LLM: "Verify pods are running"
  ↓
Summary: "Successfully restarted 3 pods"
```

### 5. Memory & Retrieval

#### Embeddings (`agent/memory/embeddings.py`)

**Implementations:**
- `VLM2VecEmbeddings`: Extract from Qwen3-VL encoder
- `TritonEmbeddings`: Triton server-based embeddings (production)
- `SentenceTransformerEmbeddings`: Alternative encoder

**Features:**
- 4096-dimensional vectors (Qwen3-VL)
- Optional PCA reduction to 768 dimensions
- Multimodal support (text + images)
- Batch processing up to 32 items

#### Vector Store (`agent/memory/vector_store.py`)

**Qdrant Configuration:**
- HNSW indexing (m=16, ef_construct=200)
- Scalar quantization (INT8 for 75% compression)
- Cosine similarity search
- Async operations

**Storage:**
- ~60-100MB per 10,000 documents (with quantization)
- Grows linearly with collection size

#### Retriever (`agent/memory/retriever.py`)

**Process:**
1. Embed user query (single document)
2. Search Qdrant for top-K similar vectors
3. Filter by score threshold (default 0.7)
4. Format context for LLM prompt

**Performance:**
- Search latency: 10-20ms
- End-to-end retrieval: 120-150ms (including embedding)
- Cache hit: <5ms (Redis)

#### Document Chunking (`agent/memory/chunking.py`)

**Strategy:**
- Token-aware chunking with tiktoken
- Text: ~300 tokens with 50-token overlap
- Code: ~500 tokens at function/class boundaries
- Metadata preservation (source, type, etc.)

### 5. Caching Layer

#### Redis Cache

**Stores:**
- Computed embeddings (queries, documents)
- Vector search results
- Model responses (optional)

**Features:**
- Sub-5ms response time for cache hits
- LRU eviction (configurable TTL)
- Async operations

**Typical hit rate:** 40-60% depending on query patterns

### 6. K8s Sync Driver (Rust)

**Purpose:** Real-time synchronization of Kubernetes resources into vector DB

**Architecture:**
- `K8sResourceCollector`: Discovers and watches resources
- `ResourcesChunker`: Converts resources to embeddable chunks
- Deterministic ID generation: SHA256(resource.uid + content)

**Features:**
- Initial snapshot collection (<5s for typical cluster)
- Watch API for real-time updates (~100ms latency)
- Namespace filtering (excludes system namespaces)
- Resource kind filtering (excludes Leases, Events)

See [docs/K8S_SYNC_DRIVER_GUIDE.md](docs/K8S_SYNC_DRIVER_GUIDE.md) for details.

---

## Data Flow

### Chat Request Flow

```
User Message (VS Code)
    ↓
    REST API → /chat endpoint
    ↓
    Embed Query (Qwen3-VL or Triton)
    ├─ Check Redis cache
    └─ If miss: compute embedding
    ↓
    Search Qdrant (vector DB)
    ├─ HNSW index search
    └─ Filter by score threshold
    ↓
    Format Context (top-K docs)
    ↓
    Augment Prompt: [system] + [context] + [user query]
    ↓
    Generate Response (Qwen3-VL)
    ├─ Token streaming for real-time feedback
    └─ Cache response in Redis
    ↓
    Return Response
    ↓
    Display in VS Code
```

### Embedding Ingestion Flow

```
Document (text/code/image)
    ↓
    Chunk (token-aware)
    ├─ Text: ~300 tokens + overlap
    └─ Code: ~500 tokens at boundaries
    ↓
    Generate Deterministic ID: SHA256(source_uid + content_hash)
    ↓
    Embed Chunk (Qwen3-VL or Triton)
    ├─ Check Redis cache
    └─ If miss: compute embedding
    ↓
    UPSERT to Qdrant
    ├─ Same ID = update (no manual deletion needed)
    └─ New ID = insert
    ↓
    Store in Vector DB (with quantization)
```

### K8s Resource Sync Flow

```
Kubernetes Cluster
    ↓
    Initial Discovery (collect all resources)
    ├─ Filter by namespace (exclude kube-system)
    └─ Filter by kind (exclude Leases, Events)
    ↓
    Chunk Each Resource
    ├─ YAML representation
    ├─ Metadata extraction
    └─ Deterministic ID: SHA256(uid + content)
    ↓
    Embed Chunks (Triton embeddings)
    ├─ Batch up to 32
    └─ 50-100 items/sec throughput
    ↓
    UPSERT to Qdrant
    ├─ Automatic deduplication
    └─ Incremental updates
    ↓
    Watch API for Changes
    ├─ ~100ms event latency
    └─ Only diffs processed
```

---

## Resource Requirements

### Minimum (Budget System)
- **GPU**: 5-6GB VRAM
- **System RAM**: 8-10GB
- **Disk**: 25GB (model + embeddings)
- **Strategy**: Native + int4 quantization

### Recommended (Balanced)
- **GPU**: 10-12GB VRAM
- **System RAM**: 16-24GB
- **Disk**: 30GB (model + cache + embeddings)
- **Strategy**: Native + int4, or vLLM + none

### Production (High Throughput)
- **GPU**: 24GB VRAM (H100/A100/RTX 6000)
- **System RAM**: 32GB+
- **Disk**: 50GB+ (larger cache)
- **Strategy**: vLLM + quantized or FP8

### Storage Breakdown
| Component | Size | Notes |
|-----------|------|-------|
| Qwen3-VL (int4) | 10-12GB | Model weights |
| Qdrant (10k docs) | 600MB | With quantization |
| Redis cache | 50-500MB | Varies with TTL |
| Logs | 1GB/month | Depends on queries |

---

## Performance Characteristics

### Inference Latency
| Operation | Latency | Throughput |
|-----------|---------|------------|
| Text embedding | ~100ms | 100-200/sec |
| Image embedding | ~300ms | 30-50/sec |
| Text generation (128 tokens) | 0.5-1s | 1-2/sec |
| Text generation (512 tokens) | 2-5s | 0.2-0.5/sec |
| Vector search | 10-20ms | Very high |

### End-to-End Chat
- **Without RAG**: 0.5-5s (generation only)
- **With RAG cache hit**: 50-100ms (cache + generation)
- **With RAG cache miss**: 200-300ms (embed + search + generation)

### Throughput
- **Single GPU**: 50-100 requests/min (sequential)
- **With batching**: 200-500 requests/min (parallel)
- **Vector search**: 1000+ queries/sec (Qdrant)

---

## Scalability Considerations

### Horizontal Scaling

1. **Multiple Model Servers**: Load balance inference
2. **Distributed Qdrant**: Sharding across nodes
3. **Redis Cluster**: High availability caching
4. **K8s Operators**: Automated deployment

### Vertical Scaling

1. **Larger GPU**: Better for batch inference
2. **More System RAM**: Higher Redis cache
3. **SSD Storage**: Faster vector DB operations

### Optimization Strategies

1. **Batch Processing**: Group requests (up to 32)
2. **Caching**: Redis for embeddings and results
3. **Quantization**: Reduce model/index size by 75%
4. **Async I/O**: Non-blocking database operations

---

## Security Considerations

1. **API Rate Limiting**: Protect against abuse (future)
2. **Authentication**: Add token validation (future)
3. **Data Isolation**: Namespace-based filtering for K8s
4. **Model Access**: Run inference in isolated container
5. **Cache Encryption**: TLS for Redis (future)

---

## Deployment Options

### Development
```bash
# Local machine with GPU
# Single Conda environment
# Docker Compose for services
```

### Staging
```bash
# Single server with multiple GPUs
# Kubernetes deployment
# Managed Qdrant/Redis (optional)
```

### Production
```bash
# Multi-node Kubernetes cluster
# Triton Inference Server (multi-model serving)
# Distributed Qdrant (sharding)
# Redis Cluster (high availability)
# Load balancer for API
```

---

## Next Steps

- **Installation**: See [GETTING_STARTED.md](GETTING_STARTED.md)
- **Performance**: Read [TRITON_PERFORMANCE.md](docs/TRITON_PERFORMANCE.md)
- **RAG Integration**: Check [RAG_INTEGRATION_PLAN.md](docs/RAG_INTEGRATION_PLAN.md)
- **K8s Sync**: Explore [docs/K8S_SYNC_DRIVER_GUIDE.md](docs/K8S_SYNC_DRIVER_GUIDE.md)

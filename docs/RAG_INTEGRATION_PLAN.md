# ⚠️ DEPRECATED: RAG Integration Plan

**Status:** DEPRECATED as of February 1, 2026

**Replacement:** See [MCP Tool Discovery & Integration](#) for current Kubernetes management approach.

---

## Previous Overview (Archived)
This document outlined a phased approach to integrate Retrieval-Augmented Generation (RAG) into the Triton AI Chat system using VLM2Vec embeddings for multimodal (text + image) retrieval.

## Migration Notes
- ✅ Kubernetes resource sync driver active (K8sResourceCollector in Rust)
- ✅ Real-time vector DB updates implemented (Qdrant)
- ✅ MCP tool discovery completed (22 Kubernetes tools)
- 🔄 LLM agent integration for tool orchestration in progress
- 🔄 VLM2Vec embedding pipeline deferred (focus on tool-based operations first)

## Architecture Goals
- Store knowledge materials (documents, code examples, diagrams) in vector database
- Use VLM2Vec to create multimodal embeddings
- Enhance Qwen3-VL responses with relevant retrieved context
- Support both text and visual explanations

---

## Phase 1: Foundation Setup (Week 1-2)

### 1.1 Choose Vector Database
**Options:**
- **ChromaDB** (Recommended for starting): Lightweight, local-first, easy Python integration
- **Weaviate**: Production-grade with multimodal support
- **Qdrant**: High performance, good for large scale
- **Milvus**: Enterprise-grade, scalable

**Decision Criteria:**
- Start with ChromaDB for rapid prototyping
- Migration path to Weaviate/Qdrant for production

### 1.2 Setup Dependencies
```bash
# Add to requirements.txt
chromadb>=0.4.0              # Vector database
sentence-transformers>=2.2.0  # For text embeddings (optional baseline)
langchain>=0.1.0             # RAG orchestration
langchain-community>=0.0.10  # Community integrations
tiktoken>=0.5.0              # Token counting for chunking
```

### 1.3 Create Memory Module Structure
```
agent/memory/
├── __init__.py
├── vector_store.py          # VectorDB interface
├── embeddings.py            # VLM2Vec embedding generation
├── chunking.py              # Document/code chunking
├── retriever.py             # Retrieval logic
└── config.py                # RAG configuration
```

### 1.4 Docker Integration
- Add ChromaDB service to docker-compose.yml
- Configure persistent volume for vector store
- Add health checks

**Tasks:**
- [ ] Install ChromaDB and dependencies
- [ ] Create `agent/memory/` module structure
- [ ] Add ChromaDB service to Docker Compose
- [ ] Create configuration for embedding dimensions

---

## Phase 2: Embedding Pipeline (Week 2-3)

### 2.1 VLM2Vec Integration
**Options for VLM2Vec:**
- Use Qwen3-VL itself for embeddings (extract hidden states)
- Use dedicated VLM embedding model (e.g., OpenCLIP, BridgeTower)
- Use text-only embeddings initially, add vision later

**Recommended Approach:**
1. Start with text embeddings (sentence-transformers)
2. Add VLM2Vec for multimodal later
3. Use Qwen3-VL's encoder outputs as embeddings

### 2.2 Implement Embedding Service
```python
# agent/memory/embeddings.py
class EmbeddingService:
    def embed_text(self, text: str) -> List[float]:
        """Generate text embedding"""
        
    def embed_multimodal(self, text: str, image: Optional[Image]) -> List[float]:
        """Generate multimodal embedding with VLM2Vec"""
        
    def embed_batch(self, items: List[Dict]) -> List[List[float]]:
        """Batch embedding for efficiency"""
```

### 2.3 Document Chunking Strategy
- **Code chunks**: Function/class level (~500 tokens)
- **Text chunks**: Semantic paragraphs (~300 tokens)
- **Image chunks**: Diagram + caption pairs
- Overlap: 50 tokens between chunks

**Tasks:**
- [ ] Implement text embedding service
- [ ] Create chunking utilities for code and text
- [ ] Design multimodal chunking (text + image pairs)
- [ ] Add batch processing for efficient embedding

---

## Phase 3: Knowledge Base Creation (Week 3-4)

### 3.1 Curate Knowledge Base
**Content Sources:**
- Algorithm explanations (sorting, searching, graphs, trees, DP)
- Code implementations (Python, Java, C++)
- Complexity analysis documents
- Algorithm visualizations/diagrams
- LeetCode-style problem explanations

### 3.2 Build Ingestion Pipeline
```python
# agent/memory/ingestion.py
class DocumentIngestion:
    def ingest_directory(self, path: str):
        """Ingest all documents from directory"""
        
    def ingest_code_file(self, filepath: str):
        """Parse and chunk code files"""
        
    def ingest_markdown_with_images(self, md_file: str):
        """Parse markdown + extract/embed images"""
```

### 3.3 Vector Store Operations
```python
# agent/memory/vector_store.py
class VectorStore:
    def add_documents(self, chunks: List[Dict]):
        """Add document chunks to vector DB"""
        
    def search(self, query_embedding: List[float], top_k: int = 5):
        """Semantic search"""
        
    def search_multimodal(self, text: str, image: Optional[Image], top_k: int = 5):
        """Multimodal semantic search"""
```

**Tasks:**
- [ ] Curate initial knowledge base (20-30 documents)
- [ ] Implement ingestion pipeline
- [ ] Create vector store interface
- [ ] Populate ChromaDB with initial knowledge

---

## Phase 4: Retrieval Integration (Week 4-5)

### 4.1 Create Retriever Service
```python
# agent/memory/retriever.py
class RAGRetriever:
    def retrieve_context(
        self, 
        query: str, 
        image: Optional[Image] = None,
        top_k: int = 3
    ) -> List[Dict]:
        """Retrieve relevant context for query"""
        
    def rerank_results(self, query: str, results: List[Dict]) -> List[Dict]:
        """Rerank retrieved results for relevance"""
        
    def format_context_for_llm(self, results: List[Dict]) -> str:
        """Format retrieved docs for LLM prompt"""
```

### 4.2 Retrieval Strategies
- **Dense retrieval**: Pure vector similarity
- **Hybrid retrieval**: Vector + keyword (BM25)
- **Re-ranking**: Use cross-encoder for top results
- **Metadata filtering**: Filter by algorithm type, difficulty

### 4.3 Context Injection
Modify inference engine to inject retrieved context:
```python
# In inference_engine.py
async def process_with_rag(
    self,
    message: str,
    image_base64: Optional[str],
    model,
    processor
) -> str:
    # 1. Retrieve relevant context
    context = await self.retriever.retrieve_context(message, image)
    
    # 2. Format prompt with context
    augmented_message = f"""Context:
{context}

User Question: {message}

Please answer using the provided context."""
    
    # 3. Generate response
    return await self.process_native(augmented_message, image_base64, model, processor)
```

**Tasks:**
- [ ] Implement retriever service
- [ ] Add RAG-enabled endpoint to FastAPI server
- [ ] Modify inference engine to support RAG
- [ ] Test retrieval quality with sample queries

---

## Phase 5: API Integration (Week 5-6)

### 5.1 Update FastAPI Endpoints
```python
# New endpoints in model_server.py

@app.post("/chat/rag")
async def chat_with_rag(request: ChatRequest):
    """Chat endpoint with RAG enhancement"""
    
@app.post("/knowledge/add")
async def add_knowledge(documents: List[DocumentRequest]):
    """Add new documents to knowledge base"""
    
@app.get("/knowledge/search")
async def search_knowledge(query: str, top_k: int = 5):
    """Direct knowledge base search"""
```

### 5.2 Update VS Code Extension
- Add toggle for RAG-enhanced responses
- Show retrieved sources in chat
- Allow users to add code snippets to knowledge base

**Tasks:**
- [ ] Create RAG-enabled API endpoints
- [ ] Update VS Code extension to use RAG endpoint
- [ ] Add UI controls for RAG features
- [ ] Implement source attribution in responses

---

## Phase 6: VLM2Vec Enhancement (Week 6-7)

### 6.1 Multimodal Embedding Implementation
**Options:**
1. **Use Qwen3-VL encoder**: Extract embeddings from model's vision-text encoder
2. **Dedicated VLM2Vec model**: Use specialized multimodal embedding model
3. **Hybrid approach**: Text embeddings + separate image embeddings

### 6.2 Integrate Multimodal Search
- Support diagram/flowchart upload in queries
- Retrieve algorithm visualizations
- Match code snippets with visual explanations

### 6.3 Optimize Performance
- Batch embedding generation
- Caching for frequent queries
- Async retrieval to avoid blocking

**Tasks:**
- [ ] Implement VLM2Vec embeddings using Qwen3-VL
- [ ] Add multimodal search capabilities
- [ ] Test with algorithm diagrams and code pairs
- [ ] Benchmark retrieval latency

---

## Phase 7: Production Optimization (Week 7-8)

### 7.1 Performance Tuning
- Optimize chunk sizes and overlap
- Tune top-k retrieval parameters
- Implement query caching
- Add retrieval metrics/logging

### 7.2 Evaluation & Quality
- Create test set of questions for knowledge retrieval
- Measure retrieval precision/recall
- A/B test RAG vs non-RAG responses
- Collect user feedback

### 7.3 Scalability
- Consider migration to Weaviate/Qdrant
- Add horizontal scaling for retrieval
- Implement rate limiting
- Add monitoring/observability

**Tasks:**
- [ ] Benchmark end-to-end latency
- [ ] Create evaluation dataset
- [ ] Measure RAG quality metrics
- [ ] Document performance characteristics

---

## Phase 8: Advanced Features (Future)

### 8.1 Dynamic Knowledge Updates
- Auto-ingest new algorithm tutorials
- User-contributed code examples
- Continuous learning from user interactions

### 8.2 Personalized Retrieval
- User skill level-based filtering
- Learning progress tracking
- Personalized algorithm recommendations

### 8.3 Multi-Index Strategy
- Separate indices for different domains (algorithms, data structures, complexity)
- Hierarchical retrieval (coarse → fine)
- Graph-based knowledge representation

---

## Technical Considerations

### Embedding Dimensions
- **Text embeddings**: 384-768 dimensions (sentence-transformers)
- **VLM2Vec**: 512-1024 dimensions (depends on model)
- **Trade-off**: Higher dims = better accuracy, more storage/compute

### Chunk Size Guidelines
- **Code**: 200-500 tokens (function/class level)
- **Text**: 250-400 tokens (paragraph level)
- **Overlap**: 20-50 tokens
- **Images**: Keep with relevant text context

### Prompt Engineering for RAG
```
System: You are a helpful AI assistant. Use the provided context to answer questions accurately.

Context:
[Retrieved chunks here]

Rules:
1. Base answers primarily on provided context
2. Cite sources when using specific information
3. Acknowledge if context doesn't contain answer
4. Combine context knowledge with your general understanding

User: [question]
```

---

## Success Metrics

### Retrieval Quality
- **Precision@k**: Relevant docs in top-k results
- **Recall@k**: Coverage of relevant information
- **MRR (Mean Reciprocal Rank)**: Position of first relevant result

### End-User Impact
- **Response accuracy**: Correctness of answers
- **Response time**: Latency with RAG enabled
- **User satisfaction**: Explicit feedback ratings
- **Knowledge coverage**: % queries with relevant retrieval

### System Performance
- **Embedding latency**: Time to generate embeddings
- **Retrieval latency**: Time to search vector DB
- **End-to-end latency**: Total response time
- **Storage efficiency**: Vector DB size vs knowledge coverage

---

## Resource Requirements

### Storage
- **Vector DB**: ~1-2GB for 10k chunks
- **Raw documents**: ~500MB for comprehensive knowledge library
- **Model weights**: 4-5GB for VLM2Vec (if separate)

### Compute
- **Embedding generation**: GPU preferred, CPU acceptable
- **Vector search**: CPU sufficient for <100k vectors
- **LLM inference**: Existing GPU setup (Qwen3-VL)

### Development Time
- **MVP (Phases 1-4)**: 4-5 weeks
- **Production-ready (Phases 1-7)**: 7-8 weeks
- **Advanced features (Phase 8)**: Ongoing

---

## Getting Started

### Immediate Next Steps (This Week)

1. **Install ChromaDB**:
   ```bash
   pip install chromadb
   ```

2. **Create memory module**:
   ```bash
   mkdir -p agent/memory
   touch agent/memory/__init__.py
   ```

3. **Prototype text embeddings**:
   - Use sentence-transformers for quick start
   - Test with 10-20 algorithm explanations

4. **Proof of concept**:
   - Simple retrieval demo
   - Compare RAG vs non-RAG responses

### Key Decision Points

**Week 2**: Text-only vs multimodal first?
- Recommend: Start text-only, add VLM2Vec in Phase 6

**Week 4**: ChromaDB vs production database?
- Recommend: Stick with ChromaDB unless >100k vectors

**Week 6**: Custom VLM2Vec vs Qwen3-VL encoder?
- Recommend: Try Qwen3-VL encoder first (already loaded)

---

## References & Resources

### Vector Databases
- [ChromaDB Docs](https://docs.trychroma.com/)
- [Weaviate Multimodal](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/multi2vec-clip)

### Embeddings
- [Sentence Transformers](https://www.sbert.net/)
- [VLM2Vec concepts](https://arxiv.org/abs/2305.01287)

### RAG Frameworks
- [LangChain RAG Tutorial](https://python.langchain.com/docs/use_cases/question_answering/)
- [LlamaIndex](https://docs.llamaindex.ai/)

### Evaluation
- [RAGAS: RAG Assessment](https://github.com/explodinggradients/ragas)
- [BEIR Benchmark](https://github.com/beir-cellar/beir)

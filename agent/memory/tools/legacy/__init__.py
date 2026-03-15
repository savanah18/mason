"""
Memory module for RAG (Retrieval-Augmented Generation).

This module provides components for:
- Document chunking (text and code)
- Vector embeddings (VLM2Vec from Qwen3-VL)
- Vector storage (Qdrant with optimizations)
- Context retrieval (with caching and reranking)

Quick Start:
    >>> from agent.memory import create_rag_system
    >>> 
    >>> # Initialize RAG system
    >>> rag = await create_rag_system(model, processor)
    >>> 
    >>> # Retrieve context
    >>> results = await rag.retrieve("Explain quicksort")
    >>> context = rag.format_context(results)
"""

from .config import (
    RAGConfig,
    EmbeddingConfig,
    QdrantConfig,
    RetrieverConfig,
    CacheConfig,
    ChunkingConfig,
    get_rag_config
)

from .embeddings import (
    VLM2VecEmbeddings,
    TritonEmbeddings,
    SentenceTransformerEmbeddings,
    create_embedding_service
)

from .vector_store import (
    QdrantVectorStore,
    SyncQdrantVectorStore
)

from .chunking import (
    TextChunker,
    CodeChunker,
    Chunk,
    create_chunker
)

from .retriever import (
    RAGRetriever,
    simple_retrieve
)


__all__ = [
    # Configuration
    "RAGConfig",
    "EmbeddingConfig",
    "QdrantConfig",
    "RetrieverConfig",
    "CacheConfig",
    "ChunkingConfig",
    "get_rag_config",
    
    # Embeddings
    "VLM2VecEmbeddings",
    "TritonEmbeddings",
    "SentenceTransformerEmbeddings",
    "create_embedding_service",
    
    # Vector Store
    "QdrantVectorStore",
    "SyncQdrantVectorStore",
    
    # Chunking
    "TextChunker",
    "CodeChunker",
    "Chunk",
    "create_chunker",
    
    # Retrieval
    "RAGRetriever",
    "simple_retrieve",
    
    # Factory
    "create_rag_system",
]


# Factory function for complete RAG system
async def create_rag_system(
    model=None,
    processor=None,
    config: RAGConfig = None,
    use_triton: bool = True,
    triton_url: str = "localhost:8000"
):
    """
    Create a complete RAG system with all components initialized.
    
    Args:
        model: Qwen3-VL model instance (required if use_triton=False)
        processor: Qwen3-VL processor instance (required if use_triton=False)
        config: Optional RAGConfig (uses defaults if None)
        use_triton: If True, use Triton server for embeddings (recommended)
        triton_url: Triton server URL (if use_triton=True)
        
    Returns:
        RAGRetriever instance ready to use
        
    Example (with Triton - recommended):
        >>> from agent.memory import create_rag_system
        >>> 
        >>> # Create RAG system with Triton
        >>> rag = await create_rag_system(use_triton=True)
        >>> 
        >>> # Use it
        >>> results = await rag.retrieve_context("Explain binary search")
        >>> context = rag.format_context_for_llm(results)
    
    Example (with local model):
        >>> from agent.memory import create_rag_system
        >>> from agent.serving.fastapi.src.model_loader import ModelLoader
        >>> 
        >>> # Load model
        >>> model, processor = ModelLoader.load_native(
        >>>     model_path="Qwen/Qwen3-VL-8B-Instruct",
        >>>     quantization_type="int4",
        >>>     attention_impl="sdpa"
        >>> )
        >>> 
        >>> # Create RAG system
        >>> rag = await create_rag_system(model, processor, use_triton=False)
    """
    if config is None:
        config = get_rag_config()
    
    # Create embedding service
    if use_triton:
        embedder = TritonEmbeddings(triton_url=triton_url)
        print(f"✓ Using Triton server at {triton_url}")
    else:
        if model is None or processor is None:
            raise ValueError("model and processor required when use_triton=False")
        embedder = VLM2VecEmbeddings(
            model=model,
            processor=processor,
            pooling_strategy=config.embedding.pooling_strategy,
            normalize=config.embedding.normalize
        )
        print("✓ Using local VLM2Vec embeddings")
    
    # Create vector store
    vector_store = QdrantVectorStore(config.qdrant)
    await vector_store.initialize()
    
    # Create retriever
    retriever = RAGRetriever(
        embedder=embedder,
        vector_store=vector_store,
        config=config.retriever,
        cache_config=config.cache if config.cache.enabled else None
    )
    
    print("✓ RAG system initialized successfully")
    print(f"  - Embedding dimension: {embedder.get_embedding_dimension()}")
    print(f"  - Vector store: {config.qdrant.collection_name}")
    print(f"  - Cache: {'Enabled' if config.cache.enabled else 'Disabled'}")
    
    return retriever


__version__ = "0.1.0"

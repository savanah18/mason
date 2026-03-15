"""
RAG configuration with optimized settings for Qdrant, embeddings, and caching.
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation."""
    
    # Embedding dimensions
    vlm2vec_dim: int = 4096  # Qwen3-VL hidden size
    target_dim: Optional[int] = None  # Optional PCA reduction (e.g., 768)
    
    # Pooling strategy
    pooling_strategy: str = "mean"  # Options: mean, cls, max, last
    normalize: bool = True  # L2 normalization
    
    # Batch processing
    batch_size: int = 8  # Number of items per batch
    
    # PCA settings (if dimension reduction enabled)
    use_pca: bool = False
    pca_n_components: int = 768
    pca_model_path: Optional[str] = "./data/pca_model.pkl"


@dataclass
class QdrantConfig:
    """Configuration for Qdrant vector database."""
    
    # Connection settings
    host: str = os.getenv("QDRANT_HOST", "localhost")
    port: int = int(os.getenv("QDRANT_PORT", "6333"))
    grpc_port: int = int(os.getenv("QDRANT_GRPC_PORT", "6334"))
    prefer_grpc: bool = True  # gRPC is faster than HTTP
    
    # Collection settings
    collection_name: str = "knowledge_base"
    vector_size: int = 4096  # Must match embedding dimension
    distance: str = "Cosine"  # Options: Cosine, Euclid, Dot
    
    # HNSW index optimization
    hnsw_config: dict = None
    
    # Scalar quantization for 75% storage reduction
    use_quantization: bool = True
    quantization_type: str = "scalar"  # Options: scalar, product
    
    # Performance tuning
    shard_number: int = 1
    replication_factor: int = 1
    write_consistency_factor: int = 1
    
    # Batch operations
    batch_size: int = 100  # Points to upsert per batch
    parallel_operations: int = 4  # Concurrent upload threads
    
    def __post_init__(self):
        """Initialize HNSW config with optimized defaults."""
        if self.hnsw_config is None:
            self.hnsw_config = {
                "m": 16,  # Number of edges per node (16 = balanced)
                "ef_construct": 200,  # Quality during index build
                "full_scan_threshold": 10000,  # Use exact search below this
            }


@dataclass
class RetrieverConfig:
    """Configuration for RAG retrieval."""
    
    # Search parameters
    top_k: int = 3  # Number of documents to retrieve
    score_threshold: float = 0.7  # Minimum similarity score
    
    # Search optimization
    ef_search: int = 128  # HNSW search quality (higher = better recall)
    exact_search: bool = False  # Use exact search (slower but perfect)
    
    # Reranking
    use_reranking: bool = False  # Cross-encoder reranking
    rerank_top_n: int = 10  # Retrieve more, rerank to top_k
    
    # Metadata filtering
    enable_filtering: bool = True
    filter_by: Optional[dict] = None  # e.g., {"algorithm_type": "sorting"}
    
    # Context formatting
    max_context_tokens: int = 2000  # Maximum tokens for context
    include_metadata: bool = True  # Include source info in context


@dataclass
class CacheConfig:
    """Configuration for Redis caching."""
    
    # Redis connection
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    db: int = 0
    password: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    
    # Cache settings
    enabled: bool = True
    ttl: int = 3600  # Cache TTL in seconds (1 hour)
    max_memory: str = "512mb"  # Redis max memory
    eviction_policy: str = "allkeys-lru"  # LRU eviction
    
    # Key prefixes
    embedding_cache_prefix: str = "emb:"
    query_cache_prefix: str = "qry:"
    
    # Performance
    connection_pool_size: int = 10
    socket_timeout: int = 5  # seconds


@dataclass
class ChunkingConfig:
    """Configuration for document chunking."""
    
    # Token limits
    text_chunk_size: int = 300  # Tokens per text chunk
    code_chunk_size: int = 500  # Tokens per code chunk
    overlap: int = 50  # Token overlap between chunks
    
    # Encoding
    encoding_name: str = "cl100k_base"  # tiktoken encoding
    
    # Code parsing
    code_languages: list = None  # Supported languages
    
    # Multimodal
    keep_images_with_text: bool = True
    max_image_size: tuple = (1024, 1024)  # Max image dimensions
    
    def __post_init__(self):
        """Initialize code languages."""
        if self.code_languages is None:
            self.code_languages = ["python", "java", "cpp", "javascript"]


@dataclass
class RAGConfig:
    """Master configuration for RAG system."""
    
    # Component configs
    embedding: EmbeddingConfig = None
    qdrant: QdrantConfig = None
    retriever: RetrieverConfig = None
    cache: CacheConfig = None
    chunking: ChunkingConfig = None
    
    # System settings
    enable_rag: bool = os.getenv("ENABLE_RAG", "true").lower() == "true"
    log_level: str = os.getenv("RAG_LOG_LEVEL", "INFO")
    
    # Data paths
    knowledge_base_path: str = "./data/knowledge_base"
    vector_store_path: str = "./data/qdrant"
    cache_path: str = "./data/cache"
    
    def __post_init__(self):
        """Initialize sub-configs with defaults."""
        if self.embedding is None:
            self.embedding = EmbeddingConfig()
        if self.qdrant is None:
            self.qdrant = QdrantConfig()
        if self.retriever is None:
            self.retriever = RetrieverConfig()
        if self.cache is None:
            self.cache = CacheConfig()
        if self.chunking is None:
            self.chunking = ChunkingConfig()


# Default configuration instance
default_rag_config = RAGConfig()


def get_rag_config() -> RAGConfig:
    """
    Get RAG configuration from environment variables or defaults.
    
    Returns:
        RAGConfig instance with environment-specific settings
    """
    config = RAGConfig()
    
    # Override with environment variables
    if os.getenv("EMBEDDING_DIM"):
        config.embedding.vlm2vec_dim = int(os.getenv("EMBEDDING_DIM"))
    
    if os.getenv("USE_PCA", "false").lower() == "true":
        config.embedding.use_pca = True
        config.embedding.target_dim = int(os.getenv("PCA_DIM", "768"))
        config.qdrant.vector_size = config.embedding.target_dim
    
    if os.getenv("TOP_K"):
        config.retriever.top_k = int(os.getenv("TOP_K"))
    
    if os.getenv("REDIS_ENABLED", "true").lower() == "false":
        config.cache.enabled = False
    
    return config


# Validation utilities
def validate_qdrant_config(config: QdrantConfig) -> bool:
    """Validate Qdrant configuration."""
    if config.vector_size != config.hnsw_config.get("full_scan_threshold", 10000):
        if config.vector_size > 2048:
            print("Warning: Large vector size may impact performance")
    
    if config.hnsw_config["m"] < 4 or config.hnsw_config["m"] > 64:
        raise ValueError("HNSW m parameter should be between 4 and 64")
    
    return True


def validate_embedding_config(config: EmbeddingConfig) -> bool:
    """Validate embedding configuration."""
    if config.use_pca and config.target_dim >= config.vlm2vec_dim:
        raise ValueError("PCA target_dim must be less than vlm2vec_dim")
    
    if config.pooling_strategy not in ["mean", "cls", "max", "last"]:
        raise ValueError(f"Invalid pooling strategy: {config.pooling_strategy}")
    
    return True

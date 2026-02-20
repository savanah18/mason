"""
RAG retriever with async operations, Redis caching, and context formatting.
"""

from typing import List, Dict, Any, Optional
import asyncio
import hashlib
import json
from PIL import Image

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None
    print("Warning: redis not installed. Install with: pip install redis")

from .config import RetrieverConfig, CacheConfig
from .vector_store import QdrantVectorStore
from .embeddings import VLM2VecEmbeddings


class RAGRetriever:
    """
    Retrieval-Augmented Generation retriever with caching and optimization.
    
    Features:
    - Async retrieval for non-blocking operations
    - Redis-backed query caching
    - Context formatting for LLM prompts
    - Score thresholding and filtering
    """
    
    def __init__(
        self,
        embedder: VLM2VecEmbeddings,
        vector_store: QdrantVectorStore,
        config: RetrieverConfig,
        cache_config: Optional[CacheConfig] = None
    ):
        """
        Initialize RAG retriever.
        
        Args:
            embedder: VLM2VecEmbeddings instance
            vector_store: QdrantVectorStore instance
            config: RetrieverConfig instance
            cache_config: Optional CacheConfig for Redis caching
        """
        self.embedder = embedder
        self.vector_store = vector_store
        self.config = config
        self.cache_config = cache_config
        
        # Initialize Redis cache
        self.cache = None
        if cache_config and cache_config.enabled and aioredis:
            self._init_cache()
    
    def _init_cache(self):
        """Initialize Redis cache connection."""
        try:
            self.cache = aioredis.Redis(
                host=self.cache_config.host,
                port=self.cache_config.port,
                db=self.cache_config.db,
                password=self.cache_config.password,
                socket_timeout=self.cache_config.socket_timeout,
                decode_responses=False  # We'll handle encoding
            )
            print(f"✓ Redis cache initialized at {self.cache_config.host}:{self.cache_config.port}")
        except Exception as e:
            print(f"Warning: Failed to initialize Redis cache: {e}")
            self.cache = None
    
    def _generate_cache_key(self, query: str, top_k: int, filters: Optional[Dict] = None) -> str:
        """Generate cache key for query."""
        cache_data = {
            "query": query,
            "top_k": top_k,
            "filters": filters or {}
        }
        cache_str = json.dumps(cache_data, sort_keys=True)
        hash_key = hashlib.sha256(cache_str.encode()).hexdigest()[:16]
        return f"{self.cache_config.query_cache_prefix}{hash_key}"
    
    async def _get_cached_results(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieve cached results from Redis."""
        if not self.cache:
            return None
        
        try:
            cached_data = await self.cache.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            print(f"Cache get error: {e}")
        
        return None
    
    async def _cache_results(self, cache_key: str, results: List[Dict[str, Any]]):
        """Store results in Redis cache."""
        if not self.cache:
            return
        
        try:
            await self.cache.setex(
                cache_key,
                self.cache_config.ttl,
                json.dumps(results)
            )
        except Exception as e:
            print(f"Cache set error: {e}")
    
    async def retrieve_context(
        self,
        query: str,
        image: Optional[Image.Image] = None,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: Query text
            image: Optional query image
            top_k: Number of results (uses config default if None)
            score_threshold: Minimum similarity score
            filter_conditions: Optional metadata filters
            
        Returns:
            List of relevant documents with text, metadata, and scores
        """
        top_k = top_k or self.config.top_k
        score_threshold = score_threshold or self.config.score_threshold
        
        # Check cache first (text-only queries)
        if not image and self.cache:
            cache_key = self._generate_cache_key(query, top_k, filter_conditions)
            cached_results = await self._get_cached_results(cache_key)
            if cached_results:
                print(f"✓ Cache hit for query: {query[:50]}...")
                return cached_results
        
        # Generate query embedding
        if image:
            query_embedding = self.embedder.embed_multimodal(query, image)
        else:
            query_embedding = self.embedder.embed_text(query)
        
        # Search vector store
        results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k * 2 if self.config.use_reranking else top_k,  # Get more for reranking
            score_threshold=score_threshold,
            filter_conditions=filter_conditions
        )
        
        # Rerank if enabled
        if self.config.use_reranking and len(results) > top_k:
            results = await self.rerank_results(query, results)
            results = results[:top_k]
        
        # Cache results (text-only queries)
        if not image and self.cache:
            await self._cache_results(cache_key, results)
        
        return results
    
    async def rerank_results(
        self,
        query: str,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Rerank results using cross-encoder or heuristics.
        
        Note: Cross-encoder reranking requires additional model.
        Currently implements simple heuristic reranking.
        
        Args:
            query: Original query
            results: Initial search results
            
        Returns:
            Reranked results
        """
        # Simple heuristic: boost exact keyword matches
        query_tokens = set(query.lower().split())
        
        for result in results:
            text_tokens = set(result["text"].lower().split())
            keyword_overlap = len(query_tokens & text_tokens) / len(query_tokens)
            
            # Adjust score based on keyword overlap
            result["score"] = result["score"] * (0.7 + 0.3 * keyword_overlap)
        
        # Re-sort by adjusted scores
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results
    
    def format_context_for_llm(
        self,
        results: List[Dict[str, Any]],
        include_scores: bool = False
    ) -> str:
        """
        Format retrieved documents into context string for LLM.
        
        Args:
            results: Retrieved documents
            include_scores: Whether to include similarity scores
            
        Returns:
            Formatted context string
        """
        if not results:
            return "[No relevant context found]"
        
        context_parts = ["[Retrieved Context]\n"]
        
        for i, result in enumerate(results, 1):
            text = result["text"]
            score = result["score"]
            metadata = result.get("metadata", {})
            
            # Build context entry
            entry = f"\n{i}. {text}"
            
            # Add metadata if enabled
            if self.config.include_metadata and metadata:
                meta_str = ", ".join([f"{k}: {v}" for k, v in metadata.items() if k != "created_at"])
                if meta_str:
                    entry += f"\n   [Source: {meta_str}]"
            
            # Add score if requested
            if include_scores:
                entry += f"\n   [Relevance: {score:.3f}]"
            
            context_parts.append(entry)
        
        context_parts.append("\n")
        
        return "\n".join(context_parts)
    
    def format_augmented_prompt(
        self,
        query: str,
        context: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Create augmented prompt with retrieved context.
        
        Args:
            query: User query
            context: Formatted context from retrieval
            system_prompt: Optional system instruction
            
        Returns:
            Augmented prompt string
        """
        if system_prompt is None:
            system_prompt = (
                "You are a helpful AI assistant. "
                "Use the provided context to answer questions accurately. "
                "If the context doesn't contain enough information, say so and provide your best answer."
            )
        
        prompt = f"""{system_prompt}

{context}

User Question: {query}

Answer:"""
        
        return prompt
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of retriever components."""
        health = {
            "vector_store": False,
            "cache": False
        }
        
        # Check vector store
        try:
            health["vector_store"] = await self.vector_store.health_check()
        except Exception as e:
            print(f"Vector store health check failed: {e}")
        
        # Check cache
        if self.cache:
            try:
                await self.cache.ping()
                health["cache"] = True
            except Exception as e:
                print(f"Cache health check failed: {e}")
        else:
            health["cache"] = None  # Not enabled
        
        return health
    
    async def close(self):
        """Close connections."""
        if self.cache:
            await self.cache.close()


# Convenience function for simple retrieval
async def simple_retrieve(
    query: str,
    embedder: VLM2VecEmbeddings,
    vector_store: QdrantVectorStore,
    top_k: int = 3
) -> str:
    """
    Simple retrieval without caching or advanced features.
    
    Args:
        query: Query text
        embedder: Embedding service
        vector_store: Vector store
        top_k: Number of results
        
    Returns:
        Formatted context string
    """
    from .config import RetrieverConfig
    
    config = RetrieverConfig(top_k=top_k)
    retriever = RAGRetriever(embedder, vector_store, config)
    
    results = await retriever.retrieve_context(query)
    context = retriever.format_context_for_llm(results)
    
    return context

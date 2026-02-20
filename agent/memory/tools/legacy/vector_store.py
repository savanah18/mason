"""
Qdrant vector store with optimized settings for RAG.
Supports async operations, scalar quantization, and batch upsert.
"""

from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime
import numpy as np

from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    SearchRequest, Filter, FieldCondition, MatchValue,
    ScalarQuantization, ScalarQuantizationConfig, ScalarType,
    HnswConfigDiff, OptimizersConfigDiff
)

from .config import QdrantConfig


class QdrantVectorStore:
    """
    Async Qdrant vector store with production optimizations.
    
    Features:
    - Async operations for non-blocking I/O
    - Scalar quantization for 75% storage reduction
    - HNSW indexing with configurable parameters
    - Batch upsert for efficient ingestion
    - Metadata filtering support
    """
    
    def __init__(self, config: QdrantConfig):
        """
        Initialize Qdrant vector store.
        
        Args:
            config: QdrantConfig instance with connection and optimization settings
        """
        self.config = config
        
        # Initialize sync and async clients
        self.client = QdrantClient(
            host=config.host,
            port=config.port,
            prefer_grpc=config.prefer_grpc
        )
        
        self.async_client = AsyncQdrantClient(
            host=config.host,
            port=config.port,
            prefer_grpc=config.prefer_grpc
        )
        
        self.collection_name = config.collection_name
        self._initialized = False
    
    async def initialize(self):
        """Create collection with optimized settings if it doesn't exist."""
        if self._initialized:
            return
        
        # Check if collection exists
        collections = await self.async_client.get_collections()
        collection_names = [col.name for col in collections.collections]
        
        if self.collection_name not in collection_names:
            print(f"Creating collection: {self.collection_name}")
            
            # Configure quantization
            quantization_config = None
            if self.config.use_quantization:
                quantization_config = ScalarQuantization(
                    scalar=ScalarQuantizationConfig(
                        type=ScalarType.INT8,
                        quantile=0.99,
                        always_ram=True  # Keep quantized vectors in RAM
                    )
                )
            
            # Configure HNSW indexing
            hnsw_config = HnswConfigDiff(
                m=self.config.hnsw_config["m"],
                ef_construct=self.config.hnsw_config["ef_construct"],
                full_scan_threshold=self.config.hnsw_config["full_scan_threshold"]
            )
            
            # Configure optimizers
            optimizers_config = OptimizersConfigDiff(
                indexing_threshold=10000,  # Start indexing after 10k points
            )
            
            # Create collection
            await self.async_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.config.vector_size,
                    distance=Distance.COSINE if self.config.distance == "Cosine" else Distance.EUCLID
                ),
                quantization_config=quantization_config,
                hnsw_config=hnsw_config,
                optimizers_config=optimizers_config,
                shard_number=self.config.shard_number,
                replication_factor=self.config.replication_factor
            )
            
            print(f"✓ Collection '{self.collection_name}' created successfully")
            print(f"  - Vector size: {self.config.vector_size}")
            print(f"  - Distance: {self.config.distance}")
            print(f"  - HNSW m: {self.config.hnsw_config['m']}")
            print(f"  - Quantization: {'Enabled (INT8)' if self.config.use_quantization else 'Disabled'}")
        else:
            print(f"Collection '{self.collection_name}' already exists")
        
        self._initialized = True
    
    async def add_documents(
        self,
        embeddings: List[np.ndarray],
        texts: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """
        Add documents to vector store with batch processing.
        
        Args:
            embeddings: List of embedding vectors
            texts: List of text content
            metadata: Optional list of metadata dicts
            ids: Optional list of IDs (auto-generated if None)
            
        Returns:
            List of document IDs
        """
        await self.initialize()
        
        if metadata is None:
            metadata = [{} for _ in texts]
        
        if ids is None:
            # Generate IDs based on timestamp and index
            timestamp = datetime.now().isoformat()
            ids = [f"doc_{timestamp}_{i}" for i in range(len(texts))]
        
        # Prepare points
        points = []
        for i, (embedding, text, meta, doc_id) in enumerate(zip(embeddings, texts, metadata, ids)):
            # Ensure embedding is the correct size
            if len(embedding) != self.config.vector_size:
                raise ValueError(
                    f"Embedding size mismatch: expected {self.config.vector_size}, "
                    f"got {len(embedding)}"
                )
            
            # Combine text and metadata
            payload = {
                "text": text,
                "created_at": datetime.now().isoformat(),
                **meta
            }
            
            points.append(PointStruct(
                id=doc_id,
                vector=embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
                payload=payload
            ))
        
        # Batch upsert
        batch_size = self.config.batch_size
        total_batches = (len(points) + batch_size - 1) // batch_size
        
        print(f"Upserting {len(points)} points in {total_batches} batches...")
        
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await self.async_client.upsert(
                collection_name=self.collection_name,
                points=batch,
                wait=True
            )
            print(f"  Batch {i//batch_size + 1}/{total_batches} complete")
        
        print(f"✓ Successfully added {len(points)} documents")
        return ids
    
    async def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents.
        
        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            score_threshold: Minimum similarity score
            filter_conditions: Optional metadata filters
            
        Returns:
            List of results with text, metadata, and scores
        """
        await self.initialize()
        
        # Prepare filter
        query_filter = None
        if filter_conditions:
            conditions = []
            for key, value in filter_conditions.items():
                conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=value))
                )
            query_filter = Filter(must=conditions)
        
        # Search
        results = await self.async_client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding,
            limit=top_k,
            query_filter=query_filter,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False  # Don't return vectors to save bandwidth
        )
        
        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                "id": result.id,
                "text": result.payload.get("text", ""),
                "score": result.score,
                "metadata": {k: v for k, v in result.payload.items() if k != "text"}
            })
        
        return formatted_results
    
    async def delete_documents(self, ids: List[str]):
        """Delete documents by IDs."""
        await self.initialize()
        
        await self.async_client.delete(
            collection_name=self.collection_name,
            points_selector=ids
        )
        print(f"✓ Deleted {len(ids)} documents")
    
    async def get_collection_info(self) -> Dict[str, Any]:
        """Get collection statistics."""
        await self.initialize()
        
        info = await self.async_client.get_collection(self.collection_name)
        
        return {
            "name": info.config.params.vectors.size,
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "points_count": info.points_count,
            "segments_count": info.segments_count,
            "status": info.status
        }
    
    async def health_check(self) -> bool:
        """Check if Qdrant is healthy and collection exists."""
        try:
            await self.initialize()
            return True
        except Exception as e:
            print(f"Health check failed: {e}")
            return False
    
    def close(self):
        """Close connections."""
        self.client.close()
        # Note: AsyncQdrantClient doesn't have explicit close method
        # It will be closed when the event loop is shut down


# Synchronous wrapper for convenience
class SyncQdrantVectorStore:
    """Synchronous wrapper around QdrantVectorStore."""
    
    def __init__(self, config: QdrantConfig):
        self.async_store = QdrantVectorStore(config)
        self.loop = asyncio.new_event_loop()
    
    def add_documents(self, embeddings, texts, metadata=None, ids=None):
        return self.loop.run_until_complete(
            self.async_store.add_documents(embeddings, texts, metadata, ids)
        )
    
    def search(self, query_embedding, top_k=5, score_threshold=None, filter_conditions=None):
        return self.loop.run_until_complete(
            self.async_store.search(query_embedding, top_k, score_threshold, filter_conditions)
        )
    
    def delete_documents(self, ids):
        return self.loop.run_until_complete(
            self.async_store.delete_documents(ids)
        )
    
    def get_collection_info(self):
        return self.loop.run_until_complete(
            self.async_store.get_collection_info()
        )
    
    def health_check(self):
        return self.loop.run_until_complete(
            self.async_store.health_check()
        )
    
    def close(self):
        self.async_store.close()
        self.loop.close()

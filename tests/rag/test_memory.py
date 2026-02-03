"""
Test script for memory module (RAG system) with Triton integration
"""
import asyncio
import sys
from pathlib import Path
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agent.memory import create_rag_system, TritonEmbeddings


async def test_memory():
    """Test RAG system components with Triton embeddings"""
    
    print("=" * 60)
    print("Testing Memory/RAG System with Triton")
    print("=" * 60)
    
    # 1. Create RAG system with Triton
    print("\n[1/5] Creating RAG system with Triton...")
    try:
        rag = await create_rag_system(use_triton=True, triton_url="localhost:8000")
        print("✓ RAG system ready with Triton embeddings")
    except Exception as e:
        print(f"✗ Failed to create RAG system: {e}")
        print("  Make sure Triton server is running: docker compose up triton-server")
        return
    
    # 2. Test single text embedding
    print("\n[2/5] Testing single text embedding...")
    test_text = "What is a useful concept to learn?"
    try:
        embedding = rag.embedder.embed_text(test_text)
        print(f"✓ Generated embedding: shape={embedding.shape}, dtype={embedding.dtype}")
        print(f"  Sample values: {embedding[:5]}")
        print(f"  L2 norm: {np.linalg.norm(embedding):.4f}")
    except Exception as e:
        print(f"✗ Embedding error: {e}")
        return
    
    # 3. Test batch embeddings
    print("\n[3/5] Testing batch embeddings...")
    test_queries = [
        {"text": "Explain an important idea"},
        {"text": "What is innovation?"},
        {"text": "How do complex systems work?"}
    ]
    try:
        embeddings = rag.embedder.embed_batch(test_queries, batch_size=16)
        print(f"✓ Generated {len(embeddings)} embeddings")
        for i, emb in enumerate(embeddings):
            print(f"  [{i+1}] shape={emb.shape}, L2={np.linalg.norm(emb):.4f}")
    except Exception as e:
        print(f"✗ Batch embedding error: {e}")
        return
    
    # 4. Test retrieval (if collection has data)
    print("\n[4/5] Testing retrieval...")
    try:
        results = await rag.retrieve_context("useful concepts to learn", top_k=3)
        if results:
            print(f"✓ Retrieved {len(results)} results")
            for i, result in enumerate(results):
                score = result.get('score', 0)
                source = result.get('metadata', {}).get('source', 'N/A')
                print(f"  [{i+1}] score={score:.4f}, source={source}")
        else:
            print("  (No data in collection yet)")
            print("  To add data:")
            print("    1. Prepare documents in a directory")
            print("    2. Run: python scripts/ingest_documents.py <directory>")
    except Exception as e:
        print(f"  (Empty collection: {e})")
    
    # 5. Test context formatting
    print("\n[5/5] Testing context formatting...")
    if results:
        try:
            context = rag.format_context_for_llm(results[:2])
            print(f"✓ Formatted context ({len(context)} chars)")
            print(f"  Preview: {context[:150]}...")
        except Exception as e:
            print(f"✗ Formatting error: {e}")
    else:
        print("  (Skipped - no results to format)")
    
    print("\n" + "=" * 60)
    print("Memory test complete!")
    print("=" * 60)
    print("\n✓ RAG system ready for use")
    print("  - Embedding via Triton server (efficient, batched)")
    print("  - Vector storage via Qdrant")
    print("  - Retrieval with caching and reranking")


if __name__ == "__main__":
    asyncio.run(test_memory())

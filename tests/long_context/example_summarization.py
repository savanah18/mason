#!/usr/bin/env python3
"""
Example usage patterns for Triton summarization client.
Demonstrates various ways to use the client for different scenarios.
"""

import sys
from pathlib import Path

# Import the client
try:
    from agent.client.triton_summarization_client import (
        TritonSummarizationHttpClient,
        TritonSummarizationGrpcClient,
        SummarizationLevel
    )
except ImportError:
    # Try relative import if running from repo root
    sys.path.insert(0, str(Path(__file__).parent / "agent" / "client"))
    from triton_summarization_client import (
        TritonSummarizationHttpClient,
        TritonSummarizationGrpcClient,
        SummarizationLevel
    )


def example_1_basic_summarization():
    """Example 1: Basic text summarization."""
    print("\n" + "="*80)
    print("Example 1: Basic Text Summarization")
    print("="*80)
    
    # Create client
    client = TritonSummarizationHttpClient("localhost:8000")
    
    # Sample document
    document = """
    Machine learning is a subset of artificial intelligence (AI) that provides 
    systems the ability to automatically learn and improve from experience without 
    being explicitly programmed. Machine learning focuses on the development of 
    computer programs that can access data and use it to learn for themselves.
    
    The process of learning begins with observations or data, such as examples, 
    direct experience, or instruction, in order to look for patterns in data and 
    make better decisions in the future based on the examples that we provide. 
    The primary aim is to allow the computers to learn automatically without 
    human intervention or assistance and adjust actions accordingly.
    """
    
    try:
        summary, metrics = client.summarize(
            document,
            level=SummarizationLevel.BRIEF
        )
        
        print(f"Original ({metrics.input_length} chars):")
        print(document)
        print(f"\nSummary ({metrics.output_length} chars):")
        print(summary)
        print(f"\nCompression: {metrics.compression_ratio:.1f}x, Latency: {metrics.latency_ms:.1f}ms")
    except Exception as e:
        print(f"❌ Error: {e}")


def example_2_file_summarization():
    """Example 2: Summarize document from file."""
    print("\n" + "="*80)
    print("Example 2: File Summarization")
    print("="*80)
    
    client = TritonSummarizationHttpClient("localhost:8000")
    
    # Try to load the epic document
    epic_path = "docs/epic-kubernetes-distributed-system.md"
    
    try:
        summary, metrics = client.summarize_file(
            epic_path,
            level=SummarizationLevel.BRIEF
        )
        
        print(f"\nFile: {epic_path}")
        print(f"Input: {metrics.input_tokens_estimated} tokens")
        print(f"Output: {metrics.output_tokens_estimated} tokens")
        print(f"\nSummary:\n{summary}")
        print(f"\nLatency: {metrics.latency_ms:.1f}ms")
    except FileNotFoundError:
        print(f"⚠️  Epic document not found at {epic_path}")
        print("   Create it first with: python test_long_context_summarization.py")


def example_3_custom_instructions():
    """Example 3: Summarization with custom instructions."""
    print("\n" + "="*80)
    print("Example 3: Custom Instructions")
    print("="*80)
    
    client = TritonSummarizationHttpClient("localhost:8000")
    
    document = """
    The new product launch includes three main components:
    1. Mobile app with cross-platform support
    2. Cloud backend with 99.99% uptime SLA
    3. Analytics dashboard with real-time reporting
    
    Timeline: 
    - Q1: MVP launch
    - Q2: Major feature additions
    - Q3: Enterprise integration
    
    Budget allocation:
    - Engineering: 60%
    - Marketing: 25%
    - Operations: 15%
    
    Expected outcomes:
    - 50% market share growth
    - 200% user acquisition
    - 4x ROI in first year
    """
    
    custom_instructions = """
    Focus on:
    - Budget and resource allocation
    - Timeline and key milestones
    - Expected financial outcomes
    
    Format: Use bullet points and numbers."""
    
    try:
        summary, metrics = client.summarize(
            document,
            level=SummarizationLevel.DETAILED,
            custom_instructions=custom_instructions
        )
        
        print("Input document:")
        print(document)
        print(f"\nCustom instructions:")
        print(custom_instructions)
        print(f"\nSummary:")
        print(summary)
        print(f"\nMetrics: {metrics.compression_ratio:.1f}x compression, {metrics.latency_ms:.1f}ms")
    except Exception as e:
        print(f"❌ Error: {e}")


def example_4_batch_processing():
    """Example 4: Batch summarization of multiple documents."""
    print("\n" + "="*80)
    print("Example 4: Batch Processing")
    print("="*80)
    
    client = TritonSummarizationHttpClient("localhost:8000")
    
    documents = [
        "Python is a high-level programming language known for its simplicity and readability.",
        "Docker is a containerization platform that packages applications with dependencies.",
        "Kubernetes is an orchestration system for deploying containerized applications at scale."
    ]
    
    try:
        print("Summarizing 3 documents...")
        results = client.summarize_batch(
            documents,
            level=SummarizationLevel.BRIEF
        )
        
        for i, (summary, metrics) in enumerate(results, 1):
            print(f"\n[{i}] Summary ({metrics.compression_ratio:.1f}x, {metrics.latency_ms:.1f}ms):")
            print(summary)
    except Exception as e:
        print(f"❌ Error: {e}")


def example_5_performance_analysis():
    """Example 5: Performance analysis and consistency testing."""
    print("\n" + "="*80)
    print("Example 5: Performance Analysis")
    print("="*80)
    
    client = TritonSummarizationHttpClient("localhost:8000")
    
    document = """
    This is a test document for performance analysis.
    We will run the summarization multiple times to measure consistency.
    The goal is to understand latency variability and output consistency.
    Different runs may produce slightly different summaries due to model behavior.
    We'll collect statistics on latency, output length, and consistency metrics.
    This helps identify performance bottlenecks and model stability.
    """ * 5  # Repeat to create longer document
    
    try:
        print("Running 5 iterations of summarization...")
        analysis = client.analyze_long_context_performance(
            document,
            iterations=5
        )
        
        print("\nPerformance Summary:")
        print(f"  Mean latency: {analysis['latency_ms']['mean']:.1f}ms")
        print(f"  Median latency: {analysis['latency_ms']['median']:.1f}ms")
        print(f"  Std deviation: {analysis['consistency']['latency_stddev']:.1f}ms")
        print(f"  Min/Max: {analysis['latency_ms']['min']:.1f}ms / {analysis['latency_ms']['max']:.1f}ms")
        print(f"  Output variance: {analysis['consistency']['output_variance']:.1f}")
    except Exception as e:
        print(f"❌ Error: {e}")


def example_6_protocol_comparison():
    """Example 6: Compare HTTP and gRPC protocols."""
    print("\n" + "="*80)
    print("Example 6: Protocol Comparison")
    print("="*80)
    
    document = """
    Comparing different inference protocols. HTTP is simpler and more debuggable.
    gRPC is faster and more efficient for production deployments.
    """ * 20  # Make document longer
    
    try:
        # HTTP
        print("\nTesting HTTP protocol (port 8000)...")
        http_client = TritonSummarizationHttpClient("localhost:8000")
        summary_http, metrics_http = http_client.summarize(
            document,
            level=SummarizationLevel.BRIEF
        )
        
        # gRPC
        print("\nTesting gRPC protocol (port 8001)...")
        grpc_client = TritonSummarizationGrpcClient("localhost:8001")
        summary_grpc, metrics_grpc = grpc_client.summarize(
            document,
            level=SummarizationLevel.BRIEF
        )
        
        print("\nComparison Results:")
        print(f"{'Protocol':<12} {'Latency (ms)':<15} {'Compression':<15} {'Output (chars)':<15}")
        print("-"*57)
        print(f"{'HTTP':<12} {metrics_http.latency_ms:<15.1f} {metrics_http.compression_ratio:<15.1f}x {metrics_http.output_length:<15}")
        print(f"{'gRPC':<12} {metrics_grpc.latency_ms:<15.1f} {metrics_grpc.compression_ratio:<15.1f}x {metrics_grpc.output_length:<15}")
        
        speedup = metrics_http.latency_ms / metrics_grpc.latency_ms
        print(f"\ngRPC speedup: {speedup:.2f}x")
    except Exception as e:
        print(f"⚠️  Could not compare protocols: {e}")
        print("   Make sure both HTTP and gRPC endpoints are available")


def example_7_different_summarization_levels():
    """Example 7: Try all summarization levels."""
    print("\n" + "="*80)
    print("Example 7: Summarization Levels Comparison")
    print("="*80)
    
    client = TritonSummarizationHttpClient("localhost:8000")
    
    # Create a moderately long document
    document = """
    # Distributed Systems Architecture
    
    ## Overview
    A distributed system is a computing system whose components are located on different 
    networked computers, which communicate and coordinate their actions by passing messages 
    to one another. The components interact with each other in order to achieve a common goal.
    
    ## Key Challenges
    Distributed systems face several fundamental challenges including network latency, 
    partial failures, and consistency. These challenges require sophisticated solutions 
    including replication, consensus algorithms, and distributed transactions.
    
    ## Architecture Patterns
    Common patterns include client-server, peer-to-peer, and multi-tier architectures. 
    Each pattern has different trade-offs in terms of scalability, fault tolerance, 
    and operational complexity.
    
    ## Technologies
    Modern distributed systems often use containers (Docker), orchestration (Kubernetes), 
    and service meshes (Istio) for deployment and management. These technologies abstract 
    away many of the operational complexities of managing distributed systems at scale.
    """ * 3  # Triple length
    
    levels = [
        SummarizationLevel.BRIEF,
        SummarizationLevel.DETAILED,
        SummarizationLevel.SECTION,
        SummarizationLevel.EXTRACTION
    ]
    
    print(f"Document length: {len(document)} chars ({client._estimate_tokens(document)} tokens)\n")
    
    for level in levels:
        try:
            print(f"\n{'-'*80}")
            print(f"Level: {level.value.upper()}")
            print(f"{'-'*80}")
            
            summary, metrics = client.summarize(
                document,
                level=level
            )
            
            print(f"Output: {metrics.output_length} chars ({metrics.output_tokens_estimated} tokens)")
            print(f"Compression: {metrics.compression_ratio:.1f}x")
            print(f"Latency: {metrics.latency_ms:.1f}ms\n")
            print(summary)
        except Exception as e:
            print(f"❌ Error: {e}")


def main():
    """Run examples based on arguments."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Triton Summarization Client Examples")
    parser.add_argument(
        "--example",
        type=int,
        choices=[1, 2, 3, 4, 5, 6, 7],
        help="Run specific example (1-7), or all if not specified"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all examples"
    )
    
    args = parser.parse_args()
    
    examples = [
        example_1_basic_summarization,
        example_2_file_summarization,
        example_3_custom_instructions,
        example_4_batch_processing,
        example_5_performance_analysis,
        example_6_protocol_comparison,
        example_7_different_summarization_levels,
    ]
    
    print("="*80)
    print("Triton Summarization Client - Usage Examples")
    print("="*80)
    
    if args.example:
        examples[args.example - 1]()
    elif args.all:
        for example in examples:
            try:
                example()
            except Exception as e:
                print(f"\n⚠️  Example failed: {e}")
    else:
        print("\nAvailable examples:")
        for i, example in enumerate(examples, 1):
            print(f"  {i}. {example.__doc__.strip()}")
        print("\nUsage:")
        print("  python examples_summarization.py --example 1")
        print("  python examples_summarization.py --all")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Test and demonstration script for Triton summarization client.
Tests long-context capabilities of Qwen3 with a complex epic document.

Usage:
    python test_long_context_summarization.py [--grpc] [--host localhost] [--port 8001]
    
    Options:
        --grpc      Use gRPC protocol (default: HTTP)
        --http      Use HTTP protocol (explicit)
        --host      Triton server host (default: localhost)
        --port      Triton server port (default: 8000 for HTTP, 8001 for gRPC)
        --skip-health  Skip health check
        --output-dir   Directory to save results (default: ./test_summaries)
"""

import sys
import argparse
from pathlib import Path
import time
import json

# Import the summarization client
from triton_summarization_client import (
    TritonSummarizationClient,
    TritonSummarizationHttpClient,
    TritonSummarizationGrpcClient,
    SummarizationLevel
)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Test Qwen3 long-context capabilities via Triton",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with HTTP (default)
  python test_long_context_summarization.py
  
  # Test with gRPC
  python test_long_context_summarization.py --grpc
  
  # Custom server address
  python test_long_context_summarization.py --host 192.168.1.100 --port 8000
  
  # Skip health check for debugging
  python test_long_context_summarization.py --skip-health
        """
    )
    
    parser.add_argument(
        '--grpc',
        action='store_true',
        help='Use gRPC protocol (default: HTTP)'
    )
    parser.add_argument(
        '--http',
        action='store_true',
        help='Use HTTP protocol (explicit, default)'
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help='Triton server host (default: localhost)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help='Triton server port (default: 8000 for HTTP, 8001 for gRPC)'
    )
    parser.add_argument(
        '--skip-health',
        action='store_true',
        help='Skip health check'
    )
    parser.add_argument(
        '--output-dir',
        default='./test_summaries',
        help='Directory to save results (default: ./test_summaries)'
    )
    parser.add_argument(
        '--model',
        default='qwen3-vl',
        help='Model name in Triton (default: qwen3-vl)'
    )
    parser.add_argument(
        '--version',
        default='1',
        help='Model version (default: 1)'
    )
    
    return parser.parse_args()


def create_client(args) -> TritonSummarizationClient:
    """Create appropriate client based on arguments."""
    use_grpc = args.grpc
    
    # Determine port if not specified
    if args.port is None:
        port = 8001 if use_grpc else 8000
    else:
        port = args.port
    
    server_url = f"{args.host}:{port}"
    
    print(f"Creating Triton client...")
    print(f"  Protocol: {'gRPC' if use_grpc else 'HTTP'}")
    print(f"  Server: {server_url}")
    print(f"  Model: {args.model} (v{args.version})")
    
    if use_grpc:
        client = TritonSummarizationGrpcClient(
            url=server_url,
            model_name=args.model,
            model_version=args.version
        )
    else:
        client = TritonSummarizationHttpClient(
            url=server_url,
            model_name=args.model,
            model_version=args.version
        )
    
    return client


def test_basic_health(client: TritonSummarizationClient, args):
    """Test [1/5] - Server health check."""
    print("\n" + "="*80)
    print("[1/5] Server Health Check")
    print("="*80)
    
    if args.skip_health:
        print("⊘ Skipped (--skip-health flag)")
        return True
    
    try:
        if client.check_health():
            print("✓ Triton server is healthy!")
            print("  - Server is live")
            print("  - Server is ready")
            return True
        else:
            print("❌ Triton server is not healthy!")
            return False
    except Exception as e:
        print(f"❌ Health check failed: {str(e)}")
        return False


def test_document_loading(client: TritonSummarizationClient):
    """Test [2/5] - Document loading and token estimation."""
    print("\n" + "="*80)
    print("[2/5] Document Loading and Token Estimation")
    print("="*80)
    
    epic_path = "docs/epic-kubernetes-distributed-system.md"
    
    try:
        document = client.load_document(epic_path)
        tokens = client._estimate_tokens(document)
        
        print(f"✓ Document loaded successfully!")
        print(f"\nDocument Statistics:")
        print(f"  File: {epic_path}")
        print(f"  Size: {len(document):,} characters")
        print(f"  Estimated tokens: {tokens:,}")
        print(f"  Lines: {len(document.splitlines()):,}")
        print(f"  Words (approx): {len(document.split()):,}")
        
        return document
    except Exception as e:
        print(f"❌ Failed to load document: {str(e)}")
        sys.exit(1)


def test_brief_summarization(client: TritonSummarizationClient, document: str, args):
    """Test [3/5] - Brief summarization."""
    print("\n" + "="*80)
    print("[3/5] Brief Summarization Test")
    print("="*80)
    print("Creating one-paragraph summary of the epic document...")
    
    try:
        summary, metrics = client.summarize(
            document,
            level=SummarizationLevel.BRIEF
        )
        
        print(f"\n{'─'*80}")
        print("SUMMARY:")
        print(f"{'─'*80}")
        print(summary)
        print(f"{'─'*80}")
        
        print(f"\nMetrics:")
        print(f"  Input:  {metrics.input_length:,} chars ({metrics.input_tokens_estimated:,} tokens)")
        print(f"  Output: {metrics.output_length:,} chars ({metrics.output_tokens_estimated:,} tokens)")
        print(f"  Compression: {metrics.compression_ratio:.1f}x")
        print(f"  Latency: {metrics.latency_ms:.1f}ms")
        print(f"  Request ID: {metrics.request_id}")
        
        return summary, metrics
    except Exception as e:
        print(f"❌ Brief summarization failed: {str(e)}")
        return None, None


def test_detailed_summarization(client: TritonSummarizationClient, document: str, args):
    """Test [4/5] - Detailed summarization with custom instructions."""
    print("\n" + "="*80)
    print("[4/5] Detailed Summarization with Custom Instructions")
    print("="*80)
    
    custom_instructions = """
Focus on:
1. Architecture decisions and their rationale
2. Risk mitigation strategies
3. Timeline and phases
4. Key performance metrics and success criteria

Ignore implementation details but keep conceptual clarity."""
    
    print("Creating detailed summary with custom instructions...")
    print("Custom focus areas:")
    print("  - Architecture decisions")
    print("  - Risk mitigation")
    print("  - Timeline and phases")
    print("  - Success metrics")
    
    try:
        summary, metrics = client.summarize(
            document,
            level=SummarizationLevel.DETAILED,
            custom_instructions=custom_instructions
        )
        
        print(f"\n{'─'*80}")
        print("SUMMARY:")
        print(f"{'─'*80}")
        print(summary)
        print(f"{'─'*80}")
        
        print(f"\nMetrics:")
        print(f"  Input:  {metrics.input_length:,} chars ({metrics.input_tokens_estimated:,} tokens)")
        print(f"  Output: {metrics.output_length:,} chars ({metrics.output_tokens_estimated:,} tokens)")
        print(f"  Compression: {metrics.compression_ratio:.1f}x")
        print(f"  Latency: {metrics.latency_ms:.1f}ms")
        print(f"  Request ID: {metrics.request_id}")
        
        return summary, metrics
    except Exception as e:
        print(f"❌ Detailed summarization failed: {str(e)}")
        return None, None


def test_long_context_performance(client: TritonSummarizationClient, document: str, args):
    """Test [5/5] - Long context performance analysis."""
    print("\n" + "="*80)
    print("[5/5] Long Context Performance Analysis")
    print("="*80)
    print("Testing consistency and performance across multiple iterations...")
    
    try:
        analysis = client.analyze_long_context_performance(
            document,
            iterations=3
        )
        
        return analysis
    except Exception as e:
        print(f"❌ Performance analysis failed: {str(e)}")
        return None


def save_results(
    brief_summary: str,
    brief_metrics,
    detailed_summary: str,
    detailed_metrics,
    analysis: dict,
    output_dir: str,
    client: TritonSummarizationClient
):
    """Save all test results to files."""
    print("\n" + "="*80)
    print("Saving Results")
    print("="*80)
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    # Save brief summary
    if brief_summary and brief_metrics:
        brief_file = output_path / f"test_{timestamp}_brief_summary.txt"
        with open(brief_file, 'w', encoding='utf-8') as f:
            f.write("BRIEF SUMMARIZATION TEST\n")
            f.write("="*80 + "\n\n")
            f.write(brief_summary)
        print(f"✓ Saved: {brief_file}")
        
        brief_metrics_file = output_path / f"test_{timestamp}_brief_metrics.json"
        with open(brief_metrics_file, 'w') as f:
            json.dump(brief_metrics.to_dict(), f, indent=2)
        print(f"✓ Saved: {brief_metrics_file}")
    
    # Save detailed summary
    if detailed_summary and detailed_metrics:
        detailed_file = output_path / f"test_{timestamp}_detailed_summary.txt"
        with open(detailed_file, 'w', encoding='utf-8') as f:
            f.write("DETAILED SUMMARIZATION TEST\n")
            f.write("="*80 + "\n\n")
            f.write(detailed_summary)
        print(f"✓ Saved: {detailed_file}")
        
        detailed_metrics_file = output_path / f"test_{timestamp}_detailed_metrics.json"
        with open(detailed_metrics_file, 'w') as f:
            json.dump(detailed_metrics.to_dict(), f, indent=2)
        print(f"✓ Saved: {detailed_metrics_file}")
    
    # Save performance analysis
    if analysis:
        analysis_file = output_path / f"test_{timestamp}_performance_analysis.json"
        with open(analysis_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        print(f"✓ Saved: {analysis_file}")
    
    # Save test report summary
    report_file = output_path / f"test_{timestamp}_report.txt"
    with open(report_file, 'w') as f:
        f.write("LONG CONTEXT SUMMARIZATION TEST REPORT\n")
        f.write("="*80 + "\n\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Model: {client.model_name} (v{client.model_version})\n")
        f.write(f"Protocol: {'gRPC' if client.use_grpc else 'HTTP'}\n\n")
        
        if brief_metrics:
            f.write("BRIEF SUMMARIZATION\n")
            f.write("-"*80 + "\n")
            f.write(f"Input tokens: {brief_metrics.input_tokens_estimated:,}\n")
            f.write(f"Output tokens: {brief_metrics.output_tokens_estimated:,}\n")
            f.write(f"Compression ratio: {brief_metrics.compression_ratio:.1f}x\n")
            f.write(f"Latency: {brief_metrics.latency_ms:.1f}ms\n\n")
        
        if detailed_metrics:
            f.write("DETAILED SUMMARIZATION\n")
            f.write("-"*80 + "\n")
            f.write(f"Input tokens: {detailed_metrics.input_tokens_estimated:,}\n")
            f.write(f"Output tokens: {detailed_metrics.output_tokens_estimated:,}\n")
            f.write(f"Compression ratio: {detailed_metrics.compression_ratio:.1f}x\n")
            f.write(f"Latency: {detailed_metrics.latency_ms:.1f}ms\n\n")
        
        if analysis:
            f.write("PERFORMANCE ANALYSIS (3 iterations)\n")
            f.write("-"*80 + "\n")
            f.write(f"Mean latency: {analysis['latency_ms']['mean']:.1f}ms\n")
            f.write(f"Latency std dev: {analysis['consistency']['latency_stddev']:.1f}ms\n")
            f.write(f"Min latency: {analysis['latency_ms']['min']:.1f}ms\n")
            f.write(f"Max latency: {analysis['latency_ms']['max']:.1f}ms\n")
    
    print(f"✓ Saved: {report_file}")
    print(f"\nAll results saved to: {output_path}")


def main():
    """Main test execution."""
    args = parse_arguments()
    
    print("="*80)
    print("Qwen3 Long Context Capabilities Test")
    print("Triton Inference Server Integration")
    print("="*80)
    print()
    
    # Create client
    try:
        client = create_client(args)
    except Exception as e:
        print(f"❌ Failed to create client: {str(e)}")
        sys.exit(1)
    
    # Run tests
    tests_passed = 0
    tests_total = 5
    
    # Test 1: Health check
    if not test_basic_health(client, args):
        print("\n⚠️  Continuing despite health check failure...")
    else:
        tests_passed += 1
    
    # Test 2: Document loading
    try:
        document = test_document_loading(client)
        tests_passed += 1
    except Exception as e:
        print(f"❌ Document loading failed: {str(e)}")
        sys.exit(1)
    
    # Test 3: Brief summarization
    brief_summary, brief_metrics = test_brief_summarization(client, document, args)
    if brief_summary:
        tests_passed += 1
    
    # Test 4: Detailed summarization
    detailed_summary, detailed_metrics = test_detailed_summarization(client, document, args)
    if detailed_summary:
        tests_passed += 1
    
    # Test 5: Performance analysis
    analysis = test_long_context_performance(client, document, args)
    if analysis:
        tests_passed += 1
    
    # Save results
    try:
        save_results(
            brief_summary,
            brief_metrics,
            detailed_summary,
            detailed_metrics,
            analysis,
            args.output_dir,
            client
        )
    except Exception as e:
        print(f"⚠️  Failed to save results: {str(e)}")
    
    # Final summary
    print("\n" + "="*80)
    print("Test Summary")
    print("="*80)
    print(f"Tests passed: {tests_passed}/{tests_total}")
    
    if tests_passed == tests_total:
        print("✓ All tests passed!")
        return 0
    else:
        print(f"⚠️  {tests_total - tests_passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

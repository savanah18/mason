#!/usr/bin/env python3
"""
Test script for Qwen3 Triton Ensemble Model.
Demonstrates how to use the ensemble for end-to-end inference.
"""

import tritonclient.http as httpclient
import tritonclient.grpc as grpcclient
import json
import numpy as np
import time
from typing import Dict, List


def test_http_ensemble(
    messages: List[Dict[str, str]],
    max_tokens: int = 512,
    temperature: float = 0.7,
    top_p: float = 0.9,
    url: str = "localhost:8000"
):
    """Test ensemble using HTTP client."""
    print("=" * 60)
    print("Testing Qwen3 Ensemble (HTTP)")
    print("=" * 60)
    
    client = httpclient.InferenceServerClient(url)
    
    # Check if model is ready
    if not client.is_model_ready("qwen3-ensemble"):
        print("❌ Model qwen3-ensemble is not ready")
        return
    
    print("✓ Model is ready")
    
    # Prepare inputs
    messages_json = json.dumps(messages)
    print(f"\nInput messages:\n{messages_json}\n")
    
    messages_input = httpclient.InferInput("messages", [1], "BYTES")
    messages_input.set_data_from_numpy(
        np.array([messages_json.encode()], dtype=object)
    )
    
    max_tokens_input = httpclient.InferInput("max_tokens", [1], "INT32")
    max_tokens_input.set_data_from_numpy(np.array([max_tokens], dtype=np.int32))
    
    temperature_input = httpclient.InferInput("temperature", [1], "FP32")
    temperature_input.set_data_from_numpy(np.array([temperature], dtype=np.float32))
    
    top_p_input = httpclient.InferInput("top_p", [1], "FP32")
    top_p_input.set_data_from_numpy(np.array([top_p], dtype=np.float32))
    
    # Request outputs
    outputs = [
        httpclient.InferRequestedOutput("text_output"),
        httpclient.InferRequestedOutput("usage")
    ]
    
    # Run inference
    print("Running inference...")
    start_time = time.time()
    
    response = client.infer(
        model_name="qwen3-ensemble",
        inputs=[messages_input, max_tokens_input, temperature_input, top_p_input],
        outputs=outputs
    )
    
    inference_time = time.time() - start_time
    
    # Get results
    text = response.as_numpy("text_output")[0].decode()
    usage = response.as_numpy("usage")[0]
    
    print(f"✓ Inference completed in {inference_time:.2f}s")
    print(f"\nResponse:\n{text}\n")
    print(f"Usage:")
    print(f"  - Prompt tokens: {usage[0]}")
    print(f"  - Completion tokens: {usage[1]}")
    print(f"  - Total tokens: {usage[2]}")
    print(f"  - Tokens/sec: {usage[1]/inference_time:.1f}")
    print("=" * 60)


def test_grpc_ensemble(
    messages: List[Dict[str, str]],
    max_tokens: int = 512,
    url: str = "localhost:8001"
):
    """Test ensemble using gRPC client."""
    print("=" * 60)
    print("Testing Qwen3 Ensemble (gRPC)")
    print("=" * 60)
    
    client = grpcclient.InferenceServerClient(url)
    
    # Check if model is ready
    if not client.is_model_ready("qwen3-ensemble"):
        print("❌ Model qwen3-ensemble is not ready")
        return
    
    print("✓ Model is ready")
    
    # Prepare inputs
    messages_json = json.dumps(messages)
    print(f"\nInput messages:\n{messages_json}\n")
    
    messages_input = grpcclient.InferInput("messages", [1], "BYTES")
    messages_input.set_data_from_numpy(
        np.array([messages_json.encode()], dtype=object)
    )
    
    max_tokens_input = grpcclient.InferInput("max_tokens", [1], "INT32")
    max_tokens_input.set_data_from_numpy(np.array([max_tokens], dtype=np.int32))
    
    # Request outputs
    outputs = [
        grpcclient.InferRequestedOutput("text_output"),
        grpcclient.InferRequestedOutput("usage")
    ]
    
    # Run inference
    print("Running inference...")
    start_time = time.time()
    
    response = client.infer(
        model_name="qwen3-ensemble",
        inputs=[messages_input, max_tokens_input],
        outputs=outputs
    )
    
    inference_time = time.time() - start_time
    
    # Get results
    text = response.as_numpy("text_output")[0].decode()
    usage = response.as_numpy("usage")[0]
    
    print(f"✓ Inference completed in {inference_time:.2f}s")
    print(f"\nResponse:\n{text}\n")
    print(f"Usage:")
    print(f"  - Prompt tokens: {usage[0]}")
    print(f"  - Completion tokens: {usage[1]}")
    print(f"  - Total tokens: {usage[2]}")
    print(f"  - Tokens/sec: {usage[1]/inference_time:.1f}")
    print("=" * 60)


def test_batch_inference():
    """Test batch processing with ensemble."""
    print("=" * 60)
    print("Testing Batch Inference")
    print("=" * 60)
    
    client = httpclient.InferenceServerClient("localhost:8000")
    
    # Multiple requests
    test_messages = [
        [{"role": "user", "content": "What is 2+2?"}],
        [{"role": "user", "content": "Name a color."}],
        [{"role": "user", "content": "Say hello."}],
    ]
    
    total_time = 0
    for i, messages in enumerate(test_messages):
        print(f"\nRequest {i+1}/{len(test_messages)}: {messages[0]['content']}")
        
        messages_input = httpclient.InferInput("messages", [1], "BYTES")
        messages_input.set_data_from_numpy(
            np.array([json.dumps(messages).encode()], dtype=object)
        )
        
        start = time.time()
        response = client.infer(
            model_name="qwen3-ensemble",
            inputs=[messages_input]
        )
        elapsed = time.time() - start
        total_time += elapsed
        
        text = response.as_numpy("text_output")[0].decode()
        print(f"Response ({elapsed:.2f}s): {text}")
    
    print(f"\nTotal time: {total_time:.2f}s")
    print(f"Average latency: {total_time/len(test_messages):.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    # Test messages
    simple_message = [
        {"role": "user", "content": "What is the capital of France?"}
    ]
    
    conversation = [
        {"role": "user", "content": "My name is Alice."},
        {"role": "assistant", "content": "Hello Alice! How can I help you?"},
        {"role": "user", "content": "What is my name?"}
    ]
    
    # Run tests
    try:
        # Test HTTP
        test_http_ensemble(simple_message)
        
        # Test gRPC
        test_grpc_ensemble(simple_message)
        
        # Test conversation
        test_http_ensemble(conversation, max_tokens=256)
        
        # Test batch
        test_batch_inference()
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()

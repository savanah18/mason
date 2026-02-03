"""
Triton client for Qwen3-VL inference.
Can be used instead of the FastAPI client for higher performance.
"""

import tritonclient.http as httpclient
import tritonclient.grpc as grpcclient
from typing import Optional, Tuple
import base64
import numpy as np
from pathlib import Path
import uuid


class TritonClient:
    """Client for Triton Inference Server."""
    
    def __init__(
        self,
        triton_url: str = "localhost:8001",
        use_grpc: bool = False,
        model_name: str = "qwen3-vl",
        session_id: Optional[str] = None
    ):
        """
        Initialize Triton client.
        
        Args:
            triton_url: Triton server URL (host:port)
            use_grpc: Use gRPC protocol instead of HTTP
            model_name: Model name in Triton repository
            session_id: Optional session ID for KV cache persistence
        """
        self.triton_url = triton_url
        self.model_name = model_name
        self.use_grpc = use_grpc
        self.session_id = session_id or str(uuid.uuid4())
        
        if use_grpc:
            self.client = grpcclient.InferenceServerClient(triton_url)
        else:
            self.client = httpclient.InferenceServerClient(triton_url)
        
        print(f"Connected to Triton at {triton_url}")
        print(f"Model: {model_name}")
        print(f"Session ID: {self.session_id}")
    
    @staticmethod
    def debug_infer_result(result):
        """Debug helper to inspect InferResult structure."""
        print("=== InferResult Debug Info ===")
        print(f"Type: {type(result)}")
        print(f"Available methods: {[x for x in dir(result) if not x.startswith('_')]}")
        
        # Use get_response to get the underlying protobuf message
        try:
            proto_response = result.get_response()
            print(f"Proto response outputs: {[o.name for o in proto_response.outputs]}")
            
            # Try as_numpy for known outputs
            for output in proto_response.outputs:
                try:
                    print(output.name)
                    output_data = result.as_numpy(output.name)
                    print(f"\n  Output: {output.name}")
                    print(f"    Shape: {output_data.shape}")
                    print(f"    Dtype: {output_data.dtype}")
                    print(f"    Data: {output_data}")
                except Exception as e:
                    print(f"  Error getting {output.name}: {e}")
        except Exception as e:
            print(f"Error inspecting response: {e}")
    
    
    def check_health(self) -> bool:
        """Check if Triton server is healthy."""
        try:
            if self.use_grpc:
                return self.client.is_server_live()
            else:
                return self.client.is_server_live()
        except Exception as e:
            print(f"Health check failed: {str(e)}")
            return False
    
    def chat(
        self,
        message: str,
        image_path: Optional[str] = None,
        mode: str = "generate"
    ) -> Tuple[str, float]:
        """
        Send a chat message to Triton for inference.
        
        Args:
            message: Chat message
            image_path: Optional path to image file
            mode: "generate" for text generation or "embed" for embeddings
            
        Returns:
            Tuple of (response, response_time) for generate mode
            Tuple of (embedding_array, response_time) for embed mode
        """
        # Prepare inputs separately
        message_bytes = message.encode('utf-8')
        image_bytes = None
        
        if image_path:
            try:
                with open(image_path, "rb") as f:
                    image_data = f.read()
                    image_bytes = base64.b64encode(image_data)
            except Exception as e:
                print(f"Warning: Failed to read image: {str(e)}")
        
        # Use appropriate client based on protocol
        InferInput = grpcclient.InferInput if self.use_grpc else httpclient.InferInput
        
        # Create input tensors with batch dimension
        message_input = InferInput("message", [1, 1], "BYTES")
        message_input.set_data_from_numpy(np.array([[message_bytes]], dtype=object))
        
        inputs = [message_input]
        
        # Add image input if provided
        if image_bytes:
            image_input = InferInput("image", [1, 1], "BYTES")
            image_input.set_data_from_numpy(np.array([[image_bytes]], dtype=object))
            inputs.append(image_input)
        
        # Add mode input
        mode_input = InferInput("mode", [1, 1], "BYTES")
        mode_input.set_data_from_numpy(np.array([[mode.encode('utf-8')]], dtype=object))
        inputs.append(mode_input)
        
        # Add session_id input for KV cache
        session_input = InferInput("session_id", [1, 1], "BYTES")
        session_input.set_data_from_numpy(np.array([[self.session_id.encode('utf-8')]], dtype=object))
        inputs.append(session_input)
        
        # Request inference
        try:
            response = self.client.infer(
                model_name=self.model_name,
                inputs=inputs
            )
            # Uncomment below to debug response structure
            # self.debug_infer_result(response)
            
            response_time_array = response.as_numpy("response_time")
            response_time = float(response_time_array.flat[0])
            
            if mode == "embed":
                # Extract embedding
                embedding_array = response.as_numpy("embedding")
                return embedding_array[0], response_time
            else:
                # Extract response text
                response_array = response.as_numpy("response")
                response_bytes = response_array.flat[0]
                if isinstance(response_bytes, np.bytes_):
                    response_bytes = bytes(response_bytes)
                response_text = response_bytes.decode('utf-8')
                return response_text, response_time
        
        except Exception as e:
            print(f"Inference failed: {str(e)}")
            raise
    
    def batch_chat(
        self,
        messages: list,
        image_paths: Optional[list] = None,
        mode: str = "generate",
        batch_size: int = 32
    ) -> list:
        """
        Send batch of chat messages to Triton for inference.
        
        Args:
            messages: List of chat messages (max 32)
            image_paths: Optional list of image paths (same length as messages)
            mode: "generate" for text generation or "embed" for embeddings
            batch_size: Maximum batch size (default 32)
            
        Returns:
            List of (response, response_time) tuples
        """
        if len(messages) > batch_size:
            raise ValueError(f"Batch size {len(messages)} exceeds maximum {batch_size}")
        
        batch_size_actual = len(messages)
        
        # Prepare message inputs
        message_bytes_list = [msg.encode('utf-8') for msg in messages]
        message_array = np.array([[msg] for msg in message_bytes_list], dtype=object)
        
        InferInput = grpcclient.InferInput if self.use_grpc else httpclient.InferInput
        
        message_input = InferInput("message", [batch_size_actual, 1], "BYTES")
        message_input.set_data_from_numpy(message_array)
        
        inputs = [message_input]
        
        # Add image inputs if provided
        if image_paths:
            image_bytes_list = []
            for img_path in image_paths:
                if img_path:
                    try:
                        with open(img_path, "rb") as f:
                            image_data = f.read()
                            image_bytes_list.append(base64.b64encode(image_data))
                    except Exception as e:
                        print(f"Warning: Failed to read image {img_path}: {str(e)}")
                        image_bytes_list.append(b"")
                else:
                    image_bytes_list.append(b"")
            
            image_array = np.array([[img] for img in image_bytes_list], dtype=object)
            image_input = InferInput("image", [batch_size_actual, 1], "BYTES")
            image_input.set_data_from_numpy(image_array)
            inputs.append(image_input)
        
        # Add mode input
        mode_bytes = mode.encode('utf-8')
        mode_array = np.array([[mode_bytes]] * batch_size_actual, dtype=object)
        mode_input = InferInput("mode", [batch_size_actual, 1], "BYTES")
        mode_input.set_data_from_numpy(mode_array)
        inputs.append(mode_input)
        
        # Add session_id input for KV cache (same session for all in batch)
        session_bytes = self.session_id.encode('utf-8')
        session_array = np.array([[session_bytes]] * batch_size_actual, dtype=object)
        session_input = InferInput("session_id", [batch_size_actual, 1], "BYTES")
        session_input.set_data_from_numpy(session_array)
        inputs.append(session_input)
        
        # Request batch inference
        try:
            response = self.client.infer(
                model_name=self.model_name,
                inputs=inputs
            )
            
            response_time_array = response.as_numpy("response_time")
            
            # Debug: Print array shapes
            print(f"DEBUG: response_time_array shape: {response_time_array.shape}, ndim: {response_time_array.ndim}")
            
            results = []
            if mode == "embed":
                # Extract embeddings
                embedding_array = response.as_numpy("embedding")
                print(f"DEBUG: embedding_array shape: {embedding_array.shape}, expected batch_size: {batch_size_actual}")
                for i in range(batch_size_actual):
                    response_time = float(response_time_array[i, 0]) if response_time_array.ndim > 1 else float(response_time_array[i])
                    results.append((embedding_array[i], response_time))
            else:
                # Extract response texts
                response_array = response.as_numpy("response")
                print(f"DEBUG: response_array shape: {response_array.shape}, expected batch_size: {batch_size_actual}")
                for i in range(batch_size_actual):
                    # Handle both 1D and 2D arrays
                    response_bytes = response_array[i, 0] if response_array.ndim > 1 else response_array[i]
                    if isinstance(response_bytes, np.bytes_):
                        response_bytes = bytes(response_bytes)
                    response_text = response_bytes.decode('utf-8')
                    response_time = float(response_time_array[i, 0]) if response_time_array.ndim > 1 else float(response_time_array[i])
                    results.append((response_text, response_time))
            
            return results
        
        except Exception as e:
            print(f"Batch inference failed: {str(e)}")
            raise


class TritonHttpClient(TritonClient):
    """HTTP-based Triton client."""
    
    def __init__(self, url: str = "localhost:8001", model_name: str = "qwen3-vl", session_id: Optional[str] = None):
        super().__init__(url, use_grpc=False, model_name=model_name, session_id=session_id)


class TritonGrpcClient(TritonClient):
    """gRPC-based Triton client (faster for low-latency)."""
    
    def __init__(self, url: str = "localhost:8001", model_name: str = "qwen3-vl", session_id: Optional[str] = None):
        super().__init__(url, use_grpc=True, model_name=model_name, session_id=session_id)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    print("=" * 70)
    print("Triton Qwen3-VL Inference Tests")
    print("=" * 70)
    
    # Initialize client (use HTTP by default, can switch to gRPC)
    use_grpc = "--grpc" in sys.argv
    port = "8001" if use_grpc else "8000"
    
    client = TritonGrpcClient(f"localhost:{port}") if use_grpc else TritonHttpClient(f"localhost:{port}")
    print(f"Using {'gRPC' if use_grpc else 'HTTP'} protocol on port {port}")
    
    # Health check
    print("\n[1/7] Health Check...")
    if not client.check_health():
        print("❌ Triton server is not healthy!")
        sys.exit(1)
    print("✓ Triton server is healthy!")
    
    # Test 1: Text embedding
    print("\n[2/7] Test: Text Embedding Extraction")
    print("-" * 70)
    try:
        query = "What is a useful concept to learn?"
        print(f"Query: {query}")
        embedding, response_time = client.chat(query, mode="embed")
        print(f"✓ Embedding extracted successfully")
        print(f"  Dimension: {embedding.shape}")
        print(f"  Dtype: {embedding.dtype}")
        print(f"  Sample values (first 5): {embedding[:5]}")
        print(f"  L2 norm: {np.linalg.norm(embedding):.4f}")
        print(f"⏱️  Response Time: {response_time:.2f}s")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    # Test 2: Multimodal embedding
    print("\n[3/7] Test: Multimodal Embedding (Text + Image)")
    print("-" * 70)
    image_path = Path("docs/figures/poc-vscode-ext.png")
    if image_path.exists():
        try:
            query = "Describe this VS Code interface"
            print(f"Query: {query}")
            print(f"Image: {image_path}")
            embedding, response_time = client.chat(query, str(image_path), mode="embed")
            print(f"✓ Multimodal embedding extracted successfully")
            print(f"  Dimension: {embedding.shape}")
            print(f"  Dtype: {embedding.dtype}")
            print(f"  Sample values (first 5): {embedding[:5]}")
            print(f"  L2 norm: {np.linalg.norm(embedding):.4f}")
            print(f"⏱️  Response Time: {response_time:.2f}s")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
    else:
        print(f"⚠️  Image not found: {image_path}")
    
    # Test 3: Text-only inference
    print("\n[4/7] Test: Text-only Generation")
    print("-" * 70)
    try:
        question = "Hi, are you there?"
        print(f"Query: {question}")
        response, response_time = client.chat(question)
        print(f"\nResponse:\n{response}")
        print(f"\n⏱️  Response Time: {response_time:.2f}s")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    # Test 4: Image inference with VS Code extension screenshot
    print("\n[5/7] Test: Multimodal Generation (Text + Image) - VS Code Extension")
    print("-" * 70)
    image_path = Path("docs/figures/poc-vscode-ext.png")
    if image_path.exists():
        try:
            question = "What do you see in this image? Describe the VS Code interface shown."
            print(f"Query: {question}")
            print(f"Image: {image_path}")
            response, response_time = client.chat(question, str(image_path))
            print(f"\nResponse:\n{response}")
            print(f"\n⏱️  Response Time: {response_time:.2f}s")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
    else:
        print(f"⚠️  Image not found: {image_path}")
    
    # Test 5: Image inference with POC screenshot (optional)
    # print("\n[Optional] Test: Multimodal Generation - POC Interface")
    # print("-" * 70)
    # image_path = Path("docs/figures/poc.png")
    # if image_path.exists():
    #     try:
    #         question = "Analyze this interface. What features and components can you identify?"
    #         print(f"Query: {question}")
    #         print(f"Image: {image_path}")
    #         response, response_time = client.chat(question, str(image_path))
    #         print(f"\nResponse:\n{response}")
    #         print(f"\n⏱️  Response Time: {response_time:.2f}s")
    #     except Exception as e:
    #         print(f"❌ Error: {str(e)}")
    # else:
    #     print(f"⚠️  Image not found: {image_path}")
    
    # Test 5: Batch embedding extraction
    print("\n[6/7] Test: Batch Embedding Extraction (5 requests)")
    print("-" * 70)
    try:
        batch_queries = [
            "What is a useful concept?",
            "Explain an important idea",
            "How do complex systems work?",
            "What is innovation?",
            "Tell me about progress?",
        ]
        print(f"Batch size: {len(batch_queries)}")
        print(f"Queries: {batch_queries[:3]}...")
        results = client.batch_chat(batch_queries, mode="embed")
        print(f"✓ Batch embeddings extracted successfully")
        for i, (embedding, response_time) in enumerate(results):
            print(f"  [{i+1}] Dim: {embedding.shape}, L2 norm: {np.linalg.norm(embedding):.4f}, Time: {response_time:.2f}s")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    # Test 6: Batch text generation
    print("\n[7/7] Test: Batch Text Generation (3 requests)")
    print("-" * 70)
    try:
        batch_queries = [
            "Hello, are you there?",
            "What is your name?",
            "Tell me a joke",
        ]
        print(f"Batch size: {len(batch_queries)}")
        results = client.batch_chat(batch_queries)
        print(f"✓ Batch generation completed successfully")
        for i, (response, response_time) in enumerate(results):
            print(f"  [{i+1}] {response[:60]}... (Time: {response_time:.2f}s)")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    
    print("\n" + "=" * 70)
    print("Tests Complete!")
    print("=" * 70)
    print("\nUsage:")
    print("  python agent/client/triton_client.py          # Use HTTP (port 8000)")
    print("  python agent/client/triton_client.py --grpc   # Use gRPC (port 8001)")
    print("\nAPI:")
    print("  client.chat(message)                          # Generate text")
    print("  client.chat(message, image_path)              # Generate with image")
    print("  client.chat(message, mode='embed')            # Extract text embedding")
    print("  client.chat(message, image_path, mode='embed') # Extract multimodal embedding")
    print("  client.batch_chat(messages)                   # Batch generate (max 32)")
    print("  client.batch_chat(messages, mode='embed')     # Batch embeddings (max 32)")

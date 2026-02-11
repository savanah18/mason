"""
Triton client for long context summarization with Qwen3.
Specifically designed for testing long-context capabilities of large language models.
"""

import tritonclient.http as httpclient
import tritonclient.grpc as grpcclient
from typing import Optional, Tuple, Dict, List
import base64
import numpy as np
from pathlib import Path
import uuid
import time
import json
from dataclasses import dataclass, asdict
from enum import Enum


class SummarizationLevel(Enum):
    """Summarization detail levels."""
    BRIEF = "brief"
    DETAILED = "detailed"
    COMPREHENSIVE = "comprehensive"


@dataclass
class SummarizationResult:
    """Result from summarization task."""
    summary: str
    level: str
    input_tokens: int
    output_tokens: int
    processing_time: float
    model: str
    session_id: str


class SummarizationMetrics:
    """Metrics from summarization."""
    def __init__(self, summary: str, input_text: str, output_tokens: int, processing_time: float):
        self.summary = summary
        self.input_length = len(input_text)
        self.output_length = len(summary)
        self.input_tokens_estimated = len(input_text) // 4  # rough approximation
        self.output_tokens_estimated = output_tokens
        self.latency_ms = processing_time * 1000
        self.compression_ratio = self.input_length / max(self.output_length, 1)
        self.request_id = str(uuid.uuid4())
    
    def to_dict(self):
        return {
            "input_length": self.input_length,
            "output_length": self.output_length,
            "input_tokens_estimated": self.input_tokens_estimated,
            "output_tokens_estimated": self.output_tokens_estimated,
            "compression_ratio": self.compression_ratio,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id
        }


class TritonSummarizationClient:
    """Base class for Triton summarization clients."""
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        url: str = None,
        model_name: str = "qwen3-vl",
        model_version: str = "1",
        use_grpc: bool = False,
        session_id: Optional[str] = None,
        timeout: float = 300.0
    ):
        """Initialize client."""
        # Handle url parameter
        if url:
            if ":" in url:
                self.host, port_str = url.rsplit(":", 1)
                self.port = int(port_str)
            else:
                self.host = url
                self.port = port or 8000
        else:
            self.host = host or "localhost"
            self.port = port or 8000
        
        self.model_name = model_name
        self.model_version = model_version
        self.use_grpc = use_grpc
        self.session_id = session_id or str(uuid.uuid4())
        self.timeout = int(timeout)
        self.client = None
        
    def check_health(self) -> bool:
        """Check if Triton server is healthy."""
        raise NotImplementedError
    
    def summarize(
        self,
        text: str,
        level: SummarizationLevel = SummarizationLevel.BRIEF,
        max_tokens: int = 1000,
        custom_instructions: str = None
    ) -> Tuple[str, 'SummarizationMetrics']:
        """Summarize text."""
        raise NotImplementedError
    
    def summarize_file(
        self,
        file_path: str,
        level: SummarizationLevel = SummarizationLevel.BRIEF,
        custom_instructions: str = None
    ) -> Tuple[str, 'SummarizationMetrics']:
        """Summarize file content."""
        with open(file_path, 'r') as f:
            text = f.read()
        return self.summarize(text, level, custom_instructions=custom_instructions)
    
    def summarize_batch(
        self,
        texts: List[str],
        level: SummarizationLevel = SummarizationLevel.BRIEF
    ) -> List[Tuple[str, 'SummarizationMetrics']]:
        """Summarize multiple texts."""
        results = []
        for text in texts:
            result = self.summarize(text, level)
            results.append(result)
        return results
    
    def load_document(self, file_path: str) -> str:
        """Load document from file."""
        with open(file_path, 'r') as f:
            return f.read()
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation: ~4 chars per token)."""
        return len(text) // 4
    
    def analyze_long_context_performance(
        self,
        text: str,
        max_tokens: int = 2000,
        iterations: int = 1
    ) -> Dict:
        """Analyze performance across summarization levels and iterations."""
        results = {}
        latencies = []
        
        for i in range(iterations):
            level_results = {}
            for level in SummarizationLevel:
                start_time = time.time()
                summary, metrics = self.summarize(text, level, max_tokens)
                elapsed = time.time() - start_time
                latencies.append(elapsed * 1000)
                
                level_results[level.value] = {
                    "summary": summary,
                    "input_tokens": metrics.input_tokens_estimated,
                    "output_tokens": metrics.output_tokens_estimated,
                    "latency_ms": metrics.latency_ms,
                    "compression_ratio": metrics.compression_ratio
                }
            
            results[f"iteration_{i+1}"] = level_results
        
        # Calculate consistency metrics
        results["consistency"] = {
            "latency_mean": sum(latencies) / len(latencies) if latencies else 0,
            "latency_stddev": np.std(latencies) if latencies else 0,
            "latency_min": min(latencies) if latencies else 0,
            "latency_max": max(latencies) if latencies else 0
        }
        
        results["latency_ms"] = {
            "mean": sum(latencies) / len(latencies) if latencies else 0,
            "min": min(latencies) if latencies else 0,
            "max": max(latencies) if latencies else 0
        }
        
        return results


class TritonSummarizationHttpClient(TritonSummarizationClient):
    """HTTP-based Triton summarization client."""
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        url: str = None,
        model_name: str = "qwen3-vl",
        model_version: str = "1",
        session_id: Optional[str] = None,
        timeout: float = 300.0
    ):
        """Initialize HTTP client."""
        super().__init__(host=host, port=port or 8000, url=url, model_name=model_name, model_version=model_version, session_id=session_id, timeout=timeout)
        try:
            self.client = httpclient.InferenceServerClient(f"{self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to connect to Triton at {self.host}:{self.port}: {e}")
            self.client = None
    
    def check_health(self) -> bool:
        """Check if Triton server is healthy."""
        if not self.client:
            return False
        try:
            return self.client.is_server_live()
        except Exception as e:
            print(f"Health check failed: {e}")
            return False
    
    def summarize(
        self,
        text: str,
        level: SummarizationLevel = SummarizationLevel.BRIEF,
        max_tokens: int = 1000,
        custom_instructions: str = None
    ) -> Tuple[str, SummarizationMetrics]:
        """Summarize text using Triton. Returns (summary, metrics)."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        # Prepare prompt based on level
        level_instructions = {
            SummarizationLevel.BRIEF: "Provide a brief summary in 2-3 sentences.",
            SummarizationLevel.DETAILED: "Provide a detailed summary covering main points in 1-2 paragraphs.",
            SummarizationLevel.COMPREHENSIVE: "Provide a comprehensive summary covering all key details and implications."
        }
        
        instruction = level_instructions[level]
        if custom_instructions:
            instruction += "\n" + custom_instructions
        
        prompt = f"""Summarize the following text. {instruction}

Text:
{text}

Summary:"""
        
        try:
            start_time = time.time()
            
            # Prepare input using correct input names and shape
            # Model has max_batch_size: 32 so dims [-1] becomes [-1, -1] with batch prepended
            inputs = [
                httpclient.InferInput("message", [1, 1], "BYTES"),
            ]
            
            inputs[0].set_data_from_numpy(np.array([[prompt.encode()]], dtype=object))
            
            # Request only response output
            outputs = [
                httpclient.InferRequestedOutput("response"),
            ]
            response = self.client.infer(
                model_name=self.model_name,
                inputs=inputs,
                outputs=outputs,
                headers={"Mcp-Session-Id": self.session_id},
                timeout=self.timeout
            )
            
            # Extract results - handle different array shapes
            response_array = response.as_numpy("response")
            if response_array.ndim == 2:
                summary = response_array[0, 0].decode()
            else:
                summary = response_array[0].decode()
            
            # output_tokens not available from model - estimate from output length
            output_tokens = len(summary.split())  # rough estimate: 1 token per word
            
            processing_time = time.time() - start_time
            
            metrics = SummarizationMetrics(
                summary=summary,
                input_text=text,
                output_tokens=output_tokens,
                processing_time=processing_time
            )
            
            return summary, metrics
        
        except Exception as e:
            print(f"Summarization failed: {e}")
            raise


class TritonSummarizationGrpcClient(TritonSummarizationClient):
    """gRPC-based Triton summarization client."""
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        url: str = None,
        model_name: str = "qwen3-vl",
        model_version: str = "1",
        session_id: Optional[str] = None,
        timeout: float = 300.0
    ):
        """Initialize gRPC client."""
        super().__init__(host=host, port=port or 8001, url=url, model_name=model_name, model_version=model_version, session_id=session_id, timeout=timeout)
        try:
            self.client = grpcclient.InferenceServerClient(f"{self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to connect to Triton at {self.host}:{self.port}: {e}")
            self.client = None
    
    def check_health(self) -> bool:
        """Check if Triton server is healthy."""
        if not self.client:
            return False
        try:
            return self.client.is_server_live()
        except Exception as e:
            print(f"Health check failed: {e}")
            return False
    
    def summarize(
        self,
        text: str,
        level: SummarizationLevel = SummarizationLevel.BRIEF,
        max_tokens: int = 1000,
        custom_instructions: str = None
    ) -> Tuple[str, SummarizationMetrics]:
        """Summarize text using Triton (gRPC). Returns (summary, metrics)."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        # Prepare prompt based on level
        level_instructions = {
            SummarizationLevel.BRIEF: "Provide a brief summary in 2-3 sentences.",
            SummarizationLevel.DETAILED: "Provide a detailed summary covering main points in 1-2 paragraphs.",
            SummarizationLevel.COMPREHENSIVE: "Provide a comprehensive summary covering all key details and implications."
        }
        
        instruction = level_instructions[level]
        if custom_instructions:
            instruction += "\n" + custom_instructions
        
        prompt = f"""Summarize the following text. {instruction}

Text:
{text}

Summary:"""
        
        try:
            start_time = time.time()
            
            # Prepare input using correct input names and shape
            # Model has max_batch_size: 32 so dims [-1] becomes [-1, -1] with batch prepended
            inputs = [
                grpcclient.InferInput("message", [1, 1], "BYTES"),
            ]
            
            inputs[0].set_data_from_numpy(np.array([[prompt.encode()]], dtype=object))
            
            # Request only response output
            outputs = [
                grpcclient.InferRequestedOutput("response"),
            ]
            response = self.client.infer(
                model_name=self.model_name,
                inputs=inputs,
                outputs=outputs,
                headers={"session-id": self.session_id},
                timeout=self.timeout
            )
            
            # Extract results - handle different array shapes
            response_array = response.as_numpy("response")
            if response_array.ndim == 2:
                summary = response_array[0, 0].decode()
            else:
                summary = response_array[0].decode()
            
            # output_tokens not available from model - estimate from output length
            output_tokens = len(summary.split())  # rough estimate: 1 token per word
            
            processing_time = time.time() - start_time
            
            metrics = SummarizationMetrics(
                summary=summary,
                input_text=text,
                output_tokens=output_tokens,
                processing_time=processing_time
            )
            
            return summary, metrics
        
        except Exception as e:
            print(f"Summarization failed: {e}")
            raise

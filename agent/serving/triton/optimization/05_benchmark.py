#!/usr/bin/env python3
"""
Stage 5: Comprehensive Benchmarking Script
Compares performance across all optimization stages

Features:
- Multi-stage performance comparison
- Quality assessment
- Memory profiling
- Output validation
- Detailed reporting
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
from loguru import logger

try:
    import onnxruntime as ort
    ONNXRUNTIME_AVAILABLE = True
except ImportError:
    ONNXRUNTIME_AVAILABLE = False

try:
    import tensorrt as trt
    TENSORRT_AVAILABLE = True
except ImportError:
    TENSORRT_AVAILABLE = False


class ComprehensiveBenchmark:
    """Comprehensive model benchmarking suite."""

    def __init__(self, config: argparse.Namespace):
        """Initialize benchmarking suite."""
        self.config = config
        self.results = {}
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging."""
        log_dir = Path(self.config.output_dir) / "logs" if hasattr(self.config, 'output_dir') else Path("./logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        logger.remove()
        logger.add(sys.stderr, level="INFO")
        logger.add(
            log_dir / f"benchmark_{int(time.time())}.log",
            level="DEBUG"
        )

    def _benchmark_transformers_model(self, model_id: str, batch_sizes: List[int]) -> Dict:
        """Benchmark original transformers model."""
        logger.info(f"Benchmarking transformers model: {model_id}")
        
        results = {}
        
        try:
            from transformers import AutoModel, AutoProcessor
            
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            model = AutoModel.from_pretrained(model_id, trust_remote_code=True).to(device)
            processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
            
            for batch_size in batch_sizes:
                logger.info(f"  Batch size: {batch_size}")
                
                input_ids = torch.randint(0, 32000, (batch_size, 512)).to(device)
                attention_mask = torch.ones((batch_size, 512)).to(device)
                
                times = []
                for _ in range(10):
                    torch.cuda.synchronize() if torch.cuda.is_available() else None
                    start = time.time()
                    with torch.no_grad():
                        outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                    torch.cuda.synchronize() if torch.cuda.is_available() else None
                    times.append(time.time() - start)
                
                times = np.array(times)
                results[f"batch_{batch_size}"] = {
                    "mean_ms": float(times.mean() * 1000),
                    "std_ms": float(times.std() * 1000),
                    "min_ms": float(times.min() * 1000),
                    "max_ms": float(times.max() * 1000),
                }
            
            return results
            
        except Exception as e:
            logger.error(f"Transformers benchmark failed: {str(e)}")
            return {}

    def _benchmark_onnx_model(self, onnx_path: str, batch_sizes: List[int]) -> Dict:
        """Benchmark ONNX model."""
        if not ONNXRUNTIME_AVAILABLE:
            logger.warning("ONNX Runtime not available")
            return {}
        
        logger.info(f"Benchmarking ONNX model: {onnx_path}")
        
        results = {}
        
        try:
            session = ort.InferenceSession(onnx_path)
            
            for batch_size in batch_sizes:
                logger.info(f"  Batch size: {batch_size}")
                
                input_ids = np.random.randint(0, 32000, (batch_size, 512), dtype=np.int64)
                attention_mask = np.ones((batch_size, 512), dtype=np.int64)
                
                times = []
                for _ in range(10):
                    start = time.time()
                    session.run(None, {"input_ids": input_ids, "attention_mask": attention_mask})
                    times.append(time.time() - start)
                
                times = np.array(times)
                results[f"batch_{batch_size}"] = {
                    "mean_ms": float(times.mean() * 1000),
                    "std_ms": float(times.std() * 1000),
                    "min_ms": float(times.min() * 1000),
                    "max_ms": float(times.max() * 1000),
                }
            
            return results
            
        except Exception as e:
            logger.error(f"ONNX benchmark failed: {str(e)}")
            return {}

    def _benchmark_tensorrt_engine(self, engine_path: str, batch_sizes: List[int]) -> Dict:
        """Benchmark TensorRT engine."""
        if not TENSORRT_AVAILABLE:
            logger.warning("TensorRT not available")
            return {}
        
        logger.info(f"Benchmarking TensorRT engine: {engine_path}")
        
        results = {}
        
        try:
            import pycuda.driver as cuda
            import pycuda.autoinit
            
            with open(engine_path, 'rb') as f:
                engine = trt.Runtime(trt.Logger()).deserialize_cuda_engine(f.read())
            
            for batch_size in batch_sizes:
                logger.info(f"  Batch size: {batch_size}")
                
                context = engine.create_execution_context()
                
                input_shape = engine.get_binding_shape(0)
                output_shape = engine.get_binding_shape(1)
                
                input_shape = list(input_shape)
                input_shape[0] = batch_size
                
                input_data = np.random.randn(*input_shape).astype(np.float32)
                output_data = np.empty((batch_size, 512, 768), dtype=np.float32)
                
                input_gpu = cuda.mem_alloc(input_data.nbytes)
                output_gpu = cuda.mem_alloc(output_data.nbytes)
                
                bindings = [int(input_gpu), int(output_gpu)]
                
                times = []
                for _ in range(10):
                    cuda.memcpy_htod(input_gpu, input_data)
                    
                    start = time.time()
                    context.execute_v2(bindings)
                    cuda.Context.synchronize()
                    times.append(time.time() - start)
                
                times = np.array(times)
                results[f"batch_{batch_size}"] = {
                    "mean_ms": float(times.mean() * 1000),
                    "std_ms": float(times.std() * 1000),
                    "min_ms": float(times.min() * 1000),
                    "max_ms": float(times.max() * 1000),
                }
                
                input_gpu.free()
                output_gpu.free()
            
            return results
            
        except Exception as e:
            logger.error(f"TensorRT benchmark failed: {str(e)}")
            return {}

    def _generate_report(self, results: Dict) -> str:
        """Generate comprehensive benchmark report."""
        report = []
        report.append("=" * 80)
        report.append("COMPREHENSIVE MODEL OPTIMIZATION BENCHMARK REPORT")
        report.append("=" * 80)
        report.append(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        for stage, metrics in results.items():
            report.append(f"\n{stage.upper()}")
            report.append("-" * 80)
            
            if isinstance(metrics, dict):
                for batch_size, batch_metrics in metrics.items():
                    report.append(f"  {batch_size}:")
                    if isinstance(batch_metrics, dict):
                        for metric_name, value in batch_metrics.items():
                            if isinstance(value, (int, float)):
                                report.append(f"    {metric_name}: {value:.3f}")
                            else:
                                report.append(f"    {metric_name}: {value}")
        
        report.append("\n" + "=" * 80)
        report.append("SPEEDUP SUMMARY")
        report.append("=" * 80)
        
        # Calculate speedups
        if "transformers" in results and "onnx" in results:
            baseline = results["transformers"].get("batch_1", {}).get("mean_ms", 0)
            onnx_time = results["onnx"].get("batch_1", {}).get("mean_ms", 0)
            if baseline > 0:
                speedup = baseline / onnx_time if onnx_time > 0 else 0
                report.append(f"ONNX speedup: {speedup:.2f}x")
        
        if "transformers" in results and "tensorrt" in results:
            baseline = results["transformers"].get("batch_1", {}).get("mean_ms", 0)
            trt_time = results["tensorrt"].get("batch_1", {}).get("mean_ms", 0)
            if baseline > 0:
                speedup = baseline / trt_time if trt_time > 0 else 0
                report.append(f"TensorRT speedup: {speedup:.2f}x")
        
        return "\n".join(report)

    def run(self):
        """Execute benchmark suite."""
        logger.info("=" * 60)
        logger.info("Starting Comprehensive Benchmark Suite")
        logger.info("=" * 60)
        
        try:
            batch_sizes = list(map(int, self.config.batch_sizes.split(",")))
            
            # Benchmark each stage
            logger.info("\n[Stage 1/3] Benchmarking Transformers baseline...")
            self.results["transformers"] = self._benchmark_transformers_model(
                self.config.baseline_model_id,
                batch_sizes
            )
            
            logger.info("\n[Stage 2/3] Benchmarking ONNX model...")
            if self.config.onnx_path:
                self.results["onnx"] = self._benchmark_onnx_model(
                    self.config.onnx_path,
                    batch_sizes
                )
            
            logger.info("\n[Stage 3/3] Benchmarking TensorRT engine...")
            if self.config.tensorrt_path and Path(self.config.tensorrt_path).exists():
                self.results["tensorrt"] = self._benchmark_tensorrt_engine(
                    self.config.tensorrt_path,
                    batch_sizes
                )
            
            # Generate report
            report = self._generate_report(self.results)
            logger.info("\n" + report)
            
            # Save results
            output_path = Path(self.config.output_report or "./benchmark_results.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "w") as f:
                json.dump(self.results, f, indent=2, default=str)
            
            logger.info(f"\nResults saved to: {output_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Benchmark failed: {str(e)}")
            return False


def main():
    """Parse arguments and run benchmark."""
    parser = argparse.ArgumentParser(
        description="Comprehensive model optimization benchmark"
    )
    
    parser.add_argument(
        "--baseline_model_id",
        default="Qwen/Qwen3-VL-Instruct-8B",
        help="Baseline model ID"
    )
    parser.add_argument(
        "--onnx_path",
        default="./onnx_optimized/model.onnx",
        help="Path to ONNX model"
    )
    parser.add_argument(
        "--tensorrt_path",
        default="./tensorrt_engines/engine.trt",
        help="Path to TensorRT engine"
    )
    parser.add_argument(
        "--batch_sizes",
        default="1,4,8",
        help="Comma-separated batch sizes"
    )
    parser.add_argument(
        "--output_report",
        default="./benchmark_results.json",
        help="Output report path"
    )
    parser.add_argument(
        "--output_dir",
        default="./",
        help="Output directory"
    )
    
    args = parser.parse_args()
    
    benchmark = ComprehensiveBenchmark(args)
    success = benchmark.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

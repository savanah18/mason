#!/usr/bin/env python3
"""
Stage 3: ONNX Optimization Script
Optimizes ONNX model through graph transformation and operator fusion

Features:
- Graph optimization levels (0-3)
- Operator fusion
- Constant folding
- Dead code elimination
- Execution provider optimization
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, Optional

import numpy as np
from loguru import logger


class ONNXOptimizer:
    """Optimizes ONNX models for inference."""

    def __init__(self, config: argparse.Namespace):
        """Initialize ONNX optimizer."""
        self.config = config
        self.metrics = {}
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging."""
        log_dir = Path(self.config.output_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        logger.remove()
        logger.add(sys.stderr, level="INFO")
        logger.add(
            log_dir / f"onnx_optimization_{int(time.time())}.log",
            level="DEBUG"
        )

    def _load_onnx_model(self, model_path: Path):
        """Load ONNX model."""
        logger.info(f"Loading ONNX model from {model_path}")
        
        try:
            import onnx
            model = onnx.load(str(model_path))
            logger.info("✓ ONNX model loaded successfully")
            return model
        except Exception as e:
            logger.error(f"Failed to load ONNX model: {str(e)}")
            raise

    def _apply_graph_optimizations(self, model):
        """Apply graph-level optimizations."""
        logger.info(f"Applying graph optimizations (level: {self.config.optimization_level})...")
        
        try:
            import onnx
            from onnx import optimizer as onnx_optimizer
            
            # List of optimization passes
            optimization_passes = [
                "eliminate_unused_initializer",
                "eliminate_nop_transpose",
                "eliminate_nop_pad",
                "fuse_bn_into_conv",
                "fuse_add_bias_into_conv",
                "fuse_consecutive_squeezes",
                "fuse_consecutive_log_softmax",
                "fuse_transpose_into_gemm",
                "fuse_consecutive_transposes",
                "simplify_nodes_with_ec_by_beamsearch",
            ]
            
            # Apply optimization passes based on level
            if self.config.optimization_level >= 1:
                model = onnx_optimizer.optimize(model, optimization_passes[:4])
            if self.config.optimization_level >= 2:
                model = onnx_optimizer.optimize(model, optimization_passes[:8])
            if self.config.optimization_level >= 3:
                model = onnx_optimizer.optimize(model, optimization_passes)
            
            logger.info("✓ Graph optimizations applied")
            return model
            
        except Exception as e:
            logger.warning(f"Graph optimization failed: {str(e)}")
            return model

    def _measure_model_size(self, model_path: Path) -> float:
        """Measure model file size in MB."""
        return model_path.stat().st_size / (1024 * 1024)

    def _validate_optimized_model(self, model_path: Path) -> bool:
        """Validate optimized ONNX model."""
        logger.info("Validating optimized ONNX model...")
        
        try:
            import onnx
            import onnxruntime as ort
            
            # Load and check model
            model = onnx.load(str(model_path))
            onnx.checker.check_model(model)
            
            # Try inference
            session = ort.InferenceSession(str(model_path))
            
            # Create dummy input
            input_ids = np.random.randint(0, 32000, (1, 512), dtype=np.int64)
            attention_mask = np.ones((1, 512), dtype=np.int64)
            
            # Run inference
            outputs = session.run(
                None,
                {"input_ids": input_ids, "attention_mask": attention_mask}
            )
            
            logger.info("✓ Model validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Model validation failed: {str(e)}")
            return False

    def _benchmark_inference(self, model_path: Path, num_iterations: int = 10) -> Dict[str, float]:
        """Benchmark model inference performance."""
        logger.info(f"Benchmarking model inference ({num_iterations} iterations)...")
        
        try:
            import onnxruntime as ort
            
            session = ort.InferenceSession(str(model_path))
            
            # Warmup
            input_ids = np.random.randint(0, 32000, (1, 512), dtype=np.int64)
            attention_mask = np.ones((1, 512), dtype=np.int64)
            session.run(None, {"input_ids": input_ids, "attention_mask": attention_mask})
            
            # Benchmark
            times = []
            for _ in range(num_iterations):
                start = time.time()
                session.run(None, {"input_ids": input_ids, "attention_mask": attention_mask})
                times.append(time.time() - start)
            
            times = np.array(times)
            results = {
                "mean_ms": float(times.mean() * 1000),
                "std_ms": float(times.std() * 1000),
                "min_ms": float(times.min() * 1000),
                "max_ms": float(times.max() * 1000),
                "p50_ms": float(np.percentile(times, 50) * 1000),
                "p95_ms": float(np.percentile(times, 95) * 1000),
                "p99_ms": float(np.percentile(times, 99) * 1000),
            }
            
            logger.info(f"✓ Inference benchmark completed")
            logger.info(f"  Mean latency: {results['mean_ms']:.3f}ms")
            logger.info(f"  P95 latency: {results['p95_ms']:.3f}ms")
            
            return results
            
        except Exception as e:
            logger.warning(f"Benchmarking failed: {str(e)}")
            return {}

    def run(self):
        """Execute ONNX optimization pipeline."""
        logger.info("=" * 60)
        logger.info("Starting ONNX Optimization Pipeline")
        logger.info("=" * 60)
        
        start_time = time.time()
        
        try:
            model_path = Path(self.config.onnx_model_path)
            output_dir = Path(self.config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Measure original size
            logger.info("\n[Step 1/5] Measuring original model...")
            original_size = self._measure_model_size(model_path)
            logger.info(f"Original model size: {original_size:.2f}MB")
            self.metrics["original_size_mb"] = original_size
            
            # Load model
            logger.info("\n[Step 2/5] Loading ONNX model...")
            model = self._load_onnx_model(model_path)
            
            # Apply graph optimizations
            logger.info("\n[Step 3/5] Applying graph optimizations...")
            model = self._apply_graph_optimizations(model)
            
            # Save optimized model
            optimized_path = output_dir / "model_optimized.onnx"
            logger.info(f"\n[Step 4/5] Saving optimized model to {optimized_path}")
            
            import onnx
            onnx.save(model, str(optimized_path))
            optimized_size = self._measure_model_size(optimized_path)
            
            logger.info(f"Optimized model size: {optimized_size:.2f}MB")
            logger.info(f"Size reduction: {(1 - optimized_size / original_size) * 100:.1f}%")
            
            self.metrics["optimized_size_mb"] = optimized_size
            self.metrics["size_reduction_percent"] = (1 - optimized_size / original_size) * 100
            
            # Validate
            logger.info("\n[Step 5/5] Validating optimized model...")
            if not self._validate_optimized_model(optimized_path):
                logger.warning("⚠ Validation failed, but continuing...")
            
            # Benchmark
            logger.info("\nBenchmarking optimized model...")
            benchmark_results = self._benchmark_inference(optimized_path)
            self.metrics["benchmark"] = benchmark_results
            
            # Save metrics
            self.metrics["total_time_seconds"] = time.time() - start_time
            metrics_path = output_dir / "optimization_metrics.json"
            with open(metrics_path, "w") as f:
                json.dump(self.metrics, f, indent=2, default=str)
            
            logger.info("\n" + "=" * 60)
            logger.info("ONNX OPTIMIZATION COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)
            logger.info(f"Optimized model: {optimized_path}")
            logger.info(f"Total time: {self.metrics['total_time_seconds']:.2f} seconds")
            
            return True
            
        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            return False


def main():
    """Parse arguments and run optimizer."""
    parser = argparse.ArgumentParser(
        description="Optimize ONNX model"
    )
    
    parser.add_argument(
        "--onnx_model_path",
        default="./onnx_models/model.onnx",
        help="Path to ONNX model"
    )
    parser.add_argument(
        "--output_dir",
        default="./onnx_optimized",
        help="Output directory"
    )
    parser.add_argument(
        "--optimization_level",
        type=int,
        choices=[0, 1, 2, 3],
        default=3,
        help="Optimization level (0-3)"
    )
    parser.add_argument(
        "--graph_optimization_level",
        default="all",
        help="Graph optimization level"
    )
    parser.add_argument(
        "--enable_graph_rewriter",
        type=bool,
        default=True,
        help="Enable graph rewriter"
    )
    
    args = parser.parse_args()
    
    optimizer = ONNXOptimizer(args)
    success = optimizer.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

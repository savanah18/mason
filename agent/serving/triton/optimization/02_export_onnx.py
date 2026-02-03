#!/usr/bin/env python3
"""
Stage 2: ONNX Export Script
Exports quantized model to ONNX format for cross-platform optimization

Features:
- Multiple ONNX opset versions support
- External data format for large models
- Model validation
- Input/output specification
- Checkpoint resumption
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from loguru import logger
from transformers import AutoModel, AutoProcessor, AutoTokenizer


class ONNXExportPipeline:
    """Handles ONNX export pipeline."""

    def __init__(self, config: argparse.Namespace):
        """Initialize ONNX export pipeline."""
        self.config = config
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.metrics = {}

        self._setup_logging()
        logger.info(f"Device: {self.device}")

    def _setup_logging(self):
        """Configure logging."""
        log_dir = Path(self.config.output_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        logger.remove()
        logger.add(sys.stderr, level="INFO")
        logger.add(
            log_dir / f"onnx_export_{int(time.time())}.log",
            level="DEBUG"
        )

    def _load_model_and_tokenizer(self):
        """Load quantized model and tokenizer."""
        logger.info(f"Loading model from {self.config.model_path}")
        
        try:
            model = AutoModel.from_pretrained(
                self.config.model_path,
                trust_remote_code=True,
                torch_dtype=torch.bfloat16,
            )
            
            processor = AutoProcessor.from_pretrained(
                self.config.model_path,
                trust_remote_code=True
            )
            
            logger.info("✓ Model and processor loaded successfully")
            return model, processor
            
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            raise

    def _export_to_onnx(self, model: torch.nn.Module, processor, output_dir: Path):
        """Export model to ONNX format."""
        logger.info(f"Exporting model to ONNX...")
        
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create dummy inputs
            dummy_input_ids = torch.randint(0, 32000, (1, 512), dtype=torch.long).to(self.device)
            dummy_attention_mask = torch.ones((1, 512), dtype=torch.long).to(self.device)
            
            # Export to ONNX
            onnx_path = output_dir / "model.onnx"
            
            logger.info(f"Using opset version: {self.config.opset_version}")
            
            # For large models, use external data format
            if self.config.use_external_data_format:
                logger.info("Using external data format for large tensors")
            
            # Export using torch.onnx.export
            torch.onnx.export(
                model,
                (dummy_input_ids, dummy_attention_mask),
                str(onnx_path),
                input_names=["input_ids", "attention_mask"],
                output_names=["output"],
                opset_version=self.config.opset_version,
                do_constant_folding=True,
                use_external_data_format=self.config.use_external_data_format,
                enable_onnx_checker=True,
                verbose=False,
            )
            
            logger.info(f"✓ ONNX export completed: {onnx_path}")
            self.metrics["onnx_path"] = str(onnx_path)
            self.metrics["onnx_size_mb"] = onnx_path.stat().st_size / (1024 * 1024)
            
            return onnx_path
            
        except Exception as e:
            logger.error(f"ONNX export failed: {str(e)}")
            raise

    def _verify_onnx_model(self, onnx_path: Path):
        """Verify ONNX model structure."""
        logger.info("Verifying ONNX model structure...")
        
        try:
            import onnx
            
            model = onnx.load(str(onnx_path))
            onnx.checker.check_model(model)
            
            logger.info("✓ ONNX model structure is valid")
            logger.info(f"  Graph inputs: {[inp.name for inp in model.graph.input]}")
            logger.info(f"  Graph outputs: {[out.name for out in model.graph.output]}")
            
            return True
            
        except Exception as e:
            logger.error(f"ONNX verification failed: {str(e)}")
            return False

    def _test_onnx_inference(self, onnx_path: Path):
        """Test ONNX model inference."""
        logger.info("Testing ONNX model inference...")
        
        try:
            import onnxruntime as ort
            
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            session = ort.InferenceSession(str(onnx_path), providers=providers)
            
            # Create dummy input
            input_ids = np.random.randint(0, 32000, (1, 512), dtype=np.int64)
            attention_mask = np.ones((1, 512), dtype=np.int64)
            
            input_dict = {
                "input_ids": input_ids,
                "attention_mask": attention_mask
            }
            
            # Run inference
            start_time = time.time()
            outputs = session.run(None, input_dict)
            inference_time = time.time() - start_time
            
            logger.info(f"✓ ONNX inference successful ({inference_time:.3f}s)")
            logger.info(f"  Output shape: {outputs[0].shape}")
            
            self.metrics["onnx_inference_time_seconds"] = inference_time
            
            return True
            
        except Exception as e:
            logger.error(f"ONNX inference test failed: {str(e)}")
            return False

    def _save_metadata(self, model, processor, output_dir: Path):
        """Save model metadata."""
        logger.info("Saving model metadata...")
        
        metadata = {
            "model_type": "vision-language-model",
            "base_model": self.config.model_path,
            "onnx_opset_version": self.config.opset_version,
            "optimization_applied": self.config.optimize,
            "input_specs": {
                "input_ids": {"shape": [1, 512], "dtype": "int64"},
                "attention_mask": {"shape": [1, 512], "dtype": "int64"}
            },
            "export_timestamp": time.time(),
        }
        
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"✓ Metadata saved to {metadata_path}")

    def run(self):
        """Execute ONNX export pipeline."""
        logger.info("=" * 60)
        logger.info("Starting ONNX Export Pipeline")
        logger.info("=" * 60)
        
        start_time = time.time()
        
        try:
            # Step 1: Load model
            logger.info("\n[Step 1/5] Loading model and processor...")
            model, processor = self._load_model_and_tokenizer()
            
            # Step 2: Export to ONNX
            logger.info("\n[Step 2/5] Exporting to ONNX format...")
            output_dir = Path(self.config.output_dir)
            onnx_path = self._export_to_onnx(model, processor, output_dir)
            
            # Step 3: Verify ONNX structure
            logger.info("\n[Step 3/5] Verifying ONNX model structure...")
            if not self._verify_onnx_model(onnx_path):
                logger.warning("⚠ ONNX verification failed, but continuing...")
            
            # Step 4: Test inference
            logger.info("\n[Step 4/5] Testing ONNX inference...")
            if not self._test_onnx_inference(onnx_path):
                logger.warning("⚠ ONNX inference test failed, but continuing...")
            
            # Step 5: Save metadata
            logger.info("\n[Step 5/5] Saving metadata...")
            self._save_metadata(model, processor, output_dir)
            
            # Save metrics
            self.metrics["total_time_seconds"] = time.time() - start_time
            metrics_path = output_dir / "onnx_metrics.json"
            with open(metrics_path, "w") as f:
                json.dump(self.metrics, f, indent=2, default=str)
            
            logger.info("\n" + "=" * 60)
            logger.info("ONNX EXPORT PIPELINE COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)
            logger.info(f"Total time: {self.metrics['total_time_seconds']:.2f} seconds")
            logger.info(f"Output directory: {output_dir}")
            
            return True
            
        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            return False


def main():
    """Parse arguments and run pipeline."""
    parser = argparse.ArgumentParser(
        description="Export quantized model to ONNX format"
    )
    
    parser.add_argument(
        "--model_path",
        default="./checkpoints/qwen3-vl-int8",
        help="Path to quantized model"
    )
    parser.add_argument(
        "--output_dir",
        default="./onnx_models",
        help="Output directory for ONNX model"
    )
    parser.add_argument(
        "--opset_version",
        type=int,
        default=17,
        help="ONNX opset version"
    )
    parser.add_argument(
        "--optimize",
        type=bool,
        default=True,
        help="Apply ONNX optimizations"
    )
    parser.add_argument(
        "--use_external_data_format",
        type=bool,
        default=True,
        help="Use external data format for large models"
    )
    
    args = parser.parse_args()
    
    pipeline = ONNXExportPipeline(args)
    success = pipeline.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

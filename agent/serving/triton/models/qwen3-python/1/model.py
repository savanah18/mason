"""
Triton Python backend for Qwen3-4B-Thinking model.
Implements TritonPythonModel interface for Triton Inference Server.
"""

import triton_python_backend_utils as pb_utils
import json
import numpy as np
from typing import Optional
import time
import os
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig
)


class SpecialTokens:
    """Special tokens for Qwen3 Thinking model."""
    THINK_END = 151668
    TEXT_END = 151643


class TritonPythonModel:
    """Triton Python backend model for Qwen3-4B-Thinking inference."""
    
    def initialize(self, args):
        """Initialize the model when Triton starts."""
        print("=" * 50)
        print("Initializing Qwen3-4B-Thinking Triton Model")
        print("=" * 50)
        
        self.model_config = json.loads(args['model_config'])
        self.model_name = args['model_name']
        
        # Get configuration from environment
        model_path = os.getenv(
            "MODE_CKPT", 
            "/app/tensorrt_llm/models/Qwen3-4B-Thinking-2507"
        )
        quantization_type = os.getenv("QUANTIZATION_TYPE", None)
        attention_impl = os.getenv("ATTENTION_IMPL", "sdpa")
        
        print(f"Model Path: {model_path}")
        print(f"Quantization: {quantization_type}")
        print(f"Attention Implementation: {attention_impl}")
        
        # Load model and tokenizer
        self.model, self.tokenizer = self._load_model(
            model_path=model_path,
            quantization_type=quantization_type,
            attention_impl=attention_impl
        )
        
        # Default generation parameters
        self.default_temperature = float(os.getenv("TEMPERATURE", "0.7"))
        self.default_top_p = float(os.getenv("TOP_P", "0.9"))
        self.max_new_tokens = int(os.getenv("MAX_NEW_TOKENS", "2048"))
        
        print("=" * 50)
        print("✓ Model initialized successfully!")
        print("=" * 50)
    
    def _load_model(self, model_path: str, quantization_type: str, attention_impl: str):
        """Load Qwen3-4B-Thinking model with optional quantization."""
        print(f"Loading model from {model_path}...")
        
        # Configure quantization
        quantization_config = None
        if quantization_type == "int4":
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )
        elif quantization_type == "int8":
            quantization_config = BitsAndBytesConfig(
                load_in_8bit=True
            )
        
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            quantization_config=quantization_config,
            device_map="auto",
            attn_implementation=attention_impl,
            torch_dtype=torch.bfloat16 if quantization_config is None else None,
            trust_remote_code=True
        ).eval()
        
        tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            trust_remote_code=True
        )
        
        print("✓ Model and tokenizer loaded successfully!")
        
        return model, tokenizer
    
    def execute(self, requests):
        """Process inference requests from Triton."""
        responses = []
        
        for request in requests:
            try:
                # Extract inputs
                input_ids_tensor = pb_utils.get_input_tensor_by_name(request, "input_ids")
                request_output_len_tensor = pb_utils.get_input_tensor_by_name(request, "request_output_len")
                temperature_tensor = pb_utils.get_input_tensor_by_name(request, "temperature")
                top_p_tensor = pb_utils.get_input_tensor_by_name(request, "runtime_top_p")
                
                # Convert to numpy arrays
                input_ids = input_ids_tensor.as_numpy()
                request_output_len = request_output_len_tensor.as_numpy()
                
                # Get generation parameters
                temperature = self.default_temperature
                if temperature_tensor is not None:
                    temperature = float(temperature_tensor.as_numpy()[0])
                
                top_p = self.default_top_p
                if top_p_tensor is not None:
                    top_p = float(top_p_tensor.as_numpy()[0])
                
                max_new_tokens = int(request_output_len[0])
                
                print(f"[Triton] Processing request with {input_ids.shape[1]} input tokens")
                print(f"[Triton] Generation params: max_new_tokens={max_new_tokens}, temp={temperature}, top_p={top_p}")
                
                # Run inference
                output_ids, sequence_length = self._inference(
                    input_ids=input_ids,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_p=top_p
                )
                
                # Create output tensors
                output_ids_tensor = pb_utils.Tensor(
                    "output_ids",
                    output_ids.astype(np.int32)
                )
                
                sequence_length_tensor = pb_utils.Tensor(
                    "sequence_length",
                    sequence_length.astype(np.int32)
                )
                
                response = pb_utils.InferenceResponse(
                    output_tensors=[output_ids_tensor, sequence_length_tensor]
                )
                responses.append(response)
                
            except Exception as e:
                print(f"Error in inference: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # Return error response with empty outputs
                error_output_ids = np.zeros((1, 1, 1), dtype=np.int32)
                error_sequence_length = np.zeros((1, 1), dtype=np.int32)
                
                error_response = pb_utils.InferenceResponse(
                    output_tensors=[
                        pb_utils.Tensor("output_ids", error_output_ids),
                        pb_utils.Tensor("sequence_length", error_sequence_length)
                    ]
                )
                responses.append(error_response)
        
        return responses
    
    def _inference(self, input_ids: np.ndarray, max_new_tokens: int, 
                   temperature: float, top_p: float):
        """
        Perform inference on input token IDs.
        
        Args:
            input_ids: Input token IDs [batch_size, seq_len]
            max_new_tokens: Maximum number of new tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
            
        Returns:
            output_ids: Generated token IDs [batch_size, beam_width, total_seq_len]
            sequence_length: Length of each sequence [batch_size, beam_width]
        """
        start_time = time.time()
        
        # Convert to torch tensor
        input_ids_torch = torch.from_numpy(input_ids).to(self.model.device)
        batch_size = input_ids_torch.shape[0]
        input_length = input_ids_torch.shape[1]
        
        print(f"[Triton] Input shape: {input_ids_torch.shape}")
        
        # Generate
        with torch.no_grad():
            outputs = self.model.generate(
                input_ids_torch,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=temperature,
                top_p=top_p,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                use_cache=True
            )
        
        gen_time = time.time() - start_time
        output_length = outputs.shape[1]
        new_tokens = output_length - input_length
        
        print(f"[Triton] Generated {new_tokens} tokens in {gen_time:.2f}s ({new_tokens/gen_time:.1f} tok/s)")
        
        # Convert to numpy and match TensorRT-LLM output format
        # TensorRT-LLM format: [batch_size, beam_width, seq_len]
        output_ids_np = outputs.cpu().numpy()
        output_ids_np = np.expand_dims(output_ids_np, axis=1)  # Add beam dimension
        
        # Sequence lengths: [batch_size, beam_width]
        sequence_lengths = np.full((batch_size, 1), output_length, dtype=np.int32)
        
        return output_ids_np, sequence_lengths
    
    def finalize(self):
        """Cleanup when Triton shuts down."""
        print("Finalizing Qwen3-4B-Thinking model")
        if hasattr(self, 'model'):
            del self.model
        if hasattr(self, 'tokenizer'):
            del self.tokenizer
        torch.cuda.empty_cache()

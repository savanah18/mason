"""
Triton Python backend for Qwen3-VL model.
Implements TritonPythonModel interface for Triton Inference Server.
"""

import triton_python_backend_utils as pb_utils
import json
import numpy as np
from typing import Optional, List, Dict, Any
import base64
import io
import time
from datetime import datetime
from pathlib import Path
import os
import torch
from transformers import (
    Qwen3VLForConditionalGeneration,
    AutoProcessor,
    BitsAndBytesConfig
)
from PIL import Image


class TritonPythonModel:
    """Triton Python backend model for Qwen3-VL inference."""
    
    def initialize(self, args):
        """Initialize the model when Triton starts."""
        print("=" * 50)
        print("Initializing Qwen3-VL Triton Model")
        print("=" * 50)
        
        self.model_config = json.loads(args['model_config'])
        self.model_name = args['model_name']
        
        # Get configuration from environment
        model_path = os.getenv(
            "MODEL_PATH", 
            "/root/workspace/lnd/aiops/vlm/Qwen/Qwen3-VL-8B-Instruct"
        )
        quantization_type = os.getenv("QUANTIZATION_TYPE", "int4")
        attention_impl = os.getenv("ATTENTION_IMPL", "sdpa")
        
        print(f"Model Path: {model_path}")
        print(f"Quantization: {quantization_type}")
        print(f"Attention Implementation: {attention_impl}")
        
        # Load model
        self.model, self.processor = self._load_model(
            model_path=model_path,
            quantization_type=quantization_type,
            attention_impl=attention_impl
        )
        
        # Initialize session-based state
        self.sessions = {}  # session_id -> {history, kv_cache, last_access}
        self.max_history = int(os.getenv("MAX_HISTORY", "5"))
        self.max_new_tokens = int(os.getenv("MAX_NEW_TOKENS", "512"))
        self.temperature = float(os.getenv("TEMPERATURE", "0.7"))
        self.top_p = float(os.getenv("TOP_P", "0.9"))
        self.session_timeout = int(os.getenv("SESSION_TIMEOUT", "3600"))  # 1 hour
        self.max_sessions = int(os.getenv("MAX_SESSIONS", "100"))
        
        print("=" * 50)
        print("✓ Model initialized successfully!")
        print("=" * 50)
    
    def _load_model(self, model_path: str, quantization_type: str, attention_impl: str):
        """Load Qwen3-VL model with optional quantization."""
        print(f"Loading model with transformers...")
        
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
        
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            quantization_config=quantization_config,
            device_map="auto",
            attn_implementation=attention_impl,
            torch_dtype=torch.bfloat16 if quantization_config is None else None
        ).eval()
        
        processor = AutoProcessor.from_pretrained(model_path)
        print("✓ Model loaded successfully!")
        
        return model, processor
    
    def execute(self, requests):
        """Process inference requests from Triton."""
        responses = []
        
        for request in requests:
            try:
                # Extract inputs
                message = pb_utils.get_input_tensor_by_name(request, "message")
                image_input = pb_utils.get_input_tensor_by_name(request, "image")
                mode_input = pb_utils.get_input_tensor_by_name(request, "mode")
                session_id_input = pb_utils.get_input_tensor_by_name(request, "session_id")
                
                # Get batch size from message tensor shape
                msg_array = message.as_numpy()
                batch_size = msg_array.shape[0]
                print(f"[Triton] Processing batch of {batch_size} requests")
                
                # Clean expired sessions
                self._cleanup_sessions()
                
                # Extract mode (same for all items in batch)
                mode = "generate"
                if mode_input is not None:
                    mode_array = mode_input.as_numpy()
                    mode_bytes = mode_array[0, 0] if mode_array.ndim > 1 else mode_array[0]
                    mode = mode_bytes.decode('utf-8') if isinstance(mode_bytes, bytes) else mode_bytes
                
                # Extract session_id (same for all items in batch)
                session_id = None
                if session_id_input is not None:
                    sid_array = session_id_input.as_numpy()
                    sid_bytes = sid_array[0, 0] if sid_array.ndim > 1 else sid_array[0]
                    session_id = sid_bytes.decode('utf-8') if isinstance(sid_bytes, bytes) else sid_bytes
                    if session_id:
                        print(f"[Triton] Using session: {session_id}")
                
                # Process each item in the batch
                batch_responses = []
                batch_embeddings = []
                batch_times = []
                
                for i in range(batch_size):
                    # Extract message for this batch item
                    message_bytes = msg_array[i, 0] if msg_array.ndim > 1 else msg_array[i]
                    message_str = message_bytes.decode('utf-8') if isinstance(message_bytes, bytes) else message_bytes
                    
                    # Extract image for this batch item (if provided)
                    image_base64 = None
                    if image_input is not None:
                        img_array = image_input.as_numpy()
                        if img_array.size > 0:
                            image_bytes = img_array[i, 0] if img_array.ndim > 1 else img_array[i]
                            if image_bytes:
                                image_base64 = image_bytes.decode('utf-8') if isinstance(image_bytes, bytes) else image_bytes
                    
                    start_time = time.time()
                    
                    if mode == "embed":
                        # Embedding extraction mode
                        print(f"[Triton] [{i+1}/{batch_size}] Extracting embedding for: {message_str[:50]}...")
                        embedding = self._extract_embedding(message_str, image_base64)
                        response_time = time.time() - start_time
                        print(f"[Triton] [{i+1}/{batch_size}] Embedding extracted in {response_time:.2f}s, dim={len(embedding)}")
                        
                        batch_responses.append(b"")
                        batch_embeddings.append(embedding)
                        batch_times.append(response_time)
                        
                    else:
                        # Generation mode (default)
                        print(f"[Triton] [{i+1}/{batch_size}] Starting inference for: {message_str[:50]}...")
                        response_text = self._inference(message_str, image_base64, session_id)
                        response_time = time.time() - start_time
                        print(f"[Triton] [{i+1}/{batch_size}] Inference completed in {response_time:.2f}s")
                        
                        batch_responses.append(response_text.encode('utf-8'))
                        batch_embeddings.append(np.array([], dtype=np.float32))
                        batch_times.append(response_time)
                
                # Construct batch response tensors
                if mode == "embed":
                    # Stack embeddings into batch
                    response_tensor = pb_utils.Tensor(
                        "response",
                        np.array(batch_responses, dtype=object).reshape(batch_size, 1)
                    )
                    embedding_tensor = pb_utils.Tensor(
                        "embedding",
                        np.stack(batch_embeddings).astype(np.float32)
                    )
                    time_tensor = pb_utils.Tensor(
                        "response_time",
                        np.array(batch_times, dtype=np.float32).reshape(batch_size, 1)
                    )
                else:
                    # Generation mode
                    response_tensor = pb_utils.Tensor(
                        "response",
                        np.array(batch_responses, dtype=object).reshape(batch_size, 1)
                    )
                    embedding_tensor = pb_utils.Tensor(
                        "embedding",
                        np.zeros((batch_size, 0), dtype=np.float32)
                    )
                    time_tensor = pb_utils.Tensor(
                        "response_time",
                        np.array(batch_times, dtype=np.float32).reshape(batch_size, 1)
                    )
                
                response = pb_utils.InferenceResponse(
                    output_tensors=[response_tensor, embedding_tensor, time_tensor]
                )
                responses.append(response)
                
            except Exception as e:
                print(f"Error in inference: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # Return error response
                error_response = pb_utils.InferenceResponse(
                    output_tensors=[
                        pb_utils.Tensor(
                            "response",
                            np.array([f"Error: {str(e)}".encode('utf-8')], dtype=object)
                        ),
                        pb_utils.Tensor(
                            "embedding",
                            np.array([[]], dtype=np.float32).reshape(1, 0)
                        ),
                        pb_utils.Tensor(
                            "response_time",
                            np.array([0.0], dtype=np.float32)
                        )
                    ]
                )
                responses.append(error_response)
        
        return responses
    
    def _extract_embedding(self, message: str, image_base64: Optional[str]) -> np.ndarray:
        """Extract embedding vector from the message."""
        if not message.strip():
            return np.array([], dtype=np.float32)
        
        # Build content
        content = [{"type": "text", "text": message}]
        
        # Decode image if provided
        image = None
        if image_base64:
            try:
                image_data = base64.b64decode(image_base64)
                image = Image.open(io.BytesIO(image_data))
                content.append({"type": "image", "image": image})
            except Exception as e:
                print(f"Warning: Failed to decode image: {str(e)}")
        
        messages = [{"role": "user", "content": content}]
        
        # Prepare inputs
        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=False,
            return_dict=True,
            return_tensors="pt"
        )
        inputs = inputs.to(self.model.device)
        
        # Extract hidden states
        with torch.no_grad():
            outputs = self.model(
                **inputs,
                output_hidden_states=True,
                return_dict=True
            )
            hidden_states = outputs.hidden_states[-1]  # Last layer
            
            # Mean pooling
            if 'attention_mask' in inputs:
                mask_expanded = inputs['attention_mask'].unsqueeze(-1).expand(hidden_states.size())
                sum_embeddings = torch.sum(hidden_states * mask_expanded, dim=1)
                sum_mask = torch.clamp(mask_expanded.sum(dim=1), min=1e-9)
                pooled = sum_embeddings / sum_mask
            else:
                pooled = torch.mean(hidden_states, dim=1)
            
            # Normalize
            embedding = pooled.cpu().numpy().squeeze()
            embedding = embedding / (np.linalg.norm(embedding) + 1e-9)
        
        return embedding
    
    def _inference(self, message: str, image_base64: Optional[str], session_id: Optional[str] = None) -> str:
        """Perform inference on the message with session-based KV cache."""
        inference_start = time.time()
        if not message.strip():
            return "Error: Message cannot be empty"
        
        # Build content
        content = [{
"type": "text", "text": message}]
        
        # Decode image if provided
        image = None
        if image_base64:
            try:
                decode_start = time.time()
                image_data = base64.b64decode(image_base64)
                image = Image.open(io.BytesIO(image_data))
                content.append({"type": "image", "image": image})
                print(f"[Triton] Image decode: {time.time() - decode_start:.2f}s")
            except Exception as e:
                print(f"Warning: Failed to decode image: {str(e)}")
        
        # Get or create session
        import uuid
        if not session_id:
            session_id = str(uuid.uuid4())
            print(f"[Triton] Created new session: {session_id}")
        
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "history": [],
                "kv_cache": None,
                "last_access": time.time()
            }
            print(f"[Triton] Initialized session {session_id}")
        
        session = self.sessions[session_id]
        session["last_access"] = time.time()
        
        # Add user message to session history
        session["history"].append({
            "role": "user",
            "content": content
        })
        
        # Slide context window
        if len(session["history"]) > self.max_history:
            session["history"] = session["history"][-self.max_history:]
            session["kv_cache"] = None  # Invalidate cache when trimming
            print(f"[Triton] Trimmed history to {len(session['history'])} messages")
        
        # Prepare inputs
        try:
            tokenize_start = time.time()
            inputs = self.processor.apply_chat_template(
                session["history"],
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt"
            )
            tokenize_time = time.time() - tokenize_start
            input_tokens = inputs['input_ids'].shape[1]
            
            cache_status = "cached" if session["kv_cache"] is not None else "no cache"
            print(f"[Triton] Tokenization: {tokenize_time:.2f}s | Input tokens: {input_tokens} | {cache_status}")
        except Exception as e:
            print(f"Error preparing inputs: {str(e)}")
            return f"Error preparing inputs: {str(e)}"
        
        inputs = inputs.to(self.model.device)
        
        # Inference with KV cache
        try:
            gen_start = time.time()
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    past_key_values=session["kv_cache"],
                    max_new_tokens=self.max_new_tokens,
                    do_sample=True,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    use_cache=True,
                    return_dict_in_generate=True
                )
                generated_ids = outputs.sequences
                
                # Save KV cache for next call
                if hasattr(outputs, 'past_key_values') and outputs.past_key_values is not None:
                    session["kv_cache"] = outputs.past_key_values
                    print(f"[Triton] KV cache saved for session {session_id}")
            
            gen_time = time.time() - gen_start
            output_tokens = generated_ids.shape[1] - input_tokens
            print(f"[Triton] Generation: {gen_time:.2f}s | Output tokens: {output_tokens} | Speed: {output_tokens/gen_time:.1f} tok/s")
            
            generated_ids_trimmed = [
                out_ids[len(in_ids):] 
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            
            output_text = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )
            
            response = output_text[0]
        except Exception as e:
            print(f"Error during generation: {str(e)}")
            return f"Error during generation: {str(e)}"
        
        # Add assistant response to session history
        session["history"].append({
            "role": "assistant",
            "content": [{"type": "text", "text": response}]
        })
        
        return response
    
    def _cleanup_sessions(self):
        """Remove expired sessions to prevent memory leaks."""
        current_time = time.time()
        expired = []
        
        for session_id, session in self.sessions.items():
            if current_time - session["last_access"] > self.session_timeout:
                expired.append(session_id)
        
        for session_id in expired:
            del self.sessions[session_id]
            print(f"[Triton] Cleaned expired session: {session_id}")
        
        # Enforce max sessions limit (LRU eviction)
        if len(self.sessions) > self.max_sessions:
            sorted_sessions = sorted(
                self.sessions.items(),
                key=lambda x: x[1]["last_access"]
            )
            to_remove = len(self.sessions) - self.max_sessions
            for session_id, _ in sorted_sessions[:to_remove]:
                del self.sessions[session_id]
                print(f"[Triton] Evicted session (LRU): {session_id}")
    
    def finalize(self):
        """Cleanup when Triton shuts down."""
        print("Finalizing Qwen3-VL model")
        if hasattr(self, 'model'):
            del self.model
        if hasattr(self, 'processor'):
            del self.processor
        if hasattr(self, 'sessions'):
            self.sessions.clear()

"""
Preprocessing model for Qwen3 Ensemble.
Tokenizes OpenAI-style messages into input_ids for TensorRT-LLM.
"""

import triton_python_backend_utils as pb_utils
import numpy as np
import json
from transformers import AutoProcessor


class TritonPythonModel:
    """Preprocessing model - converts text to input_ids."""
    
    def initialize(self, args):
        """Load tokenizer/processor."""
        print("=" * 50)
        print("Initializing Qwen3 Preprocessing Model")
        print("=" * 50)
        
        # Load processor for tokenization and chat template
        model_path = "/models/qwen3-tensorrtllm/tokenizer"
        self.processor = AutoProcessor.from_pretrained(model_path)
        
        # System prompt for structured output
        self.system_prompt = """You are a helpful AI assistant with the ability to think through problems step-by-step.
Do not be verbose in your thinking and answer directly. 
Do not include examples and do not think out loud unnecessarily."""
        
        print(f"✓ Processor loaded from {model_path}")
        print("=" * 50)
    
    def execute(self, requests):
        """
        Tokenize messages into input_ids.
        
        Input:
            messages: JSON string of OpenAI messages [{"role": "user", "content": "..."}]
            max_tokens: Optional max output tokens (default: 1024)
            temperature: Optional temperature (default: 0.7)
            top_p: Optional top_p (default: 0.9)
            
        Output:
            INPUT_IDS: Tokenized input [batch, seq_len]
            REQUEST_OUTPUT_LEN: Max tokens to generate
            TEMPERATURE: Temperature value
            TOP_P: Top-p value
            INPUT_LENGTH: Length of input tokens (for skipping during decode)
        """
        responses = []
        
        for request in requests:
            try:
                # Extract inputs
                messages_tensor = pb_utils.get_input_tensor_by_name(request, "messages")
                max_tokens_tensor = pb_utils.get_input_tensor_by_name(request, "max_tokens")
                temperature_tensor = pb_utils.get_input_tensor_by_name(request, "temperature")
                top_p_tensor = pb_utils.get_input_tensor_by_name(request, "top_p")
                
                # Get messages (expecting JSON string)
                messages_bytes = messages_tensor.as_numpy()[0]
                if isinstance(messages_bytes, bytes):
                    messages_str = messages_bytes.decode('utf-8')
                else:
                    messages_str = str(messages_bytes)
                
                messages = json.loads(messages_str)
                
                # Add system prompt if not present
                if not messages or messages[0].get("role") != "system":
                    full_conversation = [{"role": "system", "content": self.system_prompt}] + messages
                else:
                    full_conversation = messages
                
                print(f"[Preprocessing] Tokenizing {len(full_conversation)} messages")
                
                # Tokenize using chat template
                inputs = self.processor.apply_chat_template(
                    full_conversation,
                    tokenize=True,
                    return_tensors="pt"
                )
                
                # Convert to NumPy int32 with shape [1, N]
                input_tokens = inputs.cpu().numpy().astype(np.int32)
                if input_tokens.ndim == 1:
                    input_tokens = np.expand_dims(input_tokens, axis=0)
                
                input_length = input_tokens.shape[1]
                print(f"[Preprocessing] Input tokens: {input_length}")
                
                # Get parameters with defaults
                if max_tokens_tensor is not None:
                    max_tokens = int(max_tokens_tensor.as_numpy()[0])
                else:
                    max_tokens = 1024
                
                if temperature_tensor is not None:
                    temperature = float(temperature_tensor.as_numpy()[0])
                else:
                    temperature = 0.7
                
                if top_p_tensor is not None:
                    top_p = float(top_p_tensor.as_numpy()[0])
                else:
                    top_p = 0.9
                
                # Create output tensors
                input_ids_out = pb_utils.Tensor(
                    "INPUT_IDS",
                    input_tokens
                )
                
                request_output_len_out = pb_utils.Tensor(
                    "REQUEST_OUTPUT_LEN",
                    np.array([max_tokens], dtype=np.int32)
                )
                
                temperature_out = pb_utils.Tensor(
                    "TEMPERATURE",
                    np.array([temperature], dtype=np.float32)
                )
                
                top_p_out = pb_utils.Tensor(
                    "TOP_P",
                    np.array([top_p], dtype=np.float32)
                )
                
                input_length_out = pb_utils.Tensor(
                    "INPUT_LENGTH",
                    np.array([input_length], dtype=np.int32)
                )
                
                response = pb_utils.InferenceResponse(
                    output_tensors=[
                        input_ids_out,
                        request_output_len_out,
                        temperature_out,
                        top_p_out,
                        input_length_out
                    ]
                )
                responses.append(response)
                
            except Exception as e:
                print(f"[Preprocessing] Error: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # Return error response
                error_response = pb_utils.InferenceResponse(
                    error=pb_utils.TritonError(f"Preprocessing failed: {str(e)}")
                )
                responses.append(error_response)
        
        return responses
    
    def finalize(self):
        """Cleanup."""
        print("Finalizing Qwen3 Preprocessing Model")
        if hasattr(self, 'processor'):
            del self.processor

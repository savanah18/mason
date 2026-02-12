"""
Postprocessing model for Qwen3 Ensemble.
Detokenizes output_ids from TensorRT-LLM into text.
"""

import triton_python_backend_utils as pb_utils
import numpy as np
from transformers import AutoProcessor
from enum import IntEnum


class SpecialTokensEnums(IntEnum):
    """Special tokens for Qwen3 thinking model."""
    THINK_END = 151668    # </think>
    TEXT_END = 151643     # <|endoftext|>


class TritonPythonModel:
    """Postprocessing model - converts output_ids to text."""
    
    def initialize(self, args):
        """Load processor for detokenization."""
        print("=" * 50)
        print("Initializing Qwen3 Postprocessing Model")
        print("=" * 50)
        
        # Load processor for detokenization
        model_path = "/models/qwen3-tensorrtllm/tokenizer"
        self.processor = AutoProcessor.from_pretrained(model_path)
        
        print(f"✓ Processor loaded from {model_path}")
        print("=" * 50)
    
    def execute(self, requests):
        """
        Detokenize output_ids into text.
        
        Input:
            output_ids: Token IDs from TensorRT-LLM [batch, beam, seq_len]
            sequence_length: Valid length of each sequence [batch, beam]
            input_length: Original input length (to skip during decode)
            
        Output:
            text_output: Decoded text
            usage: [prompt_tokens, completion_tokens, total_tokens]
        """
        responses = []
        
        for request in requests:
            try:
                # Extract inputs
                output_ids_tensor = pb_utils.get_input_tensor_by_name(request, "output_ids")
                sequence_length_tensor = pb_utils.get_input_tensor_by_name(request, "sequence_length")
                input_length_tensor = pb_utils.get_input_tensor_by_name(request, "input_length")
                
                output_ids = output_ids_tensor.as_numpy()
                sequence_length = sequence_length_tensor.as_numpy()
                input_length = int(input_length_tensor.as_numpy()[0])
                
                print(f"[Postprocessing] Output shape: {output_ids.shape}, Input length: {input_length}")
                
                # Process each batch item
                decoded_texts = []
                
                for i in range(output_ids.shape[0]):
                    valid_len = int(sequence_length[i][0])  # Get valid length
                    
                    # Skip input tokens - only decode the generated part
                    tokens = output_ids[i][0][input_length:valid_len].tolist()
                    
                    # Handle special tokens for thinking model
                    try:
                        # Find first occurrence of </think> token
                        think_end_idx = tokens.index(SpecialTokensEnums.THINK_END)
                    except ValueError:
                        think_end_idx = 0
                    
                    # Find and truncate at endoftext token
                    try:
                        text_end_idx = tokens.index(SpecialTokensEnums.TEXT_END)
                        tokens_to_decode = tokens[think_end_idx:text_end_idx]
                    except ValueError:
                        tokens_to_decode = tokens[think_end_idx:]
                    
                    # Decode the tokens
                    text = self.processor.decode(tokens_to_decode, skip_special_tokens=True)
                    decoded_texts.append(text.strip())
                    
                    print(f"[Postprocessing] Decoded {len(tokens_to_decode)} tokens")
                
                # Combine batch results
                final_text = "\n".join(decoded_texts)
                
                # Calculate usage statistics
                completion_tokens = valid_len - input_length
                usage = np.array([
                    input_length,           # prompt_tokens
                    completion_tokens,      # completion_tokens
                    valid_len               # total_tokens
                ], dtype=np.int32)
                
                # Create output tensors
                text_output = pb_utils.Tensor(
                    "text_output",
                    np.array([final_text.encode('utf-8')], dtype=object)
                )
                
                usage_output = pb_utils.Tensor(
                    "usage",
                    usage.reshape(1, 3)
                )
                
                response = pb_utils.InferenceResponse(
                    output_tensors=[text_output, usage_output]
                )
                responses.append(response)
                
            except Exception as e:
                print(f"[Postprocessing] Error: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # Return error response
                error_response = pb_utils.InferenceResponse(
                    error=pb_utils.TritonError(f"Postprocessing failed: {str(e)}")
                )
                responses.append(error_response)
        
        return responses
    
    def finalize(self):
        """Cleanup."""
        print("Finalizing Qwen3 Postprocessing Model")
        if hasattr(self, 'processor'):
            del self.processor

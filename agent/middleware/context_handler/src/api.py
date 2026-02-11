from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Optional #
import numpy as np #
import grpc
import tritonclient.grpc as grpcclient
from transformers import AutoProcessor
import uvicorn
import re
import json
from enum import IntEnum
import os

from models import ChatRequest
from consts import MiddleWareEnv

app = FastAPI(title="Context Handler API")

# System prompt for Qwen3 thinking model to structure output clearly
THINKING_SYSTEM_PROMPT = """
You are a helpful AI assistant with the ability to think through problems step-by-step.
Do not be verbose in your thinking and answer directly. 
Do not include examples and do not think out loud unnecessarily.
"""

class SpecialTokensEnums(IntEnum):
    THINK_END = 151668
    TEXT_END = 151643

def build_conversation_with_system(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Add system prompt to conversation history for better structured output.
    Qwen3 respects system prompts for output formatting.
    """
    return [
        {"role": "system", "content": THINKING_SYSTEM_PROMPT},
        *history
    ]


# Load processor (chat template + tokenizer)
print("Loading processor from:", MiddleWareEnv.PRETRAINED_MODEL_CONFIG_PATH)
processor = AutoProcessor.from_pretrained(MiddleWareEnv.PRETRAINED_MODEL_CONFIG_PATH)

# Simple in-memory conversation store (replace with Redis/DB in production)
conversation_store: Dict[str, List[Dict[str, str]]] = {}

# Initialize Triton gRPC client
print("Connecting to Triton gRPC server at:", MiddleWareEnv.GRPC_SERVER_URL)
triton_client = grpcclient.InferenceServerClient(url=MiddleWareEnv.GRPC_SERVER_URL)  # default gRPC port


@app.post("/chat")
def chat(req: ChatRequest):
    # Retrieve or initialize conversation history
    history = conversation_store.get(req.session_id, [])
    
    # Append new user message
    history.append({"role": "user", "content": req.user_message})

    # Build conversation with system prompt for structured output
    full_conversation = build_conversation_with_system(history)
    print("Full conversation with system prompt:", json.dumps(full_conversation, indent=2))
    
    # Tokenize with system prompt
    inputs = processor.apply_chat_template( 
        full_conversation, 
        tokenize=True, 
        return_tensors="pt" 
    ) 
    # Convert to NumPy int32 
    input_tokens = inputs.cpu().numpy().astype(np.int32) 
    # Ensure shape is [1, N] 
    input_tokens = np.expand_dims(input_tokens.flatten(), axis=0) 
    
    # Build Triton input tensor
    input_tensor = grpcclient.InferInput("input_ids", input_tokens.shape, "INT32") 
    input_tensor.set_data_from_numpy(input_tokens)
    
    # Use req.max_tokens for output length (engine supports up to 8192)
    output_len = np.array([4096], dtype=np.int32) 
    output_len_tensor = grpcclient.InferInput("request_output_len", [1], "INT32") 
    output_len_tensor.set_data_from_numpy(output_len)

    # Temperature and top_p sampling parameters
    temperature_tensor = grpcclient.InferInput("temperature", [1], "FP32")
    temperature_tensor.set_data_from_numpy(np.array([req.temperature], dtype=np.float32))

    top_p_tensor = grpcclient.InferInput("runtime_top_p", [1], "FP32")
    top_p_tensor.set_data_from_numpy(np.array([req.top_p], dtype=np.float32))

    # Run Triton inference
    outputs = [
        grpcclient.InferRequestedOutput("output_ids"),
        grpcclient.InferRequestedOutput("sequence_length")
    ]
    response = triton_client.infer(
        model_name=os.getenv("TRITON_MODEL_NAME", "qwen3-tensortllm"),  # default model name
        inputs=[input_tensor, output_len_tensor, temperature_tensor, top_p_tensor],
        outputs=outputs
    )

    output_ids = response.as_numpy("output_ids")
    sequence_length = response.as_numpy("sequence_length")

    # Get input length to skip input tokens when decoding
    input_length = input_tokens.shape[1]
    
    decoded_texts = []
    decoded_thinking_contents = []
    
    print("original content:", processor.decode(output_ids[0][0].tolist(), skip_special_tokens=False))
    for i in range(output_ids.shape[0]):  # batch dimension
        valid_len = int(sequence_length[i][0])  # scalar length
        # Skip input tokens - only decode the generated part
        tokens = output_ids[i][0][input_length:valid_len].tolist()  # squeeze beam dimension
        try:
            # Find first occurrence of 151668 (</think>)
            index = tokens.index(SpecialTokensEnums.THINK_END)
        except ValueError:
            index = 0
        
        # Find and truncate at endoftext token (151643)
        try:
            endoftext_index = tokens.index(SpecialTokensEnums.TEXT_END)
            tokens_to_decode = tokens[index:endoftext_index]
        except ValueError:
            tokens_to_decode = tokens[index:]
        
        thinking_content = processor.decode(tokens[:index], skip_special_tokens=False)
        content = processor.decode(tokens_to_decode, skip_special_tokens=False)
        #print("thinking content:", thinking_content) # no opening <think> tag
        #print("content:", content)
        decoded_texts.append(content)

    decoded_texts = "".join(decoded_texts).strip()


    print(f"[Response]\n{decoded_texts}\n")

    # Append assistant response to history (raw output)
    history.append({"role": "assistant", "content": decoded_texts})
    conversation_store[req.session_id] = history

    return {"response": decoded_texts, "history": history}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7000,
        log_level="info"
    )

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal, Union
import numpy as np
import grpc
import tritonclient.grpc as grpcclient
from transformers import AutoProcessor
import uvicorn
import re
import json
from enum import IntEnum
import os
import time
import uuid

from models import ChatRequest
from consts import MiddleWareEnv

app = FastAPI(
    title="OpenAPI Compatible Inference API",
    description="OpenAI-compatible inference serving with TensorRT-LLM backend",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

# System prompt for Qwen3 thinking model to structure output clearly
THINKING_SYSTEM_PROMPT = """
You are a helpful AI assistant with the ability to think through problems step-by-step.
Do not be verbose in your thinking and answer directly. 
Do not include examples and do not think out loud unnecessarily.
"""

# OpenAI-compatible request/response models
class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = Field(default="qwen3-tensorrtllm", description="Model name to use for inference")
    messages: List[Message] = Field(..., description="List of messages in the conversation")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    max_tokens: int = Field(default=1024, ge=1, le=4096, description="Maximum tokens to generate")
    stream: bool = Field(default=False, description="Whether to stream responses")
    n: int = Field(default=1, ge=1, le=1, description="Number of completions (currently only 1 supported)")

class CompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionChoice(BaseModel):
    index: int
    message: Message
    finish_reason: Literal["stop", "length", "content_filter"]

class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: CompletionUsage

class ModelInfo(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str = "organization"

class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: List[ModelInfo]

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


@app.get("/v1/models")
def list_models():
    """List available models - OpenAI compatible endpoint"""
    return ModelList(
        data=[
            ModelInfo(
                id="qwen3-tensorrtllm",
                created=int(time.time()),
                owned_by="local"
            )
        ]
    )

@app.get("/health")
def health_check():
    """Health check endpoint"""
    try:
        triton_client.is_server_live()
        return {"status": "healthy", "triton_server": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(req: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint"""
    if req.stream:
        raise HTTPException(status_code=400, detail="Streaming not yet supported")
    
    if req.n != 1:
        raise HTTPException(status_code=400, detail="Only n=1 is currently supported")
    
    # Convert messages to conversation format
    messages = [msg.dict() for msg in req.messages]
    # Add system prompt if not present
    if not messages or messages[0].get("role") != "system":
        full_conversation = [{"role": "system", "content": THINKING_SYSTEM_PROMPT}] + messages
    else:
        full_conversation = messages
    
    print("Full conversation:", json.dumps(full_conversation, indent=2))
    
    # Tokenize
    inputs = processor.apply_chat_template(
        full_conversation,
        tokenize=True,
        return_tensors="pt"
    )
    # Convert to NumPy int32
    input_tokens = inputs.cpu().numpy().astype(np.int32)
    # Ensure shape is [1, N]
    input_tokens = np.expand_dims(input_tokens.flatten(), axis=0)
    prompt_tokens = input_tokens.shape[1] 
    
    # Build Triton input tensor
    input_tensor = grpcclient.InferInput("input_ids", input_tokens.shape, "INT32")
    input_tensor.set_data_from_numpy(input_tokens)
    
    # Use req.max_tokens for output length
    output_len = np.array([req.max_tokens], dtype=np.int32) 
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
    
    start_time = time.time()
    response = triton_client.infer(
        model_name=req.model,
        inputs=[input_tensor, output_len_tensor, temperature_tensor, top_p_tensor],
        outputs=outputs
    )
    inference_time = time.time() - start_time

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
    completion_tokens = valid_len - input_length

    print(f"[Response] ({inference_time:.2f}s)\n{decoded_texts}\n")

    # Build OpenAI-compatible response
    response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    
    return ChatCompletionResponse(
        id=response_id,
        created=int(time.time()),
        model=req.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=Message(role="assistant", content=decoded_texts),
                finish_reason="stop" if valid_len < prompt_tokens + req.max_tokens else "length"
            )
        ],
        usage=CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        )
    )


@app.post("/chat")
def chat(req: ChatRequest):
    """Legacy chat endpoint for backward compatibility"""
    # Retrieve or initialize conversation history
    history = conversation_store.get(req.session_id, [])
    
    # Append new user message
    history.append({"role": "user", "content": req.user_message})

    # Build conversation with system prompt for structured output
    full_conversation = build_conversation_with_system(history)
    
    # Convert to OpenAI format and call the new endpoint
    messages = [Message(role=msg["role"], content=msg["content"]) for msg in full_conversation]
    openai_req = ChatCompletionRequest(
        model="qwen3-tensorrtllm",
        messages=messages,
        temperature=req.temperature,
        top_p=req.top_p,
        max_tokens=req.max_tokens
    )
    
    result = chat_completions(openai_req)
    decoded_texts = result.choices[0].message.content
    
    # Append assistant response to history
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

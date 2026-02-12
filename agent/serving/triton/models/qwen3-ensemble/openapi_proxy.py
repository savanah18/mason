#!/usr/bin/env python3
"""
OpenAPI-compatible proxy for Triton Ensemble.
Converts OpenAI format → Triton → OpenAI format.

This provides backward compatibility for clients expecting OpenAI API format
while using the high-performance Triton ensemble backend.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal
import tritonclient.grpc as grpcclient
import numpy as np
import json
import time
import uuid


app = FastAPI(
    title="OpenAPI Ensemble Proxy",
    description="OpenAI-compatible API backed by Triton Ensemble",
    version="2.0.0"
)

# Triton client
triton_client = grpcclient.InferenceServerClient("localhost:8001")


# OpenAI-compatible models
class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="qwen3-ensemble", description="Model name")
    messages: List[Message] = Field(..., description="Conversation messages")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    max_tokens: int = Field(default=1024, ge=1, le=4096)
    stream: bool = Field(default=False)
    n: int = Field(default=1, ge=1, le=1)


class CompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionChoice(BaseModel):
    index: int
    message: Message
    finish_reason: Literal["stop", "length"]


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
    owned_by: str = "triton"


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: List[ModelInfo]


@app.get("/v1/models")
def list_models():
    """List available models."""
    return ModelList(
        data=[
            ModelInfo(
                id="qwen3-ensemble",
                created=int(time.time()),
                owned_by="triton"
            )
        ]
    )


@app.get("/health")
def health_check():
    """Health check endpoint."""
    try:
        if triton_client.is_server_live():
            return {"status": "healthy", "backend": "triton-ensemble"}
        else:
            raise HTTPException(status_code=503, detail="Triton server not live")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(req: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint.
    Proxies to Triton Ensemble backend.
    """
    if req.stream:
        raise HTTPException(status_code=400, detail="Streaming not yet supported")
    
    if req.n != 1:
        raise HTTPException(status_code=400, detail="Only n=1 is supported")
    
    try:
        # Convert OpenAI messages to JSON string
        messages = [msg.dict() for msg in req.messages]
        messages_json = json.dumps(messages)
        
        print(f"[Proxy] Processing {len(messages)} messages")
        
        # Create Triton inputs
        messages_input = grpcclient.InferInput("messages", [1], "BYTES")
        messages_input.set_data_from_numpy(
            np.array([messages_json.encode()], dtype=object)
        )
        
        max_tokens_input = grpcclient.InferInput("max_tokens", [1], "INT32")
        max_tokens_input.set_data_from_numpy(
            np.array([req.max_tokens], dtype=np.int32)
        )
        
        temperature_input = grpcclient.InferInput("temperature", [1], "FP32")
        temperature_input.set_data_from_numpy(
            np.array([req.temperature], dtype=np.float32)
        )
        
        top_p_input = grpcclient.InferInput("top_p", [1], "FP32")
        top_p_input.set_data_from_numpy(
            np.array([req.top_p], dtype=np.float32)
        )
        
        # Request outputs
        outputs = [
            grpcclient.InferRequestedOutput("text_output"),
            grpcclient.InferRequestedOutput("usage")
        ]
        
        # Call Triton ensemble
        start_time = time.time()
        response = triton_client.infer(
            model_name="qwen3-ensemble",
            inputs=[messages_input, max_tokens_input, temperature_input, top_p_input],
            outputs=outputs
        )
        inference_time = time.time() - start_time
        
        # Extract results
        text_output = response.as_numpy("text_output")[0].decode('utf-8')
        usage = response.as_numpy("usage")[0]
        
        prompt_tokens = int(usage[0])
        completion_tokens = int(usage[1])
        total_tokens = int(usage[2])
        
        print(f"[Proxy] Completed in {inference_time:.2f}s ({completion_tokens} tokens)")
        
        # Determine finish reason
        finish_reason = "stop" if completion_tokens < req.max_tokens else "length"
        
        # Build OpenAI-compatible response
        response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        
        return ChatCompletionResponse(
            id=response_id,
            created=int(time.time()),
            model=req.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=Message(role="assistant", content=text_output),
                    finish_reason=finish_reason
                )
            ],
            usage=CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens
            )
        )
        
    except Exception as e:
        print(f"[Proxy] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("Starting OpenAPI Proxy for Triton Ensemble")
    print("=" * 60)
    print("FastAPI proxy: http://localhost:7000")
    print("Triton backend: localhost:8001")
    print("=" * 60)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7000,
        log_level="info"
    )

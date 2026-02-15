# AI Chat Assistant

OpenAPI-compatible AI chat assistant supporting various inference backends including TensorRT-LLM, vLLM, OpenAI, Triton, and more. Features high-performance inference with conversation context, token usage tracking, and easy backend switching.

## Current Features

- **Real-time AI chat** with OpenAPI-compatible endpoints
- **Backend flexibility**: Works with TensorRT-LLM, vLLM, Triton, OpenAI, and other OpenAPI-compatible servers
- **Conversation context**: Maintains chat history across multiple turns
- **Token usage tracking**: Monitor prompt, completion, and total tokens
- **Response timing** metrics for performance tracking
- **Chat persistence** with clear/reset functionality
- **Server health monitoring** with automatic status checks
- **Easy configuration** via environment variables
- **Production-ready** with comprehensive error handling

## Infrastructure

- **Backend**: OpenAPI-compatible inference server (default: `http://localhost:7000`)
- **Endpoints**:
  - `/v1/chat/completions`: Chat inference (OpenAI-compatible)
  - `/health`: Server health status
  - `/v1/models`: List available models
- **Supported Backends**:
  - TensorRT-LLM with OpenAPI middleware
  - vLLM (OpenAI-compatible mode)
  - Triton Inference Server (with OpenAPI adapter)
  - OpenAI API
  - LocalAI, Ollama, and other compatible servers
- **Configuration**: Set `MIDDLEWARE_URL` environment variable to change server endpoint

## API Format

### OpenAI-Compatible Request Format
```json
{
  "model": "qwen3-tensorrtllm",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Your question here"}
  ],
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 2048,
  "stream": false
}
```

### Response Format
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1707639600,
  "model": "qwen3-tensorrtllm",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Generated text response"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 42,
    "total_tokens": 57
  }
}
```

## Upcoming Features 🚀

- **Streaming responses** for real-time generation
- **RAG integration** for knowledge base retrieval
- **Function calling** support for tool use
- **Custom model switching** via UI
- **Performance profiling** and optimization dashboard
- **Multi-turn conversations** with context management
- **Prompt templates** library for common tasks
- **Export capabilities** for chat history
- **Embedding support** for semantic search

## Commands

- `AI Chat: Start` (command id: `aiChat.start`) — Initialize the AI assistant
- `AI Chat: Open Chat Assistant` (command id: `aiChat.openChat`) — Opens the chat panel

## Getting Started

### Prerequisites
1. **OpenAPI-compatible inference server** (e.g., TensorRT-LLM middleware)
   ```bash
   # Example: Start TensorRT-LLM middleware
   cd /root/workspace/lnd/aiops/apps/newbie-app/agent/middleware/context_handler
   python src/api.py
   ```
   
2. **Verify server is ready**:
   ```bash
   # Health check
   curl http://localhost:7000/health
   
   # List models
   curl http://localhost:7000/v1/models
   
   # Test chat endpoint
   curl -X POST http://localhost:7000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"qwen3-tensorrtllm","messages":[{"role":"user","content":"Hello"}]}'
   ```

3. **Server Configuration** (default: `http://localhost:7000`):
   - Set `MIDDLEWARE_URL` environment variable to change endpoint
   - Example: `export MIDDLEWARE_URL=http://your-server:8080`

### Extension Setup
1. Navigate to extension directory:
   ```bash
   cd agent/client/extensions/vscode
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Build and launch:
   ```bash
   npm run compile
   # or for continuous build: npm run watch
   ```
   
4. Press `F5` in VS Code to launch the Extension Development Host

5. Use `AI Chat: Open Chat Assistant` command to open the chat panel

6. Verify server connection - status will show in the header

## Packaging

- Install `vsce` if you want to package a `.vsix`:
  ```bash
  npm install -g @vscode/vsce
  npm run package
  ```

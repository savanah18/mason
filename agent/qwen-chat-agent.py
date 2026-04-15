"""
FastAPI Backend for Qwen Agent with MCP Tools
Provides stateless REST API for chat operations
"""
import os
from datetime import datetime
from typing import Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
import uvicorn

from templates.data_models.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatHistory
)
from templates.data_models.health import HealthResponse
from templates.core.chat_agent import ChatAgentBackend
from actions.tools.kafka.tools import (
    KafkaProduceMessage
)
from actions.tools.resource_collector.tools import (
    ResourceCollector
)
from actions.tools.kubernetes.tools import (
    KubernetesListWorkloads,
    KubernetesApplyResourceUpdate,
)
from actions.tools.helm.tools import (
    HelmAddRepository,
    HelmRegistryLogin,
    HelmUpdateRepositories,
    HelmListRepositories,
    HelmRemoveRepository,
    HelmTemplate,
    HelmLint,
    HelmInstall,
    HelmUpgrade,
    HelmListReleases,
    HelmGetHistory,
    HelmGetValues,
    HelmRollback,
    HelmUninstall,
    HelmTest,
)

from actions.tools.prompt_optimization.tools import (
    PromptOptimizationRetrieveWorkflows
)

# ============================================================================
# FastAPI App
# ============================================================================

# Global backend instance
backend = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize backend on startup."""
    global backend
    print("🚀 Backend service starting...")
    backend = ChatAgentBackend(
        llm_cfg_path = "./templates/llm/qwen.yaml",
        prompt_cfg_path = "./personas/chat/prompts.yaml",
        actuators = "./personas/chat/actuators.yaml",
        prune_intermediate_task_contexts = True
    )
    yield
    print("🛑 Backend service shutting down...")


app = FastAPI(
    title="Qwen Agent Backend",
    description="Stateless REST API for Qwen Agent with MCP Tools",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    if not backend:
        raise HTTPException(status_code=503, detail="Backend not initialized")
    
    status = backend.get_health_status()
    return HealthResponse(
        status=status["status"],
        mcp_tools_loaded=status["mcp_tools_loaded"],
        sessions_active=status["sessions_active"],
        backend_version=status["backend_version"]
    )


@app.post("/session/create", response_model=Dict[str, str])
async def create_session():
    """Create a new chat session."""
    if not backend:
        raise HTTPException(status_code=503, detail="Backend not initialized")
    
    session_id = await backend.create_session()
    return {"session_id": session_id}


@app.post("/chat/send", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """Send a message to the agent."""
    if not backend:
        raise HTTPException(status_code=503, detail="Backend not initialized")
    
    # Create session if not provided
    session_id = request.session_id or await backend.create_session()
    
    _, session = await backend.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    try:
        response, context_len, input_len, workflow_id = await backend.send_message(session_id, request.message, workflow_id=request.workflow_id)
        # Re-fetch session to ensure we have latest state
        _, session = await backend.get_session(session_id)
        total_msgs = len(session.messages)
        print(f"📤 Returning: context={context_len}, history={total_msgs}, input={input_len} chars")
        return ChatResponse(
            session_id=session_id,
            response=response,
            timestamp=datetime.utcnow().isoformat(),
            message_count=total_msgs,
            context_length=context_len,
            total_history=total_msgs,
            input_length=input_len,
            workflow_id=workflow_id
        )
    except Exception as e:
        print(f"⚠ Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/history/{session_id}", response_model=ChatHistory)
async def get_history(session_id: str):
    """Get chat history for a session."""
    if not backend:
        raise HTTPException(status_code=503, detail="Backend not initialized")
    
    _, session = await backend.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    return ChatHistory(
        session_id=session_id,
        messages=[ChatMessage(**msg) for msg in session.messages],
        created_at=session.created_at
    )


@app.post("/chat/clear/{session_id}", response_model=Dict[str, bool])
async def clear_chat(session_id: str):
    """Clear chat history for a session."""
    if not backend:
        raise HTTPException(status_code=503, detail="Backend not initialized")
    
    success = backend.clear_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    return {"cleared": success}


@app.delete("/session/{session_id}", response_model=Dict[str, bool])
async def delete_session(session_id: str):
    """Delete a session."""
    if not backend:
        raise HTTPException(status_code=503, detail="Backend not initialized")
    
    if session_id in backend.sessions:
        del backend.sessions[session_id]
        return {"deleted": True}
    
    raise HTTPException(status_code=404, detail=f"Session {session_id} not found")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("BACKEND_PORT", "8002"))
    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    
    print(f"🌐 Starting backend on {host}:{port}")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )

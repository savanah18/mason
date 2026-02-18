"""
FastAPI Backend for Qwen Agent with MCP Tools
Provides stateless REST API for chat operations
"""
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

import urllib.parse
import json5
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool
from qwen_agent.tools.mcp_manager import MCPManager
from qwen_agent.utils.output_beautify import typewriter_print


# ============================================================================
# Data Models
# ============================================================================

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    timestamp: str
    message_count: int
    context_length: int  # Number of messages sent to LLM
    total_history: int   # Total messages in session
    input_length: int    # Character count of prompt sent to LLM


class HistoryResponse(BaseModel):
    session_id: str
    messages: List[ChatMessage]
    created_at: str


class HealthResponse(BaseModel):
    status: str
    mcp_tools_loaded: int
    sessions_active: int
    backend_version: str


# ============================================================================
# Custom Tool
# ============================================================================

@register_tool('my_image_gen')
class MyImageGen(BaseTool):
    """AI painting (image generation) service."""
    description = 'AI painting (image generation) service, input text description, and return the image URL drawn based on text information.'
    parameters = [{
        'name': 'prompt',
        'type': 'string',
        'description': 'Detailed description of the desired image content, in English',
        'required': True
    }]

    def call(self, params: str, **kwargs) -> str:
        prompt = json5.loads(params)['prompt']
        prompt = urllib.parse.quote(prompt)
        return json5.dumps(
            {'image_url': f'https://image.pollinations.ai/prompt/{prompt}'},
            ensure_ascii=False)


# ============================================================================
# Agent Backend Service
# ============================================================================

class AgentBackend:
    """Manages agent sessions and chat state."""
    
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
        self.agent = None
        self.mcp_tools_count = 0
        self._initialize_agent()
    
    def _initialize_agent(self):
        """Initialize Qwen agent with MCP tools."""
        print("🔧 Initializing Qwen Agent...")
        
        # LLM Configuration
        llm_cfg = {
            'model': 'Qwen3-4B-Instruct',
            'model_server': os.getenv('LLM_SERVER', 'http://localhost:8001/v1'),
            'generate_cfg': {
                "temperature": 0.8,
                "top_p": 0.9,
                "repetition_penalty": 1.1        
            }
        }
        
        # System instruction
        system_instruction = '''
    You are an agent that manages services in a Kubernetes cluster.
    Use the Kubernetes MCP tools (prefixed with `kubernetes-`) for any cluster operations.
    Use the Helm MCP tools (prefixed with `helm-`) for Helm operations.
    Always provide detailed information about the operations you perform and their results.
'''
        
        # Initialize MCP tools with timeout
        mcp_tools = self._load_mcp_tools()
        self.mcp_tools_count = len(mcp_tools)
        
        tools = ['my_image_gen', 'code_interpreter'] + mcp_tools
        
        print(f"✓ Qwen Agent initialized with {self.mcp_tools_count} MCP tools")
        
        # Create agent
        self.agent = Assistant(
            llm=llm_cfg,
            system_message=system_instruction,
            function_list=tools,
            files=[]
        )
    
    def _load_mcp_tools(self, timeout=5) -> List:
        """Load MCP tools with timeout."""
        result = {"tools": [], "error": None}
        
        def _init():
            try:
                mcp_config = {
                    "mcpServers": {
                        "kubernetes": {
                            "type": "streamable-http",
                            "url": f"{os.getenv('KUBE_MCP_URL', 'http://localhost:8081')}/mcp",
                        },
                        # Helm disabled for now due to connectivity issues
                        # "helm": {
                        #     "type": "sse",
                        #     "url": f"{os.getenv('HELM_MCP_URL', 'http://localhost:8012')}/mcp",
                        # },
                    }
                }
                result["tools"] = MCPManager().initConfig(mcp_config)
                print(f"✓ Loaded {len(result['tools'])} MCP tools")
            except Exception as e:
                result["error"] = e
                print(f"⚠ Warning: Failed to initialize MCP servers: {e}")
        
        thread = threading.Thread(target=_init, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            print(f"⏱ MCP initialization timeout after {timeout}s")
            return []
        
        if result["error"]:
            return []
        
        return result["tools"]
    
    def create_session(self) -> str:
        """Create a new chat session."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "messages": [],
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
        }
        print(f"📝 Created session: {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID."""
        return self.sessions.get(session_id)
    
    def clear_session(self, session_id: str) -> bool:
        """Clear a chat session."""
        if session_id in self.sessions:
            self.sessions[session_id]["messages"] = []
            self.sessions[session_id]["last_updated"] = datetime.utcnow().isoformat()
            print(f"🗑 Cleared session: {session_id}")
            return True
        return False
    
    def send_message(self, session_id: str, user_message: str) -> tuple[str, int, int]:
        """Send a message and get response. Returns (response_text, context_length, input_length)."""
        if not self.agent:
            raise ValueError("Agent not initialized")
        
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Add user message to history
        messages = session["messages"]
        messages.append({"role": "user", "content": user_message})
        print(f"📝 After adding user message: {len(messages)} messages in history")
        
        # Get agent response
        combined_messages = messages.copy()
        context_length = len(combined_messages)
        
        # Calculate actual input size (character count)
        input_length = sum(len(str(msg.get('content', ''))) for msg in combined_messages)
        print(f"📊 Context: {context_length} messages, {input_length} chars sent to LLM")
        
        response_text = ""
        response_messages: List[Dict] = []
        try:
            for response in self.agent.run(messages=combined_messages):
                response_text = typewriter_print(response, response_text)
                if isinstance(response, dict):
                    response_messages.append(response)
        except Exception as e:
            response_text = f"Error: {str(e)}"
            response_messages = [{"role": "assistant", "content": response_text}]

        # Add assistant/tool responses to history
        # if response_messages:
        #     messages.extend(response_messages)
        # else:
        #     messages.append({"role": "assistant", "content": response_text})
        session["messages"].extend(response)
        print(f"✅ After agent response: {len(session['messages'])} total messages in session")
        
        session["last_updated"] = datetime.utcnow().isoformat()
        
        return response_text, context_length, input_length
    
    def get_health_status(self) -> Dict:
        """Get backend health status."""
        return {
            "status": "healthy",
            "mcp_tools_loaded": self.mcp_tools_count,
            "sessions_active": len(self.sessions),
            "backend_version": "1.0.0",
        }


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
    backend = AgentBackend()
    yield
    print("🛑 Backend service shutting down...")


app = FastAPI(
    title="Qwen Agent Backend",
    description="Stateless REST API for Qwen Agent with MCP Tools",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# Endpoints
# ============================================================================

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
    
    session_id = backend.create_session()
    return {"session_id": session_id}


@app.post("/chat/send", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """Send a message to the agent."""
    if not backend:
        raise HTTPException(status_code=503, detail="Backend not initialized")
    
    # Create session if not provided
    session_id = request.session_id or backend.create_session()
    
    session = backend.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    try:
        response, context_len, input_len = backend.send_message(session_id, request.message)
        # Re-fetch session to ensure we have latest state
        session = backend.get_session(session_id)
        total_msgs = len(session["messages"])
        print(f"📤 Returning: context={context_len}, history={total_msgs}, input={input_len} chars")
        return ChatResponse(
            session_id=session_id,
            response=response,
            timestamp=datetime.utcnow().isoformat(),
            message_count=total_msgs,
            context_length=context_len,
            total_history=total_msgs,
            input_length=input_len
        )
    except Exception as e:
        print(f"⚠ Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/history/{session_id}", response_model=HistoryResponse)
async def get_history(session_id: str):
    """Get chat history for a session."""
    if not backend:
        raise HTTPException(status_code=503, detail="Backend not initialized")
    
    session = backend.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    return HistoryResponse(
        session_id=session_id,
        messages=[ChatMessage(**msg) for msg in session["messages"]],
        created_at=session["created_at"]
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

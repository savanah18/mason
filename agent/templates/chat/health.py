from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: str
    mcp_tools_loaded: int
    sessions_active: int
    backend_version: str
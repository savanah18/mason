import redis
import uuid
from enum import StrEnum
import json

from qwen_agent.tools.base import BaseTool

# Traceability Paramaters 
TRACEABILITY_PARAMS_ADD_ONS  = [
    {
        'name': 'workflow_id',
        'type': 'string',
        'description': 'Optional workflow ID supplied by the orchestrator for attestation',
        'required': False,
    }
]


class ToolExecStatus(StrEnum):
    PENDING     = "Pending"
    RUNNING     = "Running"
    COMPLETED   = "Completed"
    FAILED      = "Failed"
    CANCELLED   = "Cancelled"

class MemoryTraceableTool(BaseTool):
    mem_client = redis.Redis(host="redis", port=6379, decode_responses=True)

    def _record_tool_state(self, exec_id, tool_name, args={}, 
        status=ToolExecStatus.PENDING,
        result=None
    ):
        self.mem_client.hset(
            f"tool_execution:{exec_id}",
            mapping={
                "execution_id": str(exec_id),
                "tool_name": tool_name,
                "args": json.dumps(args),
                "status": str(status),
                "result": json.dumps(result)
            }
        )
        self.mem_client.expire(f"tool_execution:{exec_id}", 3600)

    def _pre_call(self, tool_name, args):
        exec_id = str(uuid.uuid4())
        self._record_tool_state(exec_id, tool_name, args, ToolExecStatus.RUNNING)
        return exec_id

    def _post_call(self, exec_id, tool_name, args, status, result=None):
        self._record_tool_state(exec_id, tool_name, args, status, result)




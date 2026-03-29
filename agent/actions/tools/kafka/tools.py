"""Registered Kafka tools for Qwen Agent."""

from __future__ import annotations

import atexit
import os
from typing import Any, Dict

import json
from qwen_agent.tools.base import BaseTool, register_tool

from .kafka_client import KafkaProducerClient
from ..utils.traceability import TRACEABILITY_PARAMS_ADD_ONS, MemoryTraceableTool, ToolExecStatus

atexit.register(KafkaProducerClient.close_shared_clients)

def _parse_params(params: Any) -> Dict[str, Any]:
    if isinstance(params, dict):
        return params
    if not params:
        return {}
    if isinstance(params, str):
        parsed = json.loads(params)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _bootstrap_servers_from_args(args: Dict[str, Any]) -> str | list[str]:
    servers = args.get("bootstrap_servers")
    if servers:
        return servers
    return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-server:9092")


@register_tool("kafka-produce-message")
class KafkaProduceMessage(MemoryTraceableTool):
    """Publish a message to Kafka topic."""
    tool_name = "kafka-produce-message"

    description = (
        "Publish a message to a Kafka topic. Supports optional workdlow_id."
    )

    parameters = [
        {
            "name": "topic",
            "type": "string",
            "description": "Kafka topic name",
            "required": True,
        },
        {
            "name": "message",
            "type": "string",
            "description": "Message payload. Can be plain text or JSON string.",
            "required": True,
        },
        {
            "name": "wait_timeout_sec",
            "type": "number",
            "description": "Delivery wait timeout in seconds (default: 10)",
            "required": False,
        }
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        exec_id = None
        args = {}
        try:
            args = _parse_params(params)
            exec_id = self._pre_call(self.tool_name, args)
            
            topic = args["topic"]
            message = args["message"]
            execution_id = args.get("workflow_id")
            wait_timeout_sec = float(args.get("wait_timeout_sec", 10))
            client = KafkaProducerClient.get_shared_client(
                bootstrap_servers=_bootstrap_servers_from_args(args),
                acks="all",
            )
            metadata = client.send_message(
                topic=topic,
                message=message,
                wait_timeout_sec=wait_timeout_sec,
            )

            result = {
                "success": True,
                "message": "Kafka message published",
                "metadata": metadata,
                "exec_id": exec_id
            }

            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            result = {
                "success": False,
                "error": str(e),
                "exec_id": exec_id
            }
            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
            return json.dumps(result, ensure_ascii=False)

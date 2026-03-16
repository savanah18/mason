"""Registered Kafka tools for Qwen Agent."""

from __future__ import annotations

import atexit
import os
from typing import Any, Dict

import json5
from qwen_agent.tools.base import BaseTool, register_tool

from .kafka_client import KafkaProducerClient


atexit.register(KafkaProducerClient.close_shared_clients)


def _parse_params(params: Any) -> Dict[str, Any]:
    if isinstance(params, dict):
        return params
    if not params:
        return {}
    if isinstance(params, str):
        parsed = json5.loads(params)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _bootstrap_servers_from_args(args: Dict[str, Any]) -> str | list[str]:
    servers = args.get("bootstrap_servers")
    if servers:
        return servers
    return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-server:9092")


@register_tool("kafka-produce-message")
class KafkaProduceMessage(BaseTool):
    """Publish a message to Kafka topic."""

    description = (
        "Publish a message to a Kafka topic. Supports optional key, headers, and execution_id."
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
            "name": "key",
            "type": "string",
            "description": "Optional message key for partitioning",
            "required": False,
        },
        {
            "name": "headers",
            "type": "object",
            "description": "Optional headers map, e.g. {\"source\": \"agent\"}",
            "required": False,
        },
        {
            "name": "execution_id",
            "type": "string",
            "description": "Optional execution ID (provided in system context)",
            "required": False,
        },
        {
            "name": "wait_timeout_sec",
            "type": "number",
            "description": "Delivery wait timeout in seconds (default: 10)",
            "required": False,
        },
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            args = _parse_params(params)
            topic = args["topic"]
            message = args["message"]
            key = args.get("key")
            headers = args.get("headers")
            execution_id = args.get("execution_id")
            wait_timeout_sec = float(args.get("wait_timeout_sec", 10))

            client = KafkaProducerClient.get_shared_client(
                bootstrap_servers=_bootstrap_servers_from_args(args),
                acks="all",
            )
            metadata = client.send_message(
                topic=topic,
                message=message,
                key=key,
                headers=headers,
                wait_timeout_sec=wait_timeout_sec,
            )

            result = {
                "success": True,
                "message": "Kafka message published",
                "metadata": metadata,
            }
            
            # Echo back execution_id if provided
            if execution_id:
                result["execution_id"] = execution_id

            return json5.dumps(result, ensure_ascii=False)
        except Exception as e:
            result = {
                "success": False,
                "error": str(e),
            }
            
            # Echo back execution_id even on error
            if args.get("execution_id"):
                result["execution_id"] = args.get("execution_id")
            
            return json5.dumps(result, ensure_ascii=False)

"""Registered resource collector tool backed by PromQL queries."""

from __future__ import annotations

from typing import Any, Dict
import json
import re

import json5
from qwen_agent.tools.base import BaseTool, register_tool
from .client import PromQLClient


# Per-turn dedupe cache: execution_id -> canonical query key -> payload
_TURN_QUERY_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}


def _parse_params(params: Any) -> Dict[str, Any]:
    if isinstance(params, dict):
        return params
    if not params:
        return {}
    if isinstance(params, str):
        parsed = json5.loads(params)
        return parsed if isinstance(parsed, dict) else {}
    return {}

def _tool_response(payload: Dict[str, Any], execution_id: str | None = None) -> str:
    response = dict(payload)
    if execution_id:
        response["execution_id"] = execution_id
    return json5.dumps(response, ensure_ascii=False)


def _normalize_promql_query(query: str) -> tuple[str, bool]:
    """Normalize common LLM query formatting mistakes while preserving semantics."""
    if not isinstance(query, str):
        return query, False

    normalized = query.strip()

    # PromQL label matchers should use double quotes for string values.
    normalized = re.sub(r"(\b[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*)'([^']*)'", r'\1"\2"', normalized)

    # Repair simple missing trailing right-paren cases.
    open_parens = normalized.count("(")
    close_parens = normalized.count(")")
    if open_parens > close_parens:
        normalized += ")" * (open_parens - close_parens)

    return normalized, normalized != query


def _build_turn_query_key(args: Dict[str, Any], normalized_query: str, step: str) -> str:
    """Build deterministic dedupe key for same-turn metric calls."""
    payload = {
        "query": normalized_query,
        "prometheus_url": args.get("prometheus_url"),
        "start_time": args.get("start_time"),
        "end_time": args.get("end_time"),
        "step": step,
        "verify_ssl": bool(args.get("verify_ssl", False)),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@register_tool("resource-collector")
class ResourceCollector(BaseTool):
    """Query PromQL endpoints for resource metrics."""

    description = (
        "Run a PromQL query against Prometheus or VictoriaMetrics and return the raw result set."
    )

    parameters = [
        {
            "name": "query",
            "type": "string",
            "description": "PromQL query to execute",
            "required": True,
        },
        {
            "name": "prometheus_url",
            "type": "string",
            "description": "Optional endpoint URL. Defaults to PROMETHEUS_URL, then VM_INSTANCE_ENTRYPOINT.",
            "required": False,
        },
        {
            "name": "start_time",
            "type": "string",
            "description": "Optional ISO8601 range start time for range queries",
            "required": False,
        },
        {
            "name": "end_time",
            "type": "string",
            "description": "Optional ISO8601 range end time for range queries",
            "required": False,
        },
        {
            "name": "step",
            "type": "string",
            "description": "Range query step, e.g. 30s, 1m (default: 30s)",
            "required": False,
        },
        {
            "name": "verify_ssl",
            "type": "boolean",
            "description": "Set true to verify TLS certificates",
            "required": False,
        },
        {
            "name": "execution_id",
            "type": "string",
            "description": "Optional execution ID supplied by orchestrator",
            "required": False,
        },
    ]

    def call(self, params: str, **kwargs) -> str:
        args: Dict[str, Any] = {}
        try:
            args = _parse_params(params)
            query = args["query"]
            normalized_query, was_normalized = _normalize_promql_query(query)
            verify_ssl = bool(args.get("verify_ssl", False))
            step = str(args.get("step", "30s"))
            execution_id = args.get("execution_id")

            # Same-turn dedupe: avoid re-running identical query arguments.
            if execution_id:
                turn_cache = _TURN_QUERY_CACHE.setdefault(execution_id, {})
                query_key = _build_turn_query_key(args, normalized_query, step)
                if query_key in turn_cache:
                    cached = dict(turn_cache[query_key])
                    cached["deduped"] = True
                    return _tool_response(cached, execution_id)

            client = PromQLClient(
                endpoint=args.get("prometheus_url"),
                verify_ssl=verify_ssl,
            )

            start_time = args.get("start_time")
            end_time = args.get("end_time")
            query_type, data = client.query(
                promql=normalized_query,
                start_time=start_time,
                end_time=end_time,
                step=step,
            )

            result = {
                "success": True,
                "query_type": query_type,
                "endpoint": client.endpoint,
                "query": normalized_query,
                "result_count": len(data) if isinstance(data, list) else 0,
                "data": data,
            }
            if was_normalized:
                result["query_normalized"] = True
                result["original_query"] = query

            if execution_id:
                query_key = _build_turn_query_key(args, normalized_query, step)
                _TURN_QUERY_CACHE.setdefault(execution_id, {})[query_key] = result
            return _tool_response(result, execution_id)
        except Exception as e:
            result = {
                "success": False,
                "query": args.get("query"),
                "error": str(e),
            }
            execution_id = args.get("execution_id")
            return _tool_response(result, execution_id)

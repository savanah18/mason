"""Registered resource collector tool backed by PromQL queries."""

from __future__ import annotations

from typing import Any, Dict
import json
import re

import json5
from qwen_agent.tools.base import BaseTool, register_tool

from .client import PromQLClient
from ..utils.traceability import TRACEABILITY_PARAMS_ADD_ONS, MemoryTraceableTool, ToolExecStatus


def _parse_params(params: Any) -> Dict[str, Any]:
    if isinstance(params, dict):
        return params
    if not params:
        return {}
    if isinstance(params, str):
        parsed = json5.loads(params)
        return parsed if isinstance(parsed, dict) else {}
    return {}

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

@register_tool("resource-collector")
class ResourceCollector(MemoryTraceableTool):
    """Query PromQL endpoints for resource metrics."""
    tool_name = "resource-collector"

    description = (
        """
        Run a PromQL query against Prometheus or VictoriaMetrics and return the raw result set.
        Tool for collecting resource usage metrics(i.e. cpu, memory) to inform downstream decision-making. 
        """
    )

    parameters = [
        {
            "name": "query",
            "type": "string",
            "description": "PromQL query to execute",
            "required": True,
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
        }
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        args: Dict[str, Any] = {}
        try:
            args = _parse_params(params)
            exec_id = self._pre_call(self.tool_name, args)
            query = args["query"]
            normalized_query, was_normalized = _normalize_promql_query(query)
            step = str(args.get("step", "30s"))
            client = PromQLClient()
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
                "exec_id": exec_id
            }
            if was_normalized:
                result["query_normalized"] = True
                result["original_query"] = query

            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            result = {
                "success": False,
                "query": args.get("query"),
                "error": str(e),
                "exec_id": exec_id
            }
            execution_id = args.get("execution_id")
            return json.dumps(result, ensure_ascii=False)

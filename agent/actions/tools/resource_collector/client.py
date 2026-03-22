"""PromQL client helpers for querying Prometheus-compatible APIs."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from prometheus_api_client import PrometheusConnect


DEFAULT_PROMQL_ENDPOINT = "http://victoria-metrics:8428"


def parse_iso_datetime(raw: str) -> datetime:
    """Parse ISO-8601 timestamps and normalize trailing Z."""
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


class PromQLClient:
    """Thin wrapper around prometheus-api-client with endpoint resolution."""

    def __init__(self, endpoint: Optional[str] = None, verify_ssl: bool = False):
        self.endpoint = (
            endpoint
            or os.getenv("PROMETHEUS_URL")
            or f'{os.getenv("VM_INSTANCE_ENTRYPOINT")}/select/0/prometheus'
            or DEFAULT_PROMQL_ENDPOINT
        )
        self.verify_ssl = verify_ssl
        self._client = PrometheusConnect(url=self.endpoint, disable_ssl=not verify_ssl)

    def query(
        self,
        promql: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        step: str = "30s",
    ) -> tuple[str, Any]:
        """Run instant or range query depending on provided time bounds."""
        if (start_time and not end_time) or (end_time and not start_time):
            raise ValueError("Both start_time and end_time are required for range query")

        if start_time and end_time:
            data = self._client.custom_query_range(
                query=promql,
                start_time=parse_iso_datetime(start_time),
                end_time=parse_iso_datetime(end_time),
                step=step,
            )
            return "range", data

        data = self._client.custom_query(query=promql)
        return "instant", data

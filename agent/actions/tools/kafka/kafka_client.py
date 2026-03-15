"""Simple Kafka producer client wrapper."""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, Iterable, Optional

from kafka import KafkaProducer


class KafkaProducerClient:
    """Thin wrapper around kafka-python producer for simple message publish."""

    _shared_clients: dict[tuple[tuple[str, ...], str, int], "KafkaProducerClient"] = {}
    _shared_lock = threading.Lock()

    def __init__(
        self,
        bootstrap_servers: Iterable[str] | str,
        acks: str = "all",
        request_timeout_ms: int = 30000,
    ) -> None:
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            acks=acks,
            request_timeout_ms=request_timeout_ms,
            value_serializer=self._serialize_value,
            key_serializer=self._serialize_key,
        )

    @staticmethod
    def _normalize_bootstrap_servers(bootstrap_servers: Iterable[str] | str) -> tuple[str, ...]:
        if isinstance(bootstrap_servers, str):
            parts = [s.strip() for s in bootstrap_servers.split(",") if s.strip()]
        else:
            parts = [str(s).strip() for s in bootstrap_servers if str(s).strip()]

        if not parts:
            raise ValueError("bootstrap_servers cannot be empty")

        return tuple(parts)

    @classmethod
    def get_shared_client(
        cls,
        bootstrap_servers: Iterable[str] | str,
        acks: str = "all",
        request_timeout_ms: int = 30000,
    ) -> "KafkaProducerClient":
        normalized_servers = cls._normalize_bootstrap_servers(bootstrap_servers)
        cache_key = (normalized_servers, acks, request_timeout_ms)

        with cls._shared_lock:
            client = cls._shared_clients.get(cache_key)
            if client is None:
                client = cls(
                    bootstrap_servers=list(normalized_servers),
                    acks=acks,
                    request_timeout_ms=request_timeout_ms,
                )
                cls._shared_clients[cache_key] = client
            return client

    @classmethod
    def close_shared_clients(cls) -> None:
        with cls._shared_lock:
            clients = list(cls._shared_clients.values())
            cls._shared_clients.clear()

        for client in clients:
            try:
                client.close()
            except Exception:
                pass

    @staticmethod
    def _serialize_value(value: Any) -> bytes:
        if isinstance(value, (dict, list)):
            return json.dumps(value).encode("utf-8")
        return str(value).encode("utf-8")

    @staticmethod
    def _serialize_key(value: Optional[str]) -> Optional[bytes]:
        if value is None:
            return None
        return str(value).encode("utf-8")

    def send_message(
        self,
        topic: str,
        message: Any,
        key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        wait_timeout_sec: float = 10.0,
    ) -> Dict[str, Any]:
        kafka_headers = None
        if headers:
            kafka_headers = [
                (str(k), str(v).encode("utf-8"))
                for k, v in headers.items()
            ]

        future = self.producer.send(
            topic=topic,
            key=key,
            value=message,
            headers=kafka_headers,
        )

        metadata = future.get(timeout=wait_timeout_sec)
        self.producer.flush(timeout=wait_timeout_sec)

        return {
            "topic": metadata.topic,
            "partition": metadata.partition,
            "offset": metadata.offset,
            "timestamp": getattr(metadata, "timestamp", None),
        }

    def close(self) -> None:
        try:
            self.producer.flush(timeout=5)
        finally:
            self.producer.close(timeout=5)

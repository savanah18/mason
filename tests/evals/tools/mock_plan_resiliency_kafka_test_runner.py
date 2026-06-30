#!/usr/bin/env python3
"""Send resiliency mock-plan request as Kafka event for tests.

Reads CHAT_PROMPT and WORKFLOW_ID from environment, infers release and namespace
from prompt text, and publishes JSON to topic tests.normal on 127.0.0.1:9092.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Optional, Tuple

from kafka import KafkaProducer


def infer_release_and_namespace(chat_prompt: str) -> Tuple[Optional[str], Optional[str]]:
    lowered = chat_prompt.lower()

    release = None
    namespace = None

    release_patterns = [
        r"release\s+`([^`]+)`",
        r"release\s+([a-z0-9][a-z0-9-]{1,})",
        r"for\s+([a-z0-9][a-z0-9-]{1,})\s+in\s+([a-z0-9][a-z0-9-]{1,})\s+namespace",
    ]
    namespace_patterns = [
        r"namespace\s+`([^`]+)`",
        r"namespace\s+([a-z0-9][a-z0-9-]{1,})",
    ]

    for p in release_patterns:
        m = re.search(p, lowered)
        if m:
            release = m.group(1)
            if m.lastindex and m.lastindex >= 2 and not namespace:
                namespace = m.group(2)
            break

    for p in namespace_patterns:
        m = re.search(p, lowered)
        if m:
            namespace = m.group(1)
            break

    return release, namespace


def main() -> int:
    chat_prompt = os.getenv("CHAT_PROMPT", "").strip()
    workflow_id = os.getenv("WORKFLOW_ID", "").strip()
    topic = os.getenv("RESILIENCY_MOCK_TOPIC", "tests.normal")

    if not chat_prompt:
        print("ERROR: CHAT_PROMPT is empty")
        return 1
    if not workflow_id:
        print("ERROR: WORKFLOW_ID is empty")
        return 1

    release_name, namespace = infer_release_and_namespace(chat_prompt)

    payload = {
        "workflow_id": workflow_id,
        "release_name": release_name,
        "namespace": namespace,
        "extra_instruction": chat_prompt,
    }

    producer = KafkaProducer(
        bootstrap_servers=["127.0.0.1:9092"],
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    try:
        future = producer.send(topic, payload)
        record_metadata = future.get(timeout=10)
        producer.flush()
    finally:
        producer.close()

    print(
        json.dumps(
            {
                "success": True,
                "topic": topic,
                "partition": record_metadata.partition,
                "offset": record_metadata.offset,
                "workflow_id": workflow_id,
                "release_name": release_name,
                "namespace": namespace,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

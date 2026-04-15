#!/usr/bin/env python3
"""Send mock-plan deployment request as Kafka event for deployer agent tests.

Reads CHAT_PROMPT and WORKFLOW_ID from environment, infers package name from the
prompt text, then publishes JSON to topic package.<package-name> on 127.0.0.1:9092.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Optional

from kafka import KafkaProducer


def infer_package_name(chat_prompt: str) -> Optional[str]:
    """Infer release/package name from chat prompt text.

    Supports patterns like:
    - release `fraud-detector`
    - deploy fraud-detector
    - process ... for media-api
    """
    patterns = [
        r"release\s+`([^`]+)`",
        r"release\s+([a-z0-9][a-z0-9-]{1,})",
        r"deploy\s+([a-z0-9][a-z0-9-]{1,})",
        r"for\s+([a-z0-9][a-z0-9-]{1,})\s+in\s+namespace",
    ]
    lowered = chat_prompt.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    return None


def main() -> int:
    chat_prompt = os.getenv("CHAT_PROMPT", "").strip()
    workflow_id = os.getenv("WORKFLOW_ID", "").strip()

    if not chat_prompt:
        print("ERROR: CHAT_PROMPT is empty")
        return 1
    if not workflow_id:
        print("ERROR: WORKFLOW_ID is empty")
        return 1

    package_name = infer_package_name(chat_prompt)
    if not package_name:
        print("ERROR: Unable to infer package-name from CHAT_PROMPT")
        return 1

    topic = f"package.{package_name}"

    payload = {
        "workflow_id": workflow_id,
        "extra-instruction": chat_prompt,
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
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

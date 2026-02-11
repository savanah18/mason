import os

class MiddleWareEnv:
    PRETRAINED_MODEL_CONFIG_PATH: str = os.getenv("PRETRAINED_MODEL_CONFIG_PATH", "/models/qwen3-tensorrtllm/configs")
    GRPC_SERVER_URL: str = os.getenv("GRPC_SERVER_URL", "localhost:8001")


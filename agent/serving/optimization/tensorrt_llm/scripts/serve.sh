#!/bin/bash
TRTLLM_DIR=/app/tensorrt_llm # change as needed to match your environment
EXTRA_LLM_API_FILE=${TRTLLM_DIR}/examples/configs/curated/qwen3.yaml

trtllm-serve serve  \
    --backend tensorrt \
    --max_batch_size 1 \
    --tokenizer /app/tensorrt_llm/tokenizer/  \
    --port 8000 \
    --host 0.0.0.0 \
    /app/tensorrt_llm/models/qwen3/1/
    # --tokenizer /app/tensorrt_llm/models/qwen3/1/tokenizer/tokenizer.json  \
    # /app/tensorrt_llm/models/qwen3-tensorrtllm/1/rank0.engine  
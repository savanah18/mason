#!/bin/bash
TRTLLM_DIR=/app/tensorrt_llm # change as needed to match your environment
EXTRA_LLM_API_FILE=${TRTLLM_DIR}/examples/configs/curated/qwen3.yaml

trtllm-serve serve  \
    --backend tensorrt \
    --max_batch_size ${MAX_BATCH_SIZE:-1} \
    --max_seq_len ${MAX_SEQ_LEN:-32768} \
    --max_num_tokens ${MAX_NUM_TOKENS:-32768} \
    --tokenizer /app/tensorrt_llm/tokenizer/  \
    --port 8000 \
    --host 0.0.0.0 \
    --enable_chunked_prefill \
    /app/tensorrt_llm/models/qwen3/2/
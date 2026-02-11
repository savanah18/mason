#!/bin/bash

set -x

echo "Converting model checkpoint to TensorRT LLM format..."
python3 /app/tensorrt_llm/examples/models/core/qwen/convert_checkpoint.py \
    --model_dir $MODEL_PATH \
    --output_dir ${TENSORRT_LLM_CKPT} \
    --dtype ${DTYPE} \
    --load_model_on_cpu \
    # --use_weight_only \
    # --weight_only_precision ${QUANTIZATION_TYPE}


echo "Converting model checkpoint to TensorRT Engines..."
trtllm-build --checkpoint_dir ${TENSORRT_LLM_CKPT}\
        --gpt_attention_plugin ${DTYPE}  \
        --gemm_plugin ${DTYPE}  \
        --remove_input_padding enable \
        --use_paged_context_fmha enable \
        --paged_kv_cache true \
        --kv_cache_type paged \
        --max_batch_size 4 \
        --max_input_len 8192 \
        --max_seq_len 16384 \
        --opt_num_tokens 4096 \
        --max_num_tokens 8192 \
        --output_dir ${TENSORRT_ENGINE_PATH} \

echo "Creating xgrammar tokenizer info..."
python3 /app/tensorrt_llm/examples/generate_xgrammar_tokenizer_info.py \
    --model_dir ${MODEL_PATH} \
    --output_dir ${TENSORRT_ENGINE_PATH}/tokenizer

set +x


# Ref: https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/tensorrtllm_backend/docs/guided_decoding.html
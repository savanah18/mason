#!/bin/bash

set -x

# [TODO] Skip conversion if TensorRT Engine already exists unless overwrite flag is set
echo "Converting model checkpoint to TensorRT LLM format..."
python3 /app/tensorrt_llm/examples/models/core/qwen/convert_checkpoint.py \
    --model_dir $MODEL_PATH \
    --output_dir ${TENSORRT_LLM_CKPT} \
    --dtype ${DTYPE} \
    --load_model_on_cpu \
    # --use_weight_only \
    # --weight_only_precision ${QUANTIZATION_TYPE}

# Override default seq len and token limits
jq --argjson seq_length "$MAX_SEQ_LEN" \
   --argjson max_input_len "$MAX_INPUT_LEN" \
   --argjson max_num_tokens "$MAX_NUM_TOKENS" \
   '.seq_length = $seq_length | .max_input_len = $max_input_len | .max_num_tokens = $max_num_tokens' \
    ${TENSORRT_LLM_CKPT}/config.json > ${TENSORRT_LLM_CKPT}/config_tmp.json && \
    mv ${TENSORRT_LLM_CKPT}/config_tmp.json ${TENSORRT_LLM_CKPT}/config.json


echo "Converting model checkpoint to TensorRT Engines..."
trtllm-build --checkpoint_dir ${TENSORRT_LLM_CKPT}\
        --gpt_attention_plugin ${DTYPE}  \
        --gemm_plugin ${DTYPE}  \
        --remove_input_padding enable \
        --use_paged_context_fmha enable \
        --kv_cache_type paged \
        --max_batch_size ${MAX_BATCH_SIZE} \
        --max_input_len ${MAX_INPUT_LEN} \
        --max_seq_len ${MAX_SEQ_LEN} \
        --opt_num_tokens ${OPT_NUM_TOKENS} \
        --max_num_tokens ${MAX_NUM_TOKENS} \
        --output_dir ${TENSORRT_ENGINE_PATH} \

echo "Creating xgrammar tokenizer info..."
python3 /app/tensorrt_llm/examples/generate_xgrammar_tokenizer_info.py \
    --model_dir ${MODEL_PATH} \
    --output_dir ${TENSORRT_ENGINE_PATH}/tokenizer

echo "Copying generation config file..."
cp ${MODEL_PATH}/generation_config.json ${TENSORRT_ENGINE_PATH}/tokenizer/generation_config.json

set +x


# Ref: https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/tensorrtllm_backend/docs/guided_decoding.html
#!bin/bash

python3 /app/tensorrt_llm/examples/models/core/qwen/convert_checkpoint.py \
    --model_dir $MODEL_PATH \
    --output_dir ${TENSORRT_LLM_CKPT} \
    --dtype ${DTYPE} \
    --load_model_on_cpu \
    --use_weight_only \
    --weight_only_precision ${QUANTIZATION_TYPE}


trtllm-build --checkpoint_dir ${TENSORRT_LLM_CKPT}\
        --gpt_attention_plugin ${DTYPE}  \
        --remove_input_padding enable \
        --kv_cache_type paged \
        --gemm_plugin ${DTYPE}  \
        --output_dir ${TENSORRT_ENGINE_PATH}

python3 /app/tensorrt_llm/examples/generate_xgrammar_tokenizer_info.py \
    --model_dir ${MODEL_PATH} \
    --output_dir ${TENSORRT_ENGINE_PATH}




# Ref: https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/tensorrtllm_backend/docs/guided_decoding.html
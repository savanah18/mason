# Qwen2.5-7B TensorRT-LLM Model for Triton

This directory contains the TensorRT-LLM optimized Qwen2.5-7B-Instruct model for Triton Inference Server.

## Setup

### 1. Build TensorRT-LLM Engine

```bash
cd ../../../../optimization/tensorrt_llm

# Build INT4 engine (recommended)
./build_qwen.sh int4 ./outputs/qwen-int4

# Or FP16 for maximum performance
./build_qwen.sh float16 ./outputs/qwen-fp16
```

### 2. Copy Engine Files

```bash
# Copy engine artifacts to this directory
cp -r ../../../../optimization/tensorrt_llm/outputs/qwen-int4/engines/* ./1/
```

### 3. Verify Structure

Your directory should look like:
```
qwen2.5-tensorrtllm/
├── config.pbtxt            # Triton model config (already present)
└── 1/                       # Model version
    ├── config.json         # TensorRT-LLM config
    └── rank0.engine        # TensorRT engine file
```

For multi-GPU (tensor parallelism):
```
1/
├── config.json
├── rank0.engine
├── rank1.engine
...
```

## Usage

### Start Triton Server

```bash
# From docker-compose
docker-compose up triton-server

# Or standalone
tritonserver --model-repository=/path/to/models
```

### Test Inference

**gRPC Client:**
```python
import tritonclient.grpc as grpcclient
import numpy as np

client = grpcclient.InferenceServerClient("localhost:8001")

text_input = np.array([["What is the capital of France?"]], dtype=object)
inputs = [grpcclient.InferInput("text_input", text_input.shape, "BYTES")]
inputs[0].set_data_from_numpy(text_input)

outputs = [grpcclient.InferRequestedOutput("text_output")]
response = client.infer("qwen2.5-tensorrtllm", inputs, outputs=outputs)

result = response.as_numpy("text_output")
print(result[0][0].decode('utf-8'))
```

**HTTP Client:**
```bash
curl -X POST http://localhost:8000/v2/models/qwen2.5-tensorrtllm/infer \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": [
      {
        "name": "text_input",
        "shape": [1, 1],
        "datatype": "BYTES",
        "data": ["What is the capital of France?"]
      }
    ]
  }'
```

## Configuration

Edit [config.pbtxt](config.pbtxt) to adjust:

- `max_batch_size`: Maximum concurrent requests (default: 8)
- `max_num_sequences`: Maximum sequences in flight
- `kv_cache_free_gpu_mem_fraction`: GPU memory for KV cache (default: 0.9)

## Performance

Expected performance on single GPU:

| Precision | Memory | Latency | Throughput |
|-----------|--------|---------|------------|
| FP16 | 15GB | 5-10s | 50-100 tok/s |
| INT4 | 6GB | 8-15s | 30-60 tok/s |
| INT8 | 8GB | 6-12s | 40-80 tok/s |

## Troubleshooting

### Model Not Loading

Check Triton logs:
```bash
docker logs triton-server 2>&1 | grep -A 10 "qwen2.5-tensorrtllm"
```

### Engine Files Missing

Verify engine files exist:
```bash
ls -lh 1/
# Should show: config.json, rank0.engine
```

### Low Performance

- Enable paged KV cache (default in build script)
- Increase `max_num_sequences` in config
- Use INT4 quantization for memory-bound workloads
- Monitor GPU utilization: `nvidia-smi dmon`

## Resources

- Build Guide: [../../../../optimization/tensorrt_llm/README.md](../../../../optimization/tensorrt_llm/README.md)
- TensorRT-LLM: https://github.com/NVIDIA/TensorRT-LLM
- Triton Backend: https://github.com/triton-inference-server/tensorrtllm_backend

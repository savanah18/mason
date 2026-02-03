# Triton Performance Analysis & Optimization

## Current Issue
Inference is taking ~100s on RTX 5060 Ti, which is extremely slow.

## Root Causes

### 1. **Python Backend Overhead** ✓
- Python backend adds 10-30% overhead vs C++ backend
- However, this shouldn't cause 100s delay

### 2. **Generation Parameters** ⚠️ MAJOR ISSUE
- `max_new_tokens=512` - Model tries to generate up to 512 tokens
- At ~2-5 tokens/sec with int4 quantization, this means 100-250s worst case
- **Solution**: Reduce to 128 or 256 tokens for faster responses

### 3. **Conversation History Accumulation**
- Each message adds to history, increasing context length
- Longer context = slower inference
- `max_history=5` limits this but still accumulates

### 4. **First Request Overhead**
- CUDA kernel compilation on first run
- Model warmup
- Can take 20-30s extra on first inference

## Performance Optimization Steps

### Immediate Fixes (Apply Now)

1. **Reduce max_new_tokens**:
   ```bash
   # In docker-compose.yml or .env
   MAX_NEW_TOKENS=128  # Down from 512
   ```

2. **Add early stopping**:
   ```python
   # In model.py generate() call, add:
   eos_token_id=self.processor.tokenizer.eos_token_id
   ```

3. **Clear conversation history more aggressively**:
   ```python
   MAX_HISTORY=2  # Down from 5
   ```

### Medium-term Optimizations

4. **Use Flash Attention 2**:
   ```python
   attn_implementation="flash_attention_2"  # Currently using "sdpa"
   ```
   Requires: `pip install flash-attn`

5. **Enable KV Cache Optimization**:
   ```python
   # In generate() call
   use_cache=True,
   cache_implementation="static"
   ```

6. **Reduce Precision**:
   - Currently using int4 (good)
   - Could try bfloat16 for larger VRAM but faster inference

### Advanced Optimizations

7. **Switch to vLLM Backend**:
   - Replace Python backend with vLLM backend
   - 2-10x faster inference
   - Supports continuous batching
   - Requires Triton + vLLM integration

8. **Enable Tensor Parallelism**:
   - If you have multiple GPUs
   - Split model across GPUs

9. **Use TensorRT-LLM**:
   - Compile model to TensorRT
   - 3-5x faster than Python backend
   - Requires model conversion

## Current Logging

Added performance logging to identify bottlenecks:
- Tokenization time
- Generation time
- Tokens/second throughput
- Input/output token counts

Check Triton logs:
```bash
docker compose logs triton-server | grep "\[Triton\]"
```

## Expected Performance After Fixes

| Configuration | Expected Time | Throughput |
|--------------|---------------|------------|
| Current (512 tokens) | 100-150s | 3-5 tok/s |
| Optimized (128 tokens) | 25-40s | 3-5 tok/s |
| With Flash Attention | 15-25s | 5-8 tok/s |
| With vLLM | 5-10s | 10-20 tok/s |
| With TensorRT | 3-5s | 20-40 tok/s |

## Quick Test

After reducing max_new_tokens, test with:
```bash
python agent/client/triton_client.py --grpc
```

Monitor logs for:
```
[Triton] Generation: X.XXs | Output tokens: YYY | Speed: Z.Z tok/s
```

## Recommended Configuration

```yaml
# docker-compose.yml or .env
MAX_NEW_TOKENS=128  # Faster responses
MAX_HISTORY=2       # Less context accumulation
ATTENTION_IMPL=flash_attention_2  # If available
TEMPERATURE=0.7
TOP_P=0.9
```

## VS Code Extension Updates

✅ **Completed**:
- Added loading indicator (⏳ Processing...)
- Shows user message immediately
- Displays both model time and total time
- Disables input while processing
- Console logging for debugging

To view logs:
```
Developer: Open Webview Developer Tools
```
Or check Extension Host output.

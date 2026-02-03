# Feature Development Checklist

## Phase 1: Foundation & Data Structures ✅

### Feature 1.1: Goal Definition Schema ✅
**File:** `src/models/goal.rs`  
**Status:** Complete  
**What it does:** Defines goals with status, lifecycle, validation  
**Test:** `cargo test models::goal`

### Feature 1.2: Goal Storage Layer ✅
**File:** `src/storage/goal_repository.rs`  
**Status:** Basic implementation complete  
**What it does:** Save/load goals from JSON files  
**Next:** Add list_active(), pagination, database migration  
**Test:** Create a goal, save it, load it back

### Feature 1.3: Task Execution State Tracker ✅
**File:** `src/models/execution_state.rs`  
**Status:** Complete  
**What it does:** Track iterations, tool calls, observations  
**Test:** `cargo test models::execution_state`

### Feature 1.4: Tool Schema Registry ⚠️
**File:** `src/execution/tool_registry.rs`  
**Status:** Stub only  
**TODO:**
1. Implement MCP protocol `tools/list` call
2. Parse tool schemas from JSON response
3. Cache in HashMap<String, ToolSchema>
4. Add refresh mechanism
**Dependencies:** MCP server running on port 8080  
**Test:** Call `discover_tools()` and verify 22 tools loaded

---

## Phase 2: LLM Integration & Decision Making

### Feature 2.1: System Prompt Generator ⚠️
**File:** `src/llm/prompt_builder.rs`  
**Status:** Stub only  
**TODO:**
1. Create template with goal, tools, context, history
2. Format tool schemas in natural language
3. Add examples (few-shot prompting)
4. Include success criteria
**Example prompt:**
```
You are an autonomous Kubernetes agent.
Goal: {goal}
Available tools: pods_list, pods_delete, ...
Current cluster state: {context}
Think step-by-step...
```
**Test:** Build prompt for sample goal and verify completeness

### Feature 2.2: Tool Call Parser ⚠️
**File:** `src/llm/tool_call_parser.rs`  
**Status:** Stub only  
**TODO:**
1. Parse `TOOL: tool_name(param=value, ...)` format
2. Parse JSON `{"tool": "...", "params": {...}}` format
3. Extract multiple tool calls from output
4. Validate parameter types
**Test:** Parse sample LLM outputs with tool calls

### Feature 2.3: Decision Engine ⚠️
**File:** `src/llm/decision_engine.rs`  
**Status:** Stub only  
**TODO:**
1. HTTP POST to `{triton_url}/v2/models/qwen3-vl/infer`
2. Build Triton inference request payload
3. Parse response to extract generated text
4. Use ToolCallParser to extract tool calls
5. Determine if goal is complete
**Dependencies:** Triton server running, Qwen model loaded  
**Test:** Send sample prompt, verify decision returned

### Feature 2.4: Context Retriever ⚠️
**File:** `src/llm/context_retriever.rs`  
**Status:** Stub only  
**TODO:**
1. HTTP POST to `{qdrant_url}/collections/knowledge_base/points/search`
2. Convert goal description to embedding (via Triton)
3. Retrieve top-k similar resource chunks
4. Format as concise text summary
**Dependencies:** Qdrant running with indexed resources  
**Test:** Search for "failed pods", verify relevant chunks returned

---

## Phase 3: Tool Execution & Observation

### Feature 3.1: MCP Tool Executor ⚠️
**File:** `src/execution/tool_executor.rs`  
**Status:** Stub only  
**TODO:**
1. Build JSON-RPC request: `{"method": "tools/call", "params": {...}}`
2. HTTP POST to `{mcp_url}/mcp` with session header
3. Parse SSE response format: `data: {...}`
4. Extract result or error
5. Add timeout (10s default)
6. Add retry with exponential backoff
**Test:** Execute `pods_list(namespace="default")` and verify output

### Feature 3.2: Result Validator ⚠️
**File:** `src/execution/result_validator.rs`  
**Status:** Stub only  
**TODO:**
1. Check if result.success is false
2. Detect empty results (no data returned)
3. Identify error types: timeout, not_found, permission_denied
4. Suggest recovery: retry, skip, use alternative tool
**Test:** Validate successful and failed tool results

### Feature 3.3: Observation Storage ⚠️
**File:** `src/storage/observation_store.rs`  
**Status:** Stub only  
**TODO:**
1. Convert tool result to text: "Tool X succeeded: output"
2. Get embedding via Triton `/embed` endpoint
3. Upsert to Qdrant with payload: {goal_id, iteration, tool_name, result}
4. Use deterministic ID: `{goal_id}_{iteration}_{tool_name}`
**Dependencies:** Qdrant collection exists  
**Test:** Store observation, query it back via context retriever

---

## Phase 4: Agent Loop & Orchestration

### Feature 4.1: Core Agent Loop ✅
**File:** `src/core/autonomous_agent.rs`  
**Status:** Framework complete, needs integration  
**TODO:**
1. Replace stub calls in `perceive()` with real ContextRetriever
2. Replace stub calls in `plan()` with real DecisionEngine
3. Replace stub calls in `act()` with real ToolExecutor
4. Test full loop with mock goal
**Test:** Execute goal "List pods" and verify it completes

### Feature 4.2: Goal Completion Detector ⚠️
**File:** `src/core/autonomous_agent.rs` (new method)  
**Status:** Not started  
**TODO:**
1. Ask LLM: "Is the goal complete based on these results?"
2. Parse yes/no + reasoning
3. Add heuristic checks (e.g., tool calls returned expected data)
4. Return confidence score (0-100)
**Test:** Check completion for various goal states

### Feature 4.3: Error Recovery Manager ⚠️
**File:** `src/utils/error_recovery.rs`  
**Status:** Basic stub  
**TODO:**
1. Implement backoff retry logic
2. Try alternative tools (e.g., if pods_list fails, try resources_list)
3. Request clarification from LLM on ambiguous errors
4. Log all recovery attempts
**Test:** Simulate tool failure, verify retry with backoff

---

## Phase 5: API & Safety

### Feature 5.1: Goal Management REST API ⚠️
**File:** New file `src/api/mod.rs`  
**Status:** Not started  
**TODO:**
1. Add Actix-web or Axum dependency
2. Create endpoints:
   - `POST /goals` - Create goal
   - `GET /goals/{id}` - Get status
   - `GET /goals/{id}/trace` - Execution history
   - `DELETE /goals/{id}` - Cancel goal
   - `GET /goals` - List all goals
3. Add authentication (optional)
**Test:** cURL commands to create and query goals

### Feature 5.2: Audit Logging System ⚠️
**File:** `src/utils/audit_logger.rs`  
**Status:** Not started  
**TODO:**
1. Log to `logs/agent_audit_{date}.jsonl`
2. Record: timestamp, goal_id, action_type, tool_name, params, result
3. Add rotation (daily, max size)
4. Optional: Send to external log aggregator
**Test:** Execute goal, verify audit log contains all actions

### Feature 5.3: Dry-Run Mode ✅
**File:** `src/execution/tool_executor.rs`  
**Status:** Basic implementation complete  
**TODO:**
1. Enhance mock responses based on tool schemas
2. Simulate realistic delays
3. Add flag to show what would be executed
**Test:** Run goal with dry_run=true, verify no real changes

---

## Development Priority

### Week 1: Enable Basic Autonomous Execution
- [ ] Feature 1.4: Tool Registry (discover 22 MCP tools)
- [ ] Feature 3.1: MCP Tool Executor (execute tools)
- [ ] Feature 2.1: System Prompt Generator (basic template)

### Week 2: Add Intelligence
- [ ] Feature 2.3: Decision Engine (Triton integration)
- [ ] Feature 2.2: Tool Call Parser (extract from LLM output)
- [ ] Feature 4.1: Integrate all components

### Week 3: Add Context & Memory
- [ ] Feature 2.4: Context Retriever (Qdrant RAG)
- [ ] Feature 3.3: Observation Storage (save results)
- [ ] Feature 4.2: Goal Completion Detector

### Week 4: Production Readiness
- [ ] Feature 4.3: Error Recovery
- [ ] Feature 5.1: REST API
- [ ] Feature 5.2: Audit Logging
- [ ] End-to-end testing

---

## Quick Start for Developers

1. **Pick a feature** from above (start with Week 1 priorities)
2. **Open the file** listed for that feature
3. **Find the TODO comment** in the code
4. **Implement** the functionality
5. **Add tests** at the bottom of the file
6. **Run tests**: `cargo test`
7. **Commit** with message: "Implement Feature X.Y: [name]"

## Testing Each Feature

```bash
# Test specific module
cargo test models::goal
cargo test execution::tool_executor

# Test everything
cargo test

# Run with output
cargo test -- --nocapture

# Run example agent
cargo run --bin autonomous-agent
```

## Dependencies by Feature

| Feature | Requires |
|---------|----------|
| 1.4 | MCP server @ localhost:8080 |
| 2.3 | Triton @ localhost:8000 |
| 2.4 | Qdrant @ localhost:6333 with knowledge_base collection |
| 3.1 | MCP server @ localhost:8080 |
| 3.3 | Qdrant @ localhost:6333 |

Start services:
```bash
# In separate terminals
docker-compose up qdrant
docker-compose up triton
docker-compose up mcp-server
```

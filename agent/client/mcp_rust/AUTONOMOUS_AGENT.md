# MCP Autonomous Agent - Modular Architecture

A modular, goal-driven autonomous agent system built in Rust for Kubernetes management via MCP (Model Context Protocol).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    AUTONOMOUS AGENT                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Core Agent Loop: Perceive → Plan → Act → Observe   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
          │         │         │         │         │
    ┌─────┴──┐ ┌───┴───┐ ┌───┴───┐ ┌───┴────┐ ┌─┴─────┐
    │ Models │ │  LLM  │ │  Exec │ │Storage │ │ Utils │
    └────────┘ └───────┘ └───────┘ └────────┘ └───────┘
```

## Module Structure

### 📦 `/src/models/` - Data Models (Phase 1)
Core data structures that can be developed independently:

- **`goal.rs`** - Goal definition with lifecycle management
  - `Goal`, `GoalStatus` enums
  - Lifecycle methods: `start()`, `complete()`, `fail()`
  - ✅ **Status:** Complete, tested

- **`execution_state.rs`** - Tracks execution progress
  - `ExecutionState` - overall state tracker
  - `Iteration` - per-iteration state
  - Metrics: tool calls, success rate, duration
  - ✅ **Status:** Complete, tested

- **`tool_call.rs`** - Tool invocation & results
  - `ToolCall` - structured tool invocation
  - `ToolResult` - execution results
  - `ToolSchema` - tool definitions with validation
  - ✅ **Status:** Complete, tested

- **`feedback.rs`** - Observations from environment
  - `Feedback` types: tool results, errors, LLM decisions
  - Severity tracking
  - ✅ **Status:** Complete

### 🧠 `/src/llm/` - LLM Integration (Phase 2)
Components for LLM-based decision making:

- **`decision_engine.rs`** - LLM inference wrapper
  - Calls Triton for text generation
  - Extracts decisions from LLM output
  - ⚠️ **Status:** Stub only - **TODO:** Implement Triton HTTP calls

- **`prompt_builder.rs`** - System prompt generation
  - Injects goal, tools, context, history
  - Template-based prompts
  - ⚠️ **Status:** Stub only - **TODO:** Implement prompt engineering

- **`context_retriever.rs`** - RAG from Qdrant
  - Semantic search for cluster state
  - Top-k context retrieval
  - ⚠️ **Status:** Stub only - **TODO:** Implement Qdrant API calls

- **`tool_call_parser.rs`** - Extract tool calls from LLM
  - Parse structured output: `TOOL: name(params)` or JSON
  - Validate against schemas
  - ⚠️ **Status:** Stub only - **TODO:** Implement parsing logic

### ⚙️ `/src/execution/` - Tool Execution (Phase 3)
Tool discovery and execution:

- **`tool_registry.rs`** - MCP tool discovery
  - Discover 22 K8s tools from MCP server
  - Cache schemas with validation
  - ⚠️ **Status:** Stub only - **TODO:** Implement MCP protocol

- **`tool_executor.rs`** - Execute MCP tools
  - HTTP/SSE calls to MCP server
  - Dry-run mode support
  - Error handling & timeouts
  - ⚠️ **Status:** Stub only - **TODO:** Implement MCP tool/call

- **`result_validator.rs`** - Validate tool results
  - Detect failures, empty results
  - Suggest retry strategies
  - ⚠️ **Status:** Stub only - **TODO:** Implement validation logic

### 💾 `/src/storage/` - Persistence (Phase 3)
Storage for goals and observations:

- **`goal_repository.rs`** - Goal CRUD operations
  - JSON file storage (migrate to DB later)
  - List, get, save, delete goals
  - ✅ **Status:** Basic implementation complete

- **`observation_store.rs`** - Store observations in Qdrant
  - Tool results as vectors
  - Audit trail for debugging
  - ⚠️ **Status:** Stub only - **TODO:** Implement Qdrant storage

### 🎯 `/src/core/` - Agent Loop (Phase 4)
Main orchestration logic:

- **`autonomous_agent.rs`** - Core agent loop
  - Perceive-Plan-Act-Observe cycle
  - Goal lifecycle management
  - Iteration control & error handling
  - ✅ **Status:** Framework complete, needs component integration

- **`agent_config.rs`** - Configuration management
  - Environment variable loading
  - JSON config file support
  - ✅ **Status:** Complete

### 🛠️ `/src/utils/` - Utilities
Helper functions:

- **`logger.rs`** - Logging utility
- **`error_recovery.rs`** - Error recovery strategies

## Development Roadmap

### ✅ Phase 1: Foundation (Complete)
- [x] Goal data model
- [x] Execution state tracking
- [x] Tool call/result structures
- [x] Agent configuration
- [x] Basic repository pattern

### 🚧 Phase 2: LLM Integration (In Progress)
- [ ] Feature 2.1: System prompt generation
- [ ] Feature 2.2: Tool call parser
- [ ] Feature 2.3: Decision engine with Triton
- [ ] Feature 2.4: Context retrieval from Qdrant

### 📋 Phase 3: Tool Execution (Planned)
- [ ] Feature 3.1: MCP tool executor
- [ ] Feature 3.2: Result validator
- [ ] Feature 3.3: Observation storage in Qdrant
- [ ] Feature 1.4: Tool registry with MCP discovery

### 📋 Phase 4: Agent Loop (Planned)
- [ ] Feature 4.1: Integrate all components in main loop
- [ ] Feature 4.2: Goal completion detector
- [ ] Feature 4.3: Error recovery manager

### 📋 Phase 5: API & Safety (Planned)
- [ ] Feature 5.1: REST API for goal management
- [ ] Feature 5.2: Audit logging
- [ ] Feature 5.3: Comprehensive dry-run mode

## Building & Running

### Build the project
```bash
cd /root/workspace/lnd/aiops/apps/newbie-app/agent/client/mcp
cargo build
```

### Run the autonomous agent (example)
```bash
cargo run --bin autonomous-agent
```

### Run the original tool discovery
```bash
cargo run --bin mcp-tool-discovery
```

### Run tests
```bash
cargo test
```

## Configuration

Configure via environment variables:

```bash
export MCP_BASE_URL=http://localhost:8080
export TRITON_URL=http://localhost:8000
export QDRANT_URL=http://localhost:6333
export DEFAULT_MAX_ITERATIONS=10
export DEFAULT_TIMEOUT=300
export VERBOSE=true
export DEFAULT_DRY_RUN=true  # Safe mode by default
```

Or use a config file:

```json
{
  "mcp_base_url": "http://localhost:8080",
  "triton_url": "http://localhost:8000",
  "qdrant_url": "http://localhost:6333",
  "default_max_iterations": 10,
  "default_timeout_seconds": 300,
  "verbose": true,
  "default_dry_run": true
}
```

## Usage Example

```rust
use mcp_agent::{AutonomousAgent, AgentConfig, Goal};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize agent
    let config = AgentConfig::from_env();
    let mut agent = AutonomousAgent::new(config).await?;
    
    // Create a goal
    let goal = Goal::with_config(
        "Restart all failed pods in production namespace",
        10,    // max iterations
        300,   // timeout seconds
        false  // dry_run
    );
    
    // Execute autonomously
    let result = agent.execute_goal(goal).await?;
    
    println!("Goal status: {:?}", result.status);
    Ok(())
}
```

## Feature Development Guide

Each feature can be developed independently:

1. **Pick a feature** from the roadmap
2. **Navigate to the module** (e.g., `src/llm/decision_engine.rs`)
3. **Replace the TODO stub** with real implementation
4. **Add tests** in the same file
5. **Test in isolation** before integrating

### Example: Implementing Feature 2.2 (Tool Call Parser)

1. Open `src/llm/tool_call_parser.rs`
2. Implement the `parse()` method to extract tool calls from LLM output
3. Add regex or JSON parsing logic
4. Test with sample LLM outputs
5. No other modules need to change!

## Testing Strategy

- **Unit tests**: In each module file (`#[cfg(test)]`)
- **Integration tests**: In `/tests` directory (coming soon)
- **End-to-end test**: With mock goal execution

## Dependencies

- **tokio**: Async runtime
- **serde/serde_json**: Serialization
- **reqwest**: HTTP client for MCP/Triton/Qdrant
- **anyhow**: Error handling
- **uuid**: Goal ID generation
- **chrono**: Timestamps
- **colored**: Terminal output

## Architecture Benefits

✅ **Modular**: Each module can be developed independently  
✅ **Testable**: Easy to unit test individual components  
✅ **Extensible**: Add new features without modifying core  
✅ **Type-safe**: Rust's type system prevents many bugs  
✅ **Async-first**: Built for high-concurrency Kubernetes operations  

## Next Steps

1. Implement LLM integration (Phase 2)
2. Implement MCP tool execution (Phase 3)
3. Test end-to-end with real Kubernetes cluster
4. Add REST API for goal management (Phase 5)
5. Deploy as production service

## Contributing

Each feature is marked with its status:
- ✅ Complete and tested
- 🚧 In progress
- ⚠️ Stub only (needs implementation)
- 📋 Planned

Pick any ⚠️ feature to work on!

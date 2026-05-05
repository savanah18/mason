# Task Viewer Extension - Modularization & Delete Agent Fix

## Changes Made

### 1. Modularized Panel Structure
Split the monolithic `extension.ts` (1400+ lines) into separate modules:

- **src/panels/base.ts** - Base class for all panels with shared utilities
  - `loadHtmlFile()` - Load and inject stylesheet paths
  - `parseJson()` - Safe JSON parsing
  - `formatDateTimeCompact()` - Compact timestamp formatting
  - `sendData()` / `sendActionResult()` - UI message helpers

- **src/panels/agent-management.ts** - Agent Management Panel (extracted)
  - Complete refactor of agent lifecycle management
  - Agent registration, deletion, instantiation
  - Redis-backed agent record retrieval with filesystem fallback
  - HTTP request handling via `postToBackend()` method

- **src/extension.ts** - Reduced to ~850 lines
  - Central extension activation and command registration
  - Dashboard, Workflow, SystemPrompts, PromptOptimization panels (inline for now)
  - Redis client initialization and management
  - Imports `AgentManagementPanel` from `./panels/agent-management`

### 2. Delete Agent Button - Fixed Issues

**Root Cause**: Extension required reloading after code changes to pick up new message handlers.

**Improvements in AgentManagementPanel**:
1. Added console logging to all message handlers for debugging:
   ```typescript
   console.log('[Agent Management] Received command:', message.command);
   ```

2. Consolidated HTTP requests into `postToBackend(path, method, payload)`:
   - Handles both POST (register) and DELETE (delete) methods
   - Consistent error handling and response validation
   - Reads `taskViewer.agentManager.backendUrl` configuration

3. Wrapped all message handlers in try/catch to log errors:
   ```typescript
   try {
     // Handle command
   } catch (error) {
     console.error('[Agent Management] Error handling command:', message.command, error);
   }
   ```

### 3. Delete Agent Workflow

**Backend**: `DELETE /api/agents/{persona}`
- Implemented in [management/backend/app.py](../../../management/backend/app.py)
- Calls `registry.delete_agent(persona)` 
- Removes agent-records and system-prompts keys from Redis

**Extension**:
- Message command: `deleteAgent`
- Calls `postToBackend()` with DELETE method
- Sends success/failure message to webview
- Refreshes agent list on success

**Webview**:
- Button with confirmation dialog
- Sends `{ command: 'deleteAgent', persona: '...' }`
- Displays action result (success or error)

## Testing the Delete Button

1. **Open the extension in VS Code**
   ```bash
   code /root/workspace/lnd/aiops/apps/newbie-app/ux/vscode-task-viewer
   ```

2. **Run the extension** (F5 or Launch Debug)

3. **Check browser console** if delete fails:
   - Look for: `[Agent Management] Received command: deleteAgent`
   - Check backend is running on http://localhost:8010
   - Verify Redis is accessible

4. **Backend server** (if not running):
   ```bash
   cd /root/workspace/lnd/aiops/apps/newbie-app
   python -m uvicorn management.backend.app:app --host 0.0.0.0 --port 8010
   ```

## File Structure

```
ux/vscode-task-viewer/src/
  ├── extension.ts          # Main extension (850 lines, reduced from 1400)
  └── panels/
      ├── base.ts           # Base panel class
      ├── agent-management.ts # Agent management panel
      └── (future: dashboard.ts, workflows.ts, etc.)
```

## Next Steps for Full Modularization

To complete modularization, extract remaining panels:
- `src/panels/dashboard.ts` - Dashboard panel
- `src/panels/workflows.ts` - Workflow panel  
- `src/panels/system-prompts.ts` - System prompts panel
- `src/panels/prompt-optimization.ts` - Prompt optimization panel

Each panel would follow the `BasePanel` pattern for consistency.

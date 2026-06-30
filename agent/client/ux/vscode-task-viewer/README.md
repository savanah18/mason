# Newbie Task Viewer Extension

A VS Code extension that mirrors the Streamlit-based task-viewer app, providing native panels to browse and interact with Redis-backed task records for workflows, system prompts, and prompt optimization candidates.

## Features

- **Workflow Index**: Browse all workflow executions, filter by persona, search across task/result/metadata.
- **System Prompts**: View system prompts for each persona, annotate with feedback and remarks, edit and save changes.
- **Prompt Optimization**: Review candidate prompt optimization diffs, accept/reject candidates, and write back to goal.yaml files.
- **Redis Integration**: Direct connection to Redis for real-time data fetching and storage.
- **Side Panel UI**: All views launch as side panels for easy multitasking alongside coding.

## Installation

1. Navigate to the extension directory:
   ```bash
   cd ux/task-viewer/vscode-task-viewer
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Build the extension:
   ```bash
   npm run compile
   ```

4. Launch the Extension Development Host in VS Code (`F5`), or package it:
   ```bash
   npm run package
   ```

## Configuration

Configure Redis connection via VS Code settings (`settings.json`):

```json
{
  "taskViewer.redis.host": "localhost",
  "taskViewer.redis.port": 6379,
  "taskViewer.redis.password": "",
  "taskViewer.redis.database": 0
}
```

## Commands

- **Task Viewer: Open Dashboard** — Opens the main dashboard with quick access to all views.
- **Task Viewer: Open Workflows** — Browse workflow execution records.
- **Task Viewer: Open System Prompts** — View and edit system prompts, add feedback and remarks.
- **Task Viewer: Open Prompt Optimization** — Review candidate prompts, accept/reject optimizations.

## Development

- Run in watch mode:
  ```bash
  npm run watch
  ```

- Press `F5` in VS Code to start the Extension Development Host.

- Reload the window (`Ctrl+Shift+P` → "Developer: Reload Window") to test changes.

## Architecture

- **Redis Manager**: Handles connections and queries for workflows, system prompts, and candidate prompts.
- **Webview Panels**: Each view (workflows, system prompts, optimization) is a separate webview panel with its own HTML/CSS/JS.
- **Extension Entry**: `src/extension.ts` registers commands and manages panel lifecycle.

## License

Same as parent project.

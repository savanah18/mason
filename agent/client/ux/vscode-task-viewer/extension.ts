import * as vscode from 'vscode';
import * as path from 'path';
import { createClient, RedisClientType } from 'redis';

let redisClient: RedisClientType | null = null;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  console.log('[Task Viewer] Activating extension');

  // Register commands
  const dashboardCmd = vscode.commands.registerCommand('newbieTaskViewer.openDashboard', async () => {
    await DashboardPanel.createOrShow(context);
  });

  const workflowsCmd = vscode.commands.registerCommand('newbieTaskViewer.openWorkflows', async () => {
    await WorkflowPanel.createOrShow(context);
  });

  const promptsCmd = vscode.commands.registerCommand('newbieTaskViewer.openSystemPrompts', async () => {
    await SystemPromptsPanel.createOrShow(context);
  });

  const optimizationCmd = vscode.commands.registerCommand('newbieTaskViewer.openPromptOptimization', async () => {
    await PromptOptimizationPanel.createOrShow(context);
  });

  context.subscriptions.push(dashboardCmd, workflowsCmd, promptsCmd, optimizationCmd);

  // Initialize Redis connection
  try {
    await initializeRedisClient();
    vscode.window.showInformationMessage('Task Viewer: Redis connected');
  } catch (error) {
    vscode.window.showWarningMessage(`Task Viewer: Redis connection failed - ${error}`);
  }
}

export function deactivate(): void {
  void redisClient?.disconnect();
  redisClient = null;
}

async function initializeRedisClient(): Promise<void> {
  const config = vscode.workspace.getConfiguration('taskViewer.redis');
  const host = config.get<string>('host', 'localhost');
  const port = config.get<number>('port', 6379);
  const password = config.get<string>('password', '');
  const database = config.get<number>('database', 0);

  redisClient = createClient({
    host,
    port,
    password: password || undefined,
    database,
  } as any);

  redisClient.on('error', (err) => console.error('[Task Viewer Redis]', err));

  await redisClient.connect();
}

function getRedisClient(): RedisClientType {
  if (!redisClient) {
    throw new Error('Redis client not initialized');
  }
  return redisClient;
}

// ============================================================================
// Dashboard Panel
// ============================================================================

class DashboardPanel {
  private static instance: DashboardPanel | undefined;

  private constructor(private readonly panel: vscode.WebviewPanel) {
    this.panel.onDidDispose(() => {
      DashboardPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message.command === 'openWorkflows') {
        await WorkflowPanel.createOrShow(this.panel._context);
      } else if (message.command === 'openSystemPrompts') {
        await SystemPromptsPanel.createOrShow(this.panel._context);
      } else if (message.command === 'openPromptOptimization') {
        await PromptOptimizationPanel.createOrShow(this.panel._context);
      }
    });

    this.panel.webview.html = this.getHtml();
  }

  static async createOrShow(context: vscode.ExtensionContext): Promise<void> {
    if (DashboardPanel.instance) {
      DashboardPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'taskViewerDashboard',
      'Task Viewer Dashboard',
      vscode.ViewColumn.Beside,
      { enableScripts: true }
    );

    (panel as any)._context = context;
    DashboardPanel.instance = new DashboardPanel(panel);
  }

  private getHtml(): string {
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
      font-family: var(--vscode-font-family); 
      color: var(--vscode-foreground);
      background-color: var(--vscode-editor-background);
      padding: 20px;
    }
    h1 { margin-bottom: 24px; font-size: 24px; font-weight: 600; }
    .dashboard { display: grid; gap: 16px; }
    .card { 
      border: 1px solid var(--vscode-panel-border); 
      border-radius: 6px;
      padding: 16px;
      cursor: pointer;
      transition: background-color 0.2s;
    }
    .card:hover { background-color: var(--vscode-list-hoverBackground); }
    .card strong { display: block; font-size: 16px; margin-bottom: 8px; }
    .card p { font-size: 13px; line-height: 1.4; color: var(--vscode-descriptionForeground); }
  </style>
</head>
<body>
  <h1>📊 Task Viewer</h1>
  <div class="dashboard">
    <div class="card" onclick="openView('workflows')">
      <strong>🔄 Workflows</strong>
      <p>Browse workflow execution records, filter by persona, search tasks and results.</p>
    </div>
    <div class="card" onclick="openView('prompts')">
      <strong>📝 System Prompts</strong>
      <p>View system prompts for each persona, add feedback and remarks, edit and save.</p>
    </div>
    <div class="card" onclick="openView('optimization')">
      <strong>✨ Prompt Optimization</strong>
      <p>Review prompt optimization candidates, view diffs, accept/reject optimizations.</p>
    </div>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    function openView(view) {
      if (view === 'workflows') vscode.postMessage({command: 'openWorkflows'});
      else if (view === 'prompts') vscode.postMessage({command: 'openSystemPrompts'});
      else if (view === 'optimization') vscode.postMessage({command: 'openPromptOptimization'});
    }
  </script>
</body>
</html>`;
  }
}

// ============================================================================
// Workflow Panel
// ============================================================================

class WorkflowPanel {
  private static instance: WorkflowPanel | undefined;
  private records: any[] = [];
  private filteredRecords: any[] = [];
  private sortColumn = 'created_at';
  private sortAsc = false;

  private constructor(private readonly panel: vscode.WebviewPanel) {
    this.panel.onDidDispose(() => {
      WorkflowPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message.command === 'init') {
        this.records = await this.loadRecords();
        this.filteredRecords = [...this.records];
        this.render();
      } else if (message.command === 'filter') {
        this.applyFilters(message.persona, message.search);
        this.render();
      } else if (message.command === 'sort') {
        this.sortRecords(message.column);
        this.render();
      }
    });

    this.panel.webview.html = this.getHtml();
  }

  static async createOrShow(context: vscode.ExtensionContext): Promise<void> {
    if (WorkflowPanel.instance) {
      WorkflowPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'taskViewerWorkflows',
      'Workflows',
      vscode.ViewColumn.Beside,
      { enableScripts: true }
    );

    WorkflowPanel.instance = new WorkflowPanel(panel);
    WorkflowPanel.instance.panel.webview.postMessage({ command: 'init' });
  }

  private async loadRecords(): Promise<any[]> {
    const client = getRedisClient();
    const keyPattern = 'workflow:dev:*:*';
    const records: any[] = [];

    try {
      const keys = await client.keys(keyPattern);
      for (const key of keys.sort().reverse()) {
        const data = await client.hGetAll(key);
        const parts = key.split(':');
        if (parts.length >= 4) {
          records.push({
            key,
            persona: parts[2] || '',
            workflow_id: parts[3] || '',
            created_at: this.parseJson(data.metadata)?.created_at || '',
            task: data.task || '',
            result: data.result || '',
          });
        }
      }
    } catch (error) {
      console.error('[Workflows] Failed to load records:', error);
    }

    return records;
  }

  private applyFilters(persona: string, search: string): void {
    this.filteredRecords = this.records.filter((r) => {
      if (persona && persona !== 'All' && r.persona !== persona) return false;
      if (search) {
        const needle = search.toLowerCase();
        const haystack = `${r.key} ${r.persona} ${r.workflow_id} ${r.task} ${r.result}`.toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }

  private sortRecords(column: string): void {
    if (this.sortColumn === column) {
      this.sortAsc = !this.sortAsc;
    } else {
      this.sortColumn = column;
      this.sortAsc = true;
    }

    this.filteredRecords.sort((a, b) => {
      const aVal = a[column] || '';
      const bVal = b[column] || '';
      const cmp = String(aVal).localeCompare(String(bVal));
      return this.sortAsc ? cmp : -cmp;
    });
  }

  private parseJson(val: any): any {
    if (typeof val === 'string') {
      try {
        return JSON.parse(val);
      } catch {
        return null;
      }
    }
    return val;
  }

  private render(): void {
    const personas = ['All', ...new Set(this.records.map((r) => r.persona))];
    const rowsHtml = this.filteredRecords
      .map(
        (r) => `<tr>
      <td>${this.escapeHtml(r.key)}</td>
      <td>${this.escapeHtml(r.persona)}</td>
      <td>${this.escapeHtml(r.workflow_id)}</td>
      <td>${this.escapeHtml(r.created_at)}</td>
      <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(r.task.substring(0, 150))}</td>
      <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(r.result.substring(0, 200))}</td>
    </tr>`
      )
      .join('');

    const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
      font-family: var(--vscode-font-family); 
      color: var(--vscode-foreground);
      background-color: var(--vscode-editor-background);
      display: flex;
      height: 100vh;
    }
    .sidebar { 
      width: 240px; 
      border-right: 1px solid var(--vscode-panel-border);
      padding: 16px;
      overflow-y: auto;
      background-color: var(--vscode-sideBar-background);
    }
    .main { 
      flex: 1; 
      padding: 16px;
      overflow: auto;
    }
    h1 { font-size: 18px; margin-bottom: 16px; }
    h2 { font-size: 14px; margin-top: 16px; margin-bottom: 8px; font-weight: 600; }
    .form-group { margin-bottom: 12px; }
    label { display: block; font-size: 12px; margin-bottom: 4px; font-weight: 500; }
    input, select { 
      width: 100%; 
      padding: 6px; 
      border: 1px solid var(--vscode-input-border);
      background-color: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border-radius: 4px;
      font-size: 12px;
    }
    input:focus, select:focus { 
      outline: none; 
      border-color: var(--vscode-focusBorder);
    }
    table { 
      width: 100%; 
      border-collapse: collapse; 
      font-size: 12px;
      margin-top: 12px;
    }
    th, td { 
      padding: 8px; 
      text-align: left; 
      border-bottom: 1px solid var(--vscode-panel-border);
    }
    th { 
      background-color: var(--vscode-editor-selectionBackground);
      font-weight: 600;
      cursor: pointer;
      user-select: none;
    }
    th:hover { background-color: var(--vscode-list-hoverBackground); }
    tr:hover { background-color: var(--vscode-list-hoverBackground); }
    .info { font-size: 12px; color: var(--vscode-descriptionForeground); margin-bottom: 12px; }
  </style>
</head>
<body>
  <div class="sidebar">
    <h1>Filters</h1>
    <div class="form-group">
      <label>Persona</label>
      <select id="personaFilter" onchange="applyFilters()">
        ${personas.map((p) => `<option value="${p}">${p}</option>`).join('')}
      </select>
    </div>
    <div class="form-group">
      <label>Search</label>
      <input type="text" id="searchInput" placeholder="Search..." onkeyup="applyFilters()">
    </div>
  </div>
  <div class="main">
    <h1>Workflow Index</h1>
    <div class="info">Showing <strong>${this.filteredRecords.length}</strong> of <strong>${this.records.length}</strong> records</div>
    <table>
      <thead>
        <tr>
          <th onclick="sort('key')">Key</th>
          <th onclick="sort('persona')">Persona</th>
          <th onclick="sort('workflow_id')">Workflow ID</th>
          <th onclick="sort('created_at')">Created At</th>
          <th onclick="sort('task')">Task</th>
          <th onclick="sort('result')">Result</th>
        </tr>
      </thead>
      <tbody>
        ${rowsHtml}
      </tbody>
    </table>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    function applyFilters() {
      const persona = document.getElementById('personaFilter').value;
      const search = document.getElementById('searchInput').value;
      vscode.postMessage({command: 'filter', persona, search});
    }
    function sort(column) {
      vscode.postMessage({command: 'sort', column});
    }
  </script>
</body>
</html>`;

    this.panel.webview.html = html;
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}

// ============================================================================
// System Prompts Panel
// ============================================================================

class SystemPromptsPanel {
  private static instance: SystemPromptsPanel | undefined;
  private records: any[] = [];
  private filteredRecords: any[] = [];
  private sortColumn = 'created_at';
  private sortAsc = false;

  private constructor(private readonly panel: vscode.WebviewPanel) {
    this.panel.onDidDispose(() => {
      SystemPromptsPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message.command === 'init') {
        this.records = await this.loadRecords();
        this.filteredRecords = [...this.records];
        this.render();
      } else if (message.command === 'filter') {
        this.applyFilters(message.persona, message.search, message.feedbackOnly);
        this.render();
      } else if (message.command === 'sort') {
        this.sortRecords(message.column);
        this.render();
      }
    });

    this.panel.webview.html = this.getHtml();
  }

  static async createOrShow(context: vscode.ExtensionContext): Promise<void> {
    if (SystemPromptsPanel.instance) {
      SystemPromptsPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'taskViewerSystemPrompts',
      'System Prompts',
      vscode.ViewColumn.Beside,
      { enableScripts: true }
    );

    SystemPromptsPanel.instance = new SystemPromptsPanel(panel);
    SystemPromptsPanel.instance.panel.webview.postMessage({ command: 'init' });
  }

  private async loadRecords(): Promise<any[]> {
    const client = getRedisClient();
    const keyPattern = 'system-prompts:*';
    const records: any[] = [];

    try {
      const keys = await client.keys(keyPattern);
      for (const key of keys.sort().reverse()) {
        const data = await client.hGetAll(key);
        const metadata = this.parseJson(data.metadata) || {};
        const remarks = this.parseJson(data.remarks) || {};

        records.push({
          key,
          persona: metadata.persona || '',
          created_at: metadata.created_at || '',
          created_by: remarks.created_by || '',
          prompt: data.prompt || '',
          feedback: data.feedback || '',
          hasFeedback: Boolean(data.feedback && String(data.feedback).trim()),
        });
      }
    } catch (error) {
      console.error('[System Prompts] Failed to load records:', error);
    }

    return records;
  }

  private applyFilters(persona: string, search: string, feedbackOnly: boolean): void {
    this.filteredRecords = this.records.filter((r) => {
      if (persona && persona !== 'All' && r.persona !== persona) return false;
      if (feedbackOnly && !r.hasFeedback) return false;
      if (search) {
        const needle = search.toLowerCase();
        const haystack = `${r.key} ${r.persona} ${r.prompt} ${r.feedback}`.toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }

  private sortRecords(column: string): void {
    if (this.sortColumn === column) {
      this.sortAsc = !this.sortAsc;
    } else {
      this.sortColumn = column;
      this.sortAsc = true;
    }

    this.filteredRecords.sort((a, b) => {
      const aVal = a[column] || '';
      const bVal = b[column] || '';
      const cmp = String(aVal).localeCompare(String(bVal));
      return this.sortAsc ? cmp : -cmp;
    });
  }

  private parseJson(val: any): any {
    if (typeof val === 'string') {
      try {
        return JSON.parse(val);
      } catch {
        return null;
      }
    }
    return val;
  }

  private render(): void {
    const personas = ['All', ...new Set(this.records.map((r) => r.persona))];
    const rowsHtml = this.filteredRecords
      .map(
        (r) => `<tr>
      <td>${this.escapeHtml(r.key)}</td>
      <td>${this.escapeHtml(r.persona)}</td>
      <td>${this.escapeHtml(r.created_at)}</td>
      <td>${this.escapeHtml(r.created_by)}</td>
      <td>${r.hasFeedback ? '✓' : '—'}</td>
      <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(r.prompt.substring(0, 200))}</td>
    </tr>`
      )
      .join('');

    const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
      font-family: var(--vscode-font-family); 
      color: var(--vscode-foreground);
      background-color: var(--vscode-editor-background);
      display: flex;
      height: 100vh;
    }
    .sidebar { 
      width: 240px; 
      border-right: 1px solid var(--vscode-panel-border);
      padding: 16px;
      overflow-y: auto;
      background-color: var(--vscode-sideBar-background);
    }
    .main { 
      flex: 1; 
      padding: 16px;
      overflow: auto;
    }
    h1 { font-size: 18px; margin-bottom: 16px; }
    h2 { font-size: 14px; margin-top: 16px; margin-bottom: 8px; font-weight: 600; }
    .form-group { margin-bottom: 12px; }
    label { display: block; font-size: 12px; margin-bottom: 4px; font-weight: 500; }
    input, select { 
      width: 100%; 
      padding: 6px; 
      border: 1px solid var(--vscode-input-border);
      background-color: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border-radius: 4px;
      font-size: 12px;
    }
    input:focus, select:focus { 
      outline: none; 
      border-color: var(--vscode-focusBorder);
    }
    input[type="checkbox"] { width: auto; }
    table { 
      width: 100%; 
      border-collapse: collapse; 
      font-size: 12px;
      margin-top: 12px;
    }
    th, td { 
      padding: 8px; 
      text-align: left; 
      border-bottom: 1px solid var(--vscode-panel-border);
    }
    th { 
      background-color: var(--vscode-editor-selectionBackground);
      font-weight: 600;
      cursor: pointer;
      user-select: none;
    }
    th:hover { background-color: var(--vscode-list-hoverBackground); }
    tr:hover { background-color: var(--vscode-list-hoverBackground); }
    .info { font-size: 12px; color: var(--vscode-descriptionForeground); margin-bottom: 12px; }
  </style>
</head>
<body>
  <div class="sidebar">
    <h1>Filters</h1>
    <div class="form-group">
      <label>Persona</label>
      <select id="personaFilter" onchange="applyFilters()">
        ${personas.map((p) => `<option value="${p}">${p}</option>`).join('')}
      </select>
    </div>
    <div class="form-group">
      <label>Search</label>
      <input type="text" id="searchInput" placeholder="Search..." onkeyup="applyFilters()">
    </div>
    <div class="form-group">
      <label>
        <input type="checkbox" id="feedbackOnly" onchange="applyFilters()"> 
        Only with feedback
      </label>
    </div>
  </div>
  <div class="main">
    <h1>System Prompts</h1>
    <div class="info">Showing <strong>${this.filteredRecords.length}</strong> of <strong>${this.records.length}</strong> records</div>
    <table>
      <thead>
        <tr>
          <th onclick="sort('key')">Key</th>
          <th onclick="sort('persona')">Persona</th>
          <th onclick="sort('created_at')">Created At</th>
          <th onclick="sort('created_by')">Created By</th>
          <th onclick="sort('hasFeedback')">Feedback</th>
          <th onclick="sort('prompt')">Prompt</th>
        </tr>
      </thead>
      <tbody>
        ${rowsHtml}
      </tbody>
    </table>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    function applyFilters() {
      const persona = document.getElementById('personaFilter').value;
      const search = document.getElementById('searchInput').value;
      const feedbackOnly = document.getElementById('feedbackOnly').checked;
      vscode.postMessage({command: 'filter', persona, search, feedbackOnly});
    }
    function sort(column) {
      vscode.postMessage({command: 'sort', column});
    }
  </script>
</body>
</html>`;

    this.panel.webview.html = html;
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}

// ============================================================================
// Prompt Optimization Panel
// ============================================================================

class PromptOptimizationPanel {
  private static instance: PromptOptimizationPanel | undefined;
  private records: any[] = [];
  private filteredRecords: any[] = [];
  private sortColumn = 'created_at';
  private sortAsc = false;

  private constructor(private readonly panel: vscode.WebviewPanel) {
    this.panel.onDidDispose(() => {
      PromptOptimizationPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message.command === 'init') {
        this.records = await this.loadRecords();
        this.filteredRecords = [...this.records];
        this.render();
      } else if (message.command === 'filter') {
        this.applyFilters(message.persona, message.search);
        this.render();
      } else if (message.command === 'sort') {
        this.sortRecords(message.column);
        this.render();
      }
    });

    this.panel.webview.html = this.getHtml();
  }

  static async createOrShow(context: vscode.ExtensionContext): Promise<void> {
    if (PromptOptimizationPanel.instance) {
      PromptOptimizationPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'taskViewerPromptOptimization',
      'Prompt Optimization',
      vscode.ViewColumn.Beside,
      { enableScripts: true }
    );

    PromptOptimizationPanel.instance = new PromptOptimizationPanel(panel);
    PromptOptimizationPanel.instance.panel.webview.postMessage({ command: 'init' });
  }

  private async loadRecords(): Promise<any[]> {
    const client = getRedisClient();
    const keyPattern = 'prompt-optimization:candidate-prompts:*';
    const records: any[] = [];

    try {
      const keys = await client.keys(keyPattern);
      for (const key of keys.sort().reverse()) {
        const data = await client.hGetAll(key);
        const keyParts = key.split(':');
        if (keyParts.length >= 5) {
          records.push({
            key,
            persona: keyParts[3] || '',
            workflow_id: keyParts[4] || '',
            created_at: data.created_at || '',
            updated_at: data.updated_at || '',
            created_by: data.created_by || '',
            updated_by: data.updated_by || '',
            updated_prompt: data.updated_prompt || '',
          });
        }
      }
    } catch (error) {
      console.error('[Prompt Optimization] Failed to load records:', error);
    }

    return records;
  }

  private applyFilters(persona: string, search: string): void {
    this.filteredRecords = this.records.filter((r) => {
      if (persona && persona !== 'All' && r.persona !== persona) return false;
      if (search) {
        const needle = search.toLowerCase();
        const haystack = `${r.key} ${r.persona} ${r.workflow_id} ${r.updated_prompt}`.toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }

  private sortRecords(column: string): void {
    if (this.sortColumn === column) {
      this.sortAsc = !this.sortAsc;
    } else {
      this.sortColumn = column;
      this.sortAsc = true;
    }

    this.filteredRecords.sort((a, b) => {
      const aVal = a[column] || '';
      const bVal = b[column] || '';
      const cmp = String(aVal).localeCompare(String(bVal));
      return this.sortAsc ? cmp : -cmp;
    });
  }

  private parseJson(val: any): any {
    if (typeof val === 'string') {
      try {
        return JSON.parse(val);
      } catch {
        return null;
      }
    }
    return val;
  }

  private render(): void {
    const personas = ['All', ...new Set(this.records.map((r) => r.persona))];
    const rowsHtml = this.filteredRecords
      .map(
        (r) => `<tr>
      <td>${this.escapeHtml(r.key)}</td>
      <td>${this.escapeHtml(r.persona)}</td>
      <td>${this.escapeHtml(r.workflow_id)}</td>
      <td>${this.escapeHtml(r.created_at)}</td>
      <td>${this.escapeHtml(r.updated_at)}</td>
      <td>${this.escapeHtml(r.created_by)}</td>
      <td>${this.escapeHtml(r.updated_by)}</td>
      <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(r.updated_prompt.substring(0, 150))}</td>
    </tr>`
      )
      .join('');

    const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
      font-family: var(--vscode-font-family); 
      color: var(--vscode-foreground);
      background-color: var(--vscode-editor-background);
      display: flex;
      height: 100vh;
    }
    .sidebar { 
      width: 240px; 
      border-right: 1px solid var(--vscode-panel-border);
      padding: 16px;
      overflow-y: auto;
      background-color: var(--vscode-sideBar-background);
    }
    .main { 
      flex: 1; 
      padding: 16px;
      overflow: auto;
    }
    h1 { font-size: 18px; margin-bottom: 16px; }
    h2 { font-size: 14px; margin-top: 16px; margin-bottom: 8px; font-weight: 600; }
    .form-group { margin-bottom: 12px; }
    label { display: block; font-size: 12px; margin-bottom: 4px; font-weight: 500; }
    input, select { 
      width: 100%; 
      padding: 6px; 
      border: 1px solid var(--vscode-input-border);
      background-color: var(--vscode-input-background);
      color: var(--vscode-input-foreground);
      border-radius: 4px;
      font-size: 12px;
    }
    input:focus, select:focus { 
      outline: none; 
      border-color: var(--vscode-focusBorder);
    }
    table { 
      width: 100%; 
      border-collapse: collapse; 
      font-size: 12px;
      margin-top: 12px;
    }
    th, td { 
      padding: 8px; 
      text-align: left; 
      border-bottom: 1px solid var(--vscode-panel-border);
    }
    th { 
      background-color: var(--vscode-editor-selectionBackground);
      font-weight: 600;
      cursor: pointer;
      user-select: none;
    }
    th:hover { background-color: var(--vscode-list-hoverBackground); }
    tr:hover { background-color: var(--vscode-list-hoverBackground); }
    .info { font-size: 12px; color: var(--vscode-descriptionForeground); margin-bottom: 12px; }
  </style>
</head>
<body>
  <div class="sidebar">
    <h1>Filters</h1>
    <div class="form-group">
      <label>Persona</label>
      <select id="personaFilter" onchange="applyFilters()">
        ${personas.map((p) => `<option value="${p}">${p}</option>`).join('')}
      </select>
    </div>
    <div class="form-group">
      <label>Search</label>
      <input type="text" id="searchInput" placeholder="Search..." onkeyup="applyFilters()">
    </div>
  </div>
  <div class="main">
    <h1>Prompt Optimization Candidates</h1>
    <div class="info">Showing <strong>${this.filteredRecords.length}</strong> of <strong>${this.records.length}</strong> records</div>
    <table>
      <thead>
        <tr>
          <th onclick="sort('key')">Key</th>
          <th onclick="sort('persona')">Persona</th>
          <th onclick="sort('workflow_id')">Workflow ID</th>
          <th onclick="sort('created_at')">Created At</th>
          <th onclick="sort('updated_at')">Updated At</th>
          <th onclick="sort('created_by')">Created By</th>
          <th onclick="sort('updated_by')">Updated By</th>
          <th onclick="sort('updated_prompt')">Updated Prompt</th>
        </tr>
      </thead>
      <tbody>
        ${rowsHtml}
      </tbody>
    </table>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    function applyFilters() {
      const persona = document.getElementById('personaFilter').value;
      const search = document.getElementById('searchInput').value;
      vscode.postMessage({command: 'filter', persona, search});
    }
    function sort(column) {
      vscode.postMessage({command: 'sort', column});
    }
  </script>
</body>
</html>`;

    this.panel.webview.html = html;
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}
import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { createClient, RedisClientType } from 'redis';
import { parse as parseYaml } from 'yaml';

let redisClient: RedisClientType | null = null;
let dashboardPanel: DashboardPanel | undefined;
let workflowPanel: WorkflowPanel | undefined;
let promptsPanel: SystemPromptsPanel | undefined;
let optimizationPanel: PromptOptimizationPanel | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  console.log('[Task Viewer] Activating extension');

  // Register commands
  const dashboardCmd = vscode.commands.registerCommand('newbieTaskViewer.openDashboard', async () => {
    await DashboardPanel.createOrShow(context);
  });

  const workflowsCmd = vscode.commands.registerCommand('newbieTaskViewer.openWorkflows', async () => {
    await WorkflowPanel.createOrShow(context);
  });

  const promptsCmd = vscode.commands.registerCommand('newbieTaskViewer.openSystemPrompts', async () => {
    await SystemPromptsPanel.createOrShow(context);
  });

  const optimizationCmd = vscode.commands.registerCommand('newbieTaskViewer.openPromptOptimization', async () => {
    await PromptOptimizationPanel.createOrShow(context);
  });

  context.subscriptions.push(dashboardCmd, workflowsCmd, promptsCmd, optimizationCmd);

  // Initialize Redis connection
  try {
    await initializeRedisClient();
    vscode.window.showInformationMessage('Task Viewer: Redis connected');
  } catch (error) {
    vscode.window.showWarningMessage(`Task Viewer: Redis connection failed - ${error}`);
  }
}

export function deactivate(): void {
  void redisClient?.disconnect();
  redisClient = null;
}

async function initializeRedisClient(): Promise<void> {
  const config = vscode.workspace.getConfiguration('taskViewer.redis');
  const host = config.get<string>('host', 'localhost');
  const port = config.get<number>('port', 6379);
  const password = config.get<string>('password', '');
  const database = config.get<number>('database', 0);

  redisClient = createClient({
    host,
    port,
    password: password || undefined,
    database,
  } as any);

  redisClient.on('error', (err) => console.error('[Task Viewer Redis]', err));

  await redisClient.connect();
}

function getRedisClient(): RedisClientType {
  if (!redisClient) {
    throw new Error('Redis client not initialized');
  }
  return redisClient;
}

// ============================================================================
// Dashboard Panel
// ============================================================================

class DashboardPanel {
  private static instance: DashboardPanel | undefined;

  private constructor(private readonly panel: vscode.WebviewPanel) {
    this.panel.onDidDispose(() => {
      DashboardPanel.instance = undefined;
    });

    this.panel.webview.html = this.getHtml();
  }

  static async createOrShow(context: vscode.ExtensionContext): Promise<void> {
    if (DashboardPanel.instance) {
      DashboardPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'taskViewerDashboard',
      'Task Viewer Dashboard',
      vscode.ViewColumn.Beside,
      {}
    );

    DashboardPanel.instance = new DashboardPanel(panel);
  }

  private getHtml(): string {
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { font-family: var(--vscode-font-family); padding: 20px; color: var(--vscode-foreground); }
          .card { border: 1px solid var(--vscode-panel-border); padding: 12px; margin: 8px 0; border-radius: 4px; cursor: pointer; }
          .card:hover { background-color: var(--vscode-list-hoverBackground); }
          h1 { margin-top: 0; }
          p { margin: 4px 0; }
        </style>
      </head>
      <body>
        <h1>Task Viewer</h1>
        <p>Quick access to all task viewer panels:</p>
        <div class="card" onclick="vscode.postMessage({command: 'openWorkflows'})">
          <strong>📋 Workflows</strong>
          <p>Browse workflow execution records, filter by persona, search tasks and results.</p>
        </div>
        <div class="card" onclick="vscode.postMessage({command: 'openSystemPrompts'})">
          <strong>📝 System Prompts</strong>
          <p>View system prompts for each persona, add feedback and remarks, edit and save.</p>
        </div>
        <div class="card" onclick="vscode.postMessage({command: 'openPromptOptimization'})">
          <strong>✨ Prompt Optimization</strong>
          <p>Review prompt optimization candidates, view diffs, accept/reject optimizations.</p>
        </div>
      </body>
      <script>
        const vscode = acquireVsCodeApi();
      </script>
      </html>
    `;
  }
}

// ============================================================================
// Workflow Panel
// ============================================================================

interface WorkflowRecord {
  key: string;
  persona: string;
  workflow_id: string;
  created_at: string;
  task: string;
  result: string;
  metadata: Record<string, any>;
  stats: Record<string, any>;
}

class WorkflowPanel {
  private static instance: WorkflowPanel | undefined;

  private constructor(private readonly panel: vscode.WebviewPanel, private records: WorkflowRecord[]) {
    this.panel.onDidDispose(() => {
      WorkflowPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message.command === 'refresh') {
        await this.refresh();
      }
    });

    this.panel.webview.html = this.getHtml();
  }

  static async createOrShow(context: vscode.ExtensionContext): Promise<void> {
    if (WorkflowPanel.instance) {
      WorkflowPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const records = await WorkflowPanel.loadRecords();
    const panel = vscode.window.createWebviewPanel(
      'taskViewerWorkflows',
      'Workflows',
      vscode.ViewColumn.Beside,
      {}
    );

    WorkflowPanel.instance = new WorkflowPanel(panel, records);
  }

  private static async loadRecords(): Promise<WorkflowRecord[]> {
    const client = getRedisClient();
    const keyPattern = 'workflow:dev:*:*';
    const records: WorkflowRecord[] = [];

    try {
      const keys = await client.keys(keyPattern);
      for (const key of keys.sort()) {
        const data = await client.hGetAll(key);
        const parts = key.split(':');
        if (parts.length >= 4) {
          records.push({
            key,
            persona: parts[2] || '',
            workflow_id: parts[3] || '',
            created_at: (data.metadata ? JSON.parse(data.metadata as string).created_at : '') || '',
            task: data.task || '',
            result: data.result || '',
            metadata: data.metadata ? JSON.parse(data.metadata as string) : {},
            stats: data.stats ? JSON.parse(data.stats as string) : {},
          });
        }
      }
    } catch (error) {
      console.error('[Task Viewer Workflows] Failed to load records:', error);
    }

    return records;
  }

  private async refresh(): Promise<void> {
    this.records = await WorkflowPanel.loadRecords();
    this.panel.webview.html = this.getHtml();
  }

  private getHtml(): string {
    const recordsJson = JSON.stringify(this.records);
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { font-family: var(--vscode-font-family); padding: 16px; color: var(--vscode-foreground); }
          h1 { margin-top: 0; margin-bottom: 12px; }
          table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
          th, td { padding: 8px; text-align: left; border-bottom: 1px solid var(--vscode-panel-border); }
          th { background-color: var(--vscode-editor-selectionBackground); font-weight: bold; }
          tr:hover { background-color: var(--vscode-list-hoverBackground); }
          .truncate { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          button { padding: 6px 12px; background-color: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; border-radius: 2px; cursor: pointer; }
          button:hover { background-color: var(--vscode-button-hoverBackground); }
        </style>
      </head>
      <body>
        <h1>Workflows</h1>
        <button onclick="refresh()">Refresh</button>
        <p>Total records: <strong>${this.records.length}</strong></p>
        <table>
          <thead>
            <tr>
              <th>Persona</th>
              <th>Workflow ID</th>
              <th>Created At</th>
              <th>Task (truncated)</th>
              <th>Result (truncated)</th>
            </tr>
          </thead>
          <tbody>
            ${this.records.map(r => `
              <tr>
                <td>${escapeHtml(r.persona)}</td>
                <td>${escapeHtml(r.workflow_id)}</td>
                <td>${escapeHtml(r.created_at)}</td>
                <td class="truncate">${escapeHtml(r.task.substring(0, 180))}</td>
                <td class="truncate">${escapeHtml(r.result.substring(0, 220))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </body>
      <script>
        const vscode = acquireVsCodeApi();
        function refresh() {
          vscode.postMessage({command: 'refresh'});
        }
      </script>
      </html>
    `;
  }
}

// ============================================================================
// System Prompts Panel
// ============================================================================

interface SystemPromptRecord {
  key: string;
  persona: string;
  created_at: string;
  created_by: string;
  prompt: string;
  feedback: string;
  remarks: Record<string, any>;
  metadata: Record<string, any>;
}

class SystemPromptsPanel {
  private static instance: SystemPromptsPanel | undefined;

  private constructor(private readonly panel: vscode.WebviewPanel, private records: SystemPromptRecord[]) {
    this.panel.onDidDispose(() => {
      SystemPromptsPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message.command === 'refresh') {
        await this.refresh();
      }
    });

    this.panel.webview.html = this.getHtml();
  }

  static async createOrShow(context: vscode.ExtensionContext): Promise<void> {
    if (SystemPromptsPanel.instance) {
      SystemPromptsPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const records = await SystemPromptsPanel.loadRecords();
    const panel = vscode.window.createWebviewPanel(
      'taskViewerSystemPrompts',
      'System Prompts',
      vscode.ViewColumn.Beside,
      {}
    );

    SystemPromptsPanel.instance = new SystemPromptsPanel(panel, records);
  }

  private static async loadRecords(): Promise<SystemPromptRecord[]> {
    const client = getRedisClient();
    const keyPattern = 'system-prompts:*';
    const records: SystemPromptRecord[] = [];

    try {
      const keys = await client.keys(keyPattern);
      for (const key of keys.sort()) {
        const data = await client.hGetAll(key);
        const metadata = data.metadata ? JSON.parse(data.metadata as string) : {};
        const remarks = data.remarks ? JSON.parse(data.remarks as string) : {};
        const keyParts = key.split(':');
        const persona = metadata.persona || (keyParts[1] || '');

        records.push({
          key,
          persona,
          created_at: metadata.created_at || (keyParts[2] || ''),
          created_by: (remarks as any).created_by || '',
          prompt: data.prompt || '',
          feedback: data.feedback || '',
          remarks,
          metadata,
        });
      }
    } catch (error) {
      console.error('[Task Viewer System Prompts] Failed to load records:', error);
    }

    return records;
  }

  private async refresh(): Promise<void> {
    this.records = await SystemPromptsPanel.loadRecords();
    this.panel.webview.html = this.getHtml();
  }

  private getHtml(): string {
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { font-family: var(--vscode-font-family); padding: 16px; color: var(--vscode-foreground); }
          h1 { margin-top: 0; margin-bottom: 12px; }
          table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
          th, td { padding: 8px; text-align: left; border-bottom: 1px solid var(--vscode-panel-border); }
          th { background-color: var(--vscode-editor-selectionBackground); font-weight: bold; }
          tr:hover { background-color: var(--vscode-list-hoverBackground); }
          .truncate { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          button { padding: 6px 12px; background-color: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; border-radius: 2px; cursor: pointer; }
          button:hover { background-color: var(--vscode-button-hoverBackground); }
        </style>
      </head>
      <body>
        <h1>System Prompts</h1>
        <button onclick="refresh()">Refresh</button>
        <p>Total records: <strong>${this.records.length}</strong></p>
        <table>
          <thead>
            <tr>
              <th>Persona</th>
              <th>Created At</th>
              <th>Created By</th>
              <th>Has Feedback</th>
              <th>Prompt (truncated)</th>
            </tr>
          </thead>
          <tbody>
            ${this.records.map(r => `
              <tr>
                <td>${escapeHtml(r.persona)}</td>
                <td>${escapeHtml(r.created_at)}</td>
                <td>${escapeHtml(r.created_by)}</td>
                <td>${r.feedback.trim() ? '✓' : '—'}</td>
                <td class="truncate">${escapeHtml(r.prompt.substring(0, 180))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </body>
      <script>
        const vscode = acquireVsCodeApi();
        function refresh() {
          vscode.postMessage({command: 'refresh'});
        }
      </script>
      </html>
    `;
  }
}

// ============================================================================
// Prompt Optimization Panel
// ============================================================================

interface CandidateRecord {
  key: string;
  persona: string;
  workflow_id: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  original_prompt: string;
  updated_prompt: string;
}

class PromptOptimizationPanel {
  private static instance: PromptOptimizationPanel | undefined;

  private constructor(private readonly panel: vscode.WebviewPanel, private records: CandidateRecord[]) {
    this.panel.onDidDispose(() => {
      PromptOptimizationPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message.command === 'refresh') {
        await this.refresh();
      }
    });

    this.panel.webview.html = this.getHtml();
  }

  static async createOrShow(context: vscode.ExtensionContext): Promise<void> {
    if (PromptOptimizationPanel.instance) {
      PromptOptimizationPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const records = await PromptOptimizationPanel.loadRecords();
    const panel = vscode.window.createWebviewPanel(
      'taskViewerPromptOptimization',
      'Prompt Optimization',
      vscode.ViewColumn.Beside,
      {}
    );

    PromptOptimizationPanel.instance = new PromptOptimizationPanel(panel, records);
  }

  private static async loadRecords(): Promise<CandidateRecord[]> {
    const client = getRedisClient();
    const keyPattern = 'prompt-optimization:candidate-prompts:*';
    const records: CandidateRecord[] = [];

    try {
      const keys = await client.keys(keyPattern);
      for (const key of keys.sort()) {
        const data = await client.hGetAll(key);
        const keyParts = key.split(':');
        if (keyParts.length >= 5) {
          records.push({
            key,
            persona: keyParts[3] || '',
            workflow_id: keyParts[4] || '',
            created_at: data.created_at || '',
            updated_at: data.updated_at || '',
            created_by: data.created_by || '',
            updated_by: data.updated_by || '',
            original_prompt: data.original_prompt || '',
            updated_prompt: data.updated_prompt || '',
          });
        }
      }
    } catch (error) {
      console.error('[Task Viewer Prompt Optimization] Failed to load records:', error);
    }

    return records;
  }

  private async refresh(): Promise<void> {
    this.records = await PromptOptimizationPanel.loadRecords();
    this.panel.webview.html = this.getHtml();
  }

  private getHtml(): string {
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { font-family: var(--vscode-font-family); padding: 16px; color: var(--vscode-foreground); }
          h1 { margin-top: 0; margin-bottom: 12px; }
          table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
          th, td { padding: 8px; text-align: left; border-bottom: 1px solid var(--vscode-panel-border); }
          th { background-color: var(--vscode-editor-selectionBackground); font-weight: bold; }
          tr:hover { background-color: var(--vscode-list-hoverBackground); }
          .truncate { max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          button { padding: 6px 12px; background-color: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; border-radius: 2px; cursor: pointer; }
          button:hover { background-color: var(--vscode-button-hoverBackground); }
        </style>
      </head>
      <body>
        <h1>Prompt Optimization Candidates</h1>
        <button onclick="refresh()">Refresh</button>
        <p>Total records: <strong>${this.records.length}</strong></p>
        <table>
          <thead>
            <tr>
              <th>Persona</th>
              <th>Workflow ID</th>
              <th>Created At</th>
              <th>Updated At</th>
              <th>Created By</th>
              <th>Updated By</th>
              <th>Updated Prompt (truncated)</th>
            </tr>
          </thead>
          <tbody>
            ${this.records.map(r => `
              <tr>
                <td>${escapeHtml(r.persona)}</td>
                <td>${escapeHtml(r.workflow_id)}</td>
                <td>${escapeHtml(r.created_at)}</td>
                <td>${escapeHtml(r.updated_at)}</td>
                <td>${escapeHtml(r.created_by)}</td>
                <td>${escapeHtml(r.updated_by)}</td>
                <td class="truncate">${escapeHtml(r.updated_prompt.substring(0, 160))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </body>
      <script>
        const vscode = acquireVsCodeApi();
        function refresh() {
          vscode.postMessage({command: 'refresh'});
        }
      </script>
      </html>
    `;
  }
}

// ============================================================================
// Utility Functions
// ============================================================================

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { createClient, RedisClientType } from 'redis';
import { AgentManagementPanel } from './panels/agent-management';

let redisClient: RedisClientType | null = null;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  console.log('[Task Viewer] Activating extension');

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

  const agentManagementCmd = vscode.commands.registerCommand('newbieTaskViewer.openAgentManagement', async () => {
    await AgentManagementPanel.createOrShow(context, getRedisClient());
  });

  context.subscriptions.push(dashboardCmd, workflowsCmd, promptsCmd, optimizationCmd, agentManagementCmd);

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
  private context: vscode.ExtensionContext | null = null;

  private constructor(private readonly panel: vscode.WebviewPanel, context?: vscode.ExtensionContext) {
    if (context) this.context = context;

    this.panel.onDidDispose(() => {
      DashboardPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (!this.context) return;
      if (message.command === 'openWorkflows') {
        await WorkflowPanel.createOrShow(this.context);
      } else if (message.command === 'openSystemPrompts') {
        await SystemPromptsPanel.createOrShow(this.context);
      } else if (message.command === 'openPromptOptimization') {
        await PromptOptimizationPanel.createOrShow(this.context);
      } else if (message.command === 'openAgentManagement') {
        await AgentManagementPanel.createOrShow(this.context, (() => {
          try {
            return getRedisClient();
          } catch {
            return null;
          }
        })());
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

    DashboardPanel.instance = new DashboardPanel(panel, context);
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
    <div class="card" onclick="openView('agents')">
      <strong>🤖 Agent Management</strong>
      <p>Register persona agents, validate config files, and control lifecycle actions.</p>
    </div>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    function openView(view) {
      if (view === 'workflows') vscode.postMessage({command: 'openWorkflows'});
      else if (view === 'prompts') vscode.postMessage({command: 'openSystemPrompts'});
      else if (view === 'optimization') vscode.postMessage({command: 'openPromptOptimization'});
      else if (view === 'agents') vscode.postMessage({command: 'openAgentManagement'});
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
  private static readonly NULL_PLACEHOLDER = 'null';

  private constructor(private readonly panel: vscode.WebviewPanel, context: vscode.ExtensionContext) {
    this.panel.onDidDispose(() => {
      WorkflowPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message.command === 'init') {
        await this.loadAndSendData();
      }
    });

    const htmlPath = path.join(context.extensionPath, 'media', 'workflows.html');
    const stylePath = this.panel.webview.asWebviewUri(vscode.Uri.file(path.join(context.extensionPath, 'media', 'styles.css')));
    let html = fs.readFileSync(htmlPath, 'utf-8');
    html = html.replace('stylesheet" href="styles.css', `stylesheet" href="${stylePath}`);
    this.panel.webview.html = html;
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

    WorkflowPanel.instance = new WorkflowPanel(panel, context);
  }

  private async loadAndSendData(): Promise<void> {
    try {
      this.records = await this.loadRecords();
      this.panel.webview.postMessage({
        type: 'setData',
        records: this.records
      });
    } catch (error) {
      console.error('[Workflows] Error:', error);
      vscode.window.showErrorMessage(`Failed to load workflows: ${error}`);
    }
  }

  private async loadRecords(): Promise<any[]> {
    const client = getRedisClient();
    const keyPattern = 'workflow:dev:*:*';
    const records: any[] = [];

    const keys = await client.keys(keyPattern);
    for (const key of keys.sort().reverse()) {
      const data = await client.hGetAll(key);
      const parts = key.split(':');
      if (parts.length >= 4) {
        const metadata = this.parseJson(data.metadata) || {};
        const stats = this.parseJson(data.stats) || {};
        const createdOn = metadata?.created_on || WorkflowPanel.NULL_PLACEHOLDER;
        records.push({
          key,
          persona: parts[2] || '',
          workflow_id: parts[3] || '',
          created_on: createdOn,
          created_at: createdOn,
          task: data.task || '',
          result: data.result || '',
          metadata,
          stats,
        });
      }
    }

    return records;
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
}

// ============================================================================
// System Prompts Panel
// ============================================================================

class SystemPromptsPanel {
  private static instance: SystemPromptsPanel | undefined;
  private records: any[] = [];

  private constructor(private readonly panel: vscode.WebviewPanel, context: vscode.ExtensionContext) {
    this.panel.onDidDispose(() => {
      SystemPromptsPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message.command === 'init') {
        await this.loadAndSendData();
      }
    });

    const htmlPath = path.join(context.extensionPath, 'media', 'system-prompts.html');
    const stylePath = this.panel.webview.asWebviewUri(vscode.Uri.file(path.join(context.extensionPath, 'media', 'styles.css')));
    let html = fs.readFileSync(htmlPath, 'utf-8');
    html = html.replace('stylesheet" href="styles.css', `stylesheet" href="${stylePath}`);
    this.panel.webview.html = html;
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

    SystemPromptsPanel.instance = new SystemPromptsPanel(panel, context);
  }

  private async loadAndSendData(): Promise<void> {
    try {
      this.records = await this.loadRecords();
      this.panel.webview.postMessage({
        type: 'setData',
        records: this.records
      });
    } catch (error) {
      console.error('[System Prompts] Error:', error);
      vscode.window.showErrorMessage(`Failed to load system prompts: ${error}`);
    }
  }

  private async loadRecords(): Promise<any[]> {
    const client = getRedisClient();
    const keyPattern = 'system-prompts:*';
    const records: any[] = [];

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
        remarks,
        metadata,
      });
    }

    return records;
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
}

// ============================================================================
// Prompt Optimization Panel
// ============================================================================

class PromptOptimizationPanel {
  private static instance: PromptOptimizationPanel | undefined;
  private records: any[] = [];

  private constructor(private readonly panel: vscode.WebviewPanel, context: vscode.ExtensionContext) {
    this.panel.onDidDispose(() => {
      PromptOptimizationPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      if (message.command === 'init') {
        await this.loadAndSendData();
      } else if (message.command === 'savePrompt') {
        await this.savePrompt(message.key, message.updatedPrompt);
      } else if (message.command === 'acceptPrompt') {
        await this.acceptPrompt(message.key, message.updatedPrompt);
      } else if (message.command === 'rejectPrompt') {
        await this.rejectPrompt(message.key, message.updatedPrompt);
      } else if (message.command === 'reloadPrompt') {
        await this.reloadPromptData(message.key);
      } else if (message.command === 'loadOptimizationReport') {
        await this.loadOptimizationReport(message.workflowId);
      }
    });

    const htmlPath = path.join(context.extensionPath, 'media', 'prompt-optimization.html');
    const stylePath = this.panel.webview.asWebviewUri(vscode.Uri.file(path.join(context.extensionPath, 'media', 'styles.css')));
    let html = fs.readFileSync(htmlPath, 'utf-8');
    html = html.replace('stylesheet" href="styles.css', `stylesheet" href="${stylePath}`);
    this.panel.webview.html = html;
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

    PromptOptimizationPanel.instance = new PromptOptimizationPanel(panel, context);
  }

  private async loadAndSendData(): Promise<void> {
    try {
      this.records = await this.loadRecords();
      this.panel.webview.postMessage({
        type: 'setData',
        records: this.records
      });
    } catch (error) {
      console.error('[Prompt Optimization] Error:', error);
      vscode.window.showErrorMessage(`Failed to load prompt optimization records: ${error}`);
    }
  }

  private async loadRecords(): Promise<any[]> {
    const client = getRedisClient();
    const records: any[] = [];

    // Try multiple key patterns for prompt optimization candidates
    const patterns = [
      'prompt-optimization:candidate-prompts:*',
      'prompt-optimization:*',
      '*candidate*:*:*',
    ];

    let allKeys: string[] = [];
    for (const pattern of patterns) {
      try {
        const keys = await client.keys(pattern);
        allKeys = allKeys.concat(keys);
      } catch (e) {
        console.log(`[Prompt Optimization] Pattern '${pattern}' failed:`, e);
      }
      if (allKeys.length > 0) break;
    }

    // Remove duplicates and filter for candidate prompt keys
    allKeys = [...new Set(allKeys)].filter(k => 
      k.includes('candidate') || k.includes('optimization')
    );

    console.log(`[Prompt Optimization] Found ${allKeys.length} keys:`, allKeys.slice(0, 3));

    for (const key of allKeys.sort().reverse()) {
      try {
        const data = await client.hGetAll(key);
        if (!data || Object.keys(data).length === 0) continue;

        // Parse key: prompt-optimization:candidate-prompts:persona:workflow_id
        const keyParts = key.split(':');
        const persona = data.persona || keyParts[2] || '';
        const workflow_id = data.workflow_id || keyParts[3] || '';

        console.log(`[Prompt Optimization] Processing key: ${key}`);
        console.log(`  - Extracted persona: ${persona}, workflow_id: ${workflow_id}`);
        console.log(`  - Data fields:`, Object.keys(data));

        // Load original prompt from system-prompts using original_prompt_ref first.
        // This ensures comparison uses the canonical system prompt source.
        const rawOriginalRef = data.original_prompt_ref || data.original_key || '';
        const systemPromptRef = this.extractSystemPromptRef(rawOriginalRef);
        const originalRef = systemPromptRef || rawOriginalRef;
        let originalPrompt = '';

        if (systemPromptRef) {
          try {
            const sysRefData = await client.hGetAll(systemPromptRef);
            if (sysRefData && Object.keys(sysRefData).length > 0) {
              originalPrompt = sysRefData.prompt || sysRefData.system_prompt || sysRefData.prompt_text || sysRefData.content || sysRefData.message || sysRefData.value || sysRefData.text || '';
              console.log(`[Prompt Optimization] ✓ Loaded original prompt from system prompt ref: ${systemPromptRef}`);
            } else {
              console.warn(`[Prompt Optimization] System prompt ref not found: ${systemPromptRef}`);
            }
          } catch (e) {
            console.warn(`[Prompt Optimization] Failed to fetch system prompt ref ${systemPromptRef}:`, e);
          }
        }

        // Fallback: if ref is present but not a system-prompts key, try direct lookup.
        if (!originalPrompt && rawOriginalRef && rawOriginalRef !== systemPromptRef) {
          try {
            const refData = await client.hGetAll(rawOriginalRef);
            if (refData && Object.keys(refData).length > 0) {
              originalPrompt = refData.prompt || refData.system_prompt || refData.prompt_text || refData.content || refData.message || refData.value || refData.text || refData.original_prompt || refData.updated_prompt || '';
              console.log(`[Prompt Optimization] Loaded original prompt from direct ref lookup: ${rawOriginalRef}`);
            }
          } catch (e) {
            console.warn(`[Prompt Optimization] Failed to fetch referenced original prompt ${rawOriginalRef}:`, e);
          }
        }

        // Fallback: locate system-prompts entry by persona when reference is unavailable.
        if (!originalPrompt && persona) {
          try {
            const sysPromptKeys = await client.keys('system-prompts:*');
            for (const sysKey of sysPromptKeys) {
              const sysData = await client.hGetAll(sysKey);
              const sysMetadata = this.parseJson(sysData.metadata) || {};
              if (sysMetadata.persona === persona) {
                originalPrompt = sysData.prompt || sysData.system_prompt || sysData.prompt_text || '';
                console.log(`[Prompt Optimization] ✓ Loaded original prompt from system-prompts by persona: ${persona} (${sysKey})`);
                break;
              }
            }
          } catch (e) {
            console.warn(`[Prompt Optimization] Failed to fetch system prompt for persona ${persona}:`, e);
          }
        }

        // Last resort to avoid blank UI if upstream data is incomplete.
        if (!originalPrompt) {
          originalPrompt = data.original_prompt || '';
        }


        records.push({
          key,
          persona,
          workflow_id,
          created_at: data.created_at || '',
          updated_at: data.updated_at || '',
          created_by: data.created_by || '',
          updated_by: data.updated_by || '',
          updated_prompt: data.updated_prompt || data.candidate_prompt || '',
          original_prompt: originalPrompt,
          original_prompt_ref: originalRef,
          optimization_report: null,
        });
      } catch (e) {
        console.error(`[Prompt Optimization] Error loading key ${key}:`, e);
      }
    }

    return records;
  }

  private async savePrompt(key: string, updatedPrompt: string): Promise<void> {
    try {
      const client = getRedisClient();
      const writeTime = new Date().toISOString();
      await client.hSet(key, {
        updated_prompt: updatedPrompt,
        updated_at: writeTime,
        updated_by: 'task-viewer-manual-edit',
      });
      vscode.window.showInformationMessage(`✓ Prompt saved to Redis: ${key.substring(0, 50)}...`);
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'save',
        success: true,
        message: `Saved candidate prompt: ${key}`,
      });
      await this.loadAndSendData();
    } catch (error) {
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'save',
        success: false,
        message: `Failed to save prompt: ${error}`,
      });
      vscode.window.showErrorMessage(`Failed to save prompt: ${error}`);
    }
  }

  private parseCandidateKey(key: string): { persona: string; workflowId: string } {
    const parts = String(key || '').split(':');
    return {
      persona: parts[2] || '',
      workflowId: parts[3] || '',
    };
  }

  private async acceptPrompt(key: string, updatedPrompt: string): Promise<void> {
    try {
      const client = getRedisClient();
      const { persona } = this.parseCandidateKey(key);
      if (!persona) {
        throw new Error(`Unable to parse persona from key: ${key}`);
      }

      const writeTime = new Date().toISOString();
      const compactTime = this.formatDateTimeCompact(new Date());
      const latestKey = `prompt-optimization:candidate-prompts:${persona}:latest`;
      const systemLatestKey = `system-prompts:${persona}:latest`;
      const current = await client.hGetAll(key);
      const originalPrompt = current.original_prompt || '';

      await client.hSet(key, {
        updated_prompt: updatedPrompt,
        updated_at: writeTime,
        updated_by: 'task-viewer-accept',
        decision: 'accepted',
        accepted_key: latestKey,
      });

      await client.hSet(latestKey, {
        persona,
        workflow_id: 'latest',
        created_at: writeTime,
        created_by: 'task-viewer-accept',
        updated_at: writeTime,
        updated_by: 'task-viewer-accept',
        original_prompt: originalPrompt,
        updated_prompt: updatedPrompt,
        source_key: key,
        decision: 'accepted',
      });

      const systemData = {
        prompt: updatedPrompt,
        metadata: JSON.stringify({
          persona,
          created_at: writeTime,
        }),
        remarks: JSON.stringify({
          created_by: 'prompt-optimizer + user',
          optimized_from: key,
        }),
        feedback: '',
      };

      // Get current latest to check if it differs
      const currentLatest = await client.hGetAll(systemLatestKey);
      const currentLatestPrompt = currentLatest.prompt || '';
      const hasChanged = currentLatestPrompt !== updatedPrompt;

      await client.hSet(systemLatestKey, systemData);

      // Only save to history if the prompt has changed
      if (hasChanged) {
        const systemHistoryKey = `system-prompts:${persona}:${compactTime}`;
        await client.hSet(systemHistoryKey, systemData);
      }

      vscode.window.showInformationMessage(`✓ Prompt saved to latest system prompt: ${systemLatestKey}`);
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'accept',
        success: true,
        message: `Saved to latest system prompt: ${systemLatestKey}`,
      });
      await this.loadAndSendData();
    } catch (error) {
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'accept',
        success: false,
        message: `Failed to accept prompt: ${error}`,
      });
      vscode.window.showErrorMessage(`Failed to accept prompt: ${error}`);
    }
  }

  private formatDateTimeCompact(date: Date): string {
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, '0');
    const day = String(date.getUTCDate()).padStart(2, '0');
    const hours = String(date.getUTCHours()).padStart(2, '0');
    const minutes = String(date.getUTCMinutes()).padStart(2, '0');
    const seconds = String(date.getUTCSeconds()).padStart(2, '0');
    return `${year}${month}${day}T${hours}${minutes}${seconds}Z`;
  }

  private async rejectPrompt(key: string, updatedPrompt: string): Promise<void> {
    try {
      const client = getRedisClient();
      const writeTime = new Date().toISOString();
      await client.hSet(key, {
        updated_prompt: updatedPrompt,
        updated_at: writeTime,
        updated_by: 'task-viewer-reject',
        decision: 'rejected',
      });
      vscode.window.showInformationMessage(`✗ Rejected candidate prompt: ${key}`);
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'reject',
        success: true,
        message: `Rejected candidate prompt: ${key}`,
      });
      await this.loadAndSendData();
    } catch (error) {
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'reject',
        success: false,
        message: `Failed to reject prompt: ${error}`,
      });
      vscode.window.showErrorMessage(`Failed to reject prompt: ${error}`);
    }
  }

  private async reloadPromptData(key: string): Promise<void> {
    try {
      const client = getRedisClient();
      const data = await client.hGetAll(key);
      if (!data || Object.keys(data).length === 0) {
        vscode.window.showWarningMessage(`Candidate prompt not found in Redis: ${key}`);
        return;
      }
      vscode.window.showInformationMessage('✓ Reloaded candidate from Redis');
      await this.loadAndSendData();
    } catch (error) {
      vscode.window.showErrorMessage(`Failed to reload prompt: ${error}`);
    }
  }

  private async loadOptimizationReport(workflowId: string): Promise<void> {
    try {
      const client = getRedisClient();
      const { report, wfKey, availableFields } = await this.fetchOptimizationReport(client, workflowId);
      this.panel.webview.postMessage({
        type: 'optimizationReport',
        workflowId,
        report,
        attemptedKey: wfKey,
        availableFields,
      });
    } catch (error) {
      console.warn(`[Prompt Optimization] Failed to load report for workflow ${workflowId}:`, error);
      this.panel.webview.postMessage({
        type: 'optimizationReport',
        workflowId,
        report: null,
      });
    }
  }

  private async fetchOptimizationReport(client: RedisClientType, workflowId: string): Promise<{report: any, wfKey: string, availableFields: string[]}> {
    const wfKey = `workflow:dev:prompt-optimizer:${workflowId}`;
    if (!workflowId) {
      return { report: null, wfKey, availableFields: [] };
    }

    const wfData = await client.hGetAll(wfKey);
    if (!wfData || Object.keys(wfData).length === 0) {
      console.warn(`[Prompt Optimization] No workflow hash found for ${wfKey}`);
      return { report: null, wfKey, availableFields: [] };
    }

    const availableFields = Object.keys(wfData || {});
    console.log(`[Prompt Optimization] Found workflow key ${wfKey} with fields:`, availableFields);

    const reportFields = ['result', 'report', 'optimization_report', 'report_data', 'optimization_data', 'data', 'payload', 'optimization'];
    for (const fieldName of reportFields) {
      const rawValue = wfData[fieldName];
      if (rawValue === undefined || rawValue === null || String(rawValue).trim() === '') {
        continue;
      }

      const parsed = this.parseJson(rawValue);
      if (parsed) {
        console.log(`[Prompt Optimization] ✓ Loaded optimization report from ${wfKey}.${fieldName}`);
        return { report: parsed, wfKey, availableFields };
      }

      if (typeof rawValue === 'string') {
        console.log(`[Prompt Optimization] ✓ Loaded raw optimization report text from ${wfKey}.${fieldName}`);
        return { report: rawValue, wfKey, availableFields };
      }
    }

    console.warn(`[Prompt Optimization] No report found in any field for ${wfKey}. Available fields:`, availableFields);
    return { report: null, wfKey, availableFields };
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

  private extractSystemPromptRef(rawRef: string): string {
    if (!rawRef) {
      return '';
    }

    const trimmed = String(rawRef).trim();
    if (trimmed.startsWith('system-prompts:')) {
      return trimmed;
    }

    const parsed = this.parseJson(trimmed);
    if (parsed && typeof parsed === 'object') {
      const nested = String(
        parsed.original_prompt_ref || parsed.reference || parsed.ref || parsed.key || ''
      ).trim();
      if (nested.startsWith('system-prompts:')) {
        return nested;
      }
    }

    const match = trimmed.match(/system-prompts:[A-Za-z0-9:_-]+/);
    return match ? match[0] : '';
  }
}

// Agent Management Panel is now in ./panels/agent-management.ts

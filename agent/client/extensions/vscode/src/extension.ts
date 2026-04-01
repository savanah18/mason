import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

type ChatMessage = { id: number; sender: 'user' | 'assistant'; text: string };

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8002';
const CHAT_VERSION = '0.4.2';
const CHAT_ENDPOINT = `${BACKEND_URL}/chat/send`;
const HEALTH_ENDPOINT = `${BACKEND_URL}/health`;
const CREATE_SESSION_ENDPOINT = `${BACKEND_URL}/session/create`;
const CLEAR_CHAT_ENDPOINT = `${BACKEND_URL}/chat/clear`;
const MAX_MESSAGES_IN_UI = 100;
const REQUEST_TIMEOUT_MS = (() => {
  const parsed = Number(process.env.AI_CHAT_REQUEST_TIMEOUT_MS ?? '3600000');
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 3600000;
})();
const HEALTH_CHECK_TIMEOUT_MS = 5000;

export function activate(context: vscode.ExtensionContext): void {
  try {
    console.log('[AI Chat] Activating extension');
    vscode.window.showInformationMessage('AI Chat is starting...');

    const startDisposable = vscode.commands.registerCommand('aiChat.start', () => {
      vscode.window.showInformationMessage('AI Chat Ready');
    });

    const chatDisposable = vscode.commands.registerCommand('aiChat.openChat', () => {
      ChatPanel.createOrShow(context);
    });

    context.subscriptions.push(startDisposable, chatDisposable);

    setTimeout(() => {
      try {
        ChatPanel.createOrShow(context);
      } catch (err) {
        console.error('[AI Chat] Failed to open chat panel:', err);
        vscode.window.showErrorMessage(`AI Chat Error: ${err}`);
      }
    }, 100);
  } catch (error) {
    console.error('[AI Chat] Activation error:', error);
    vscode.window.showErrorMessage(`AI Chat activation failed: ${error}`);
  }
}

export function deactivate(): void {
  ChatPanel.disposeInstance();
}

class ChatPanel {
  private static instance: ChatPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private webviewReady = false;
  private messages: ChatMessage[] = [
    {
      id: 1,
      sender: 'assistant',
      text: `Backend-powered chat connected to ${BACKEND_URL}.\n\nWhat can I help you with?`,
    },
  ];
  private nextId = 2;
  private serverStatus = 'Checking...';
  private backendReady = false;
  private isLoading = false;
  private sessionId = '';

  private constructor(private readonly context: vscode.ExtensionContext) {
    this.panel = vscode.window.createWebviewPanel('aiChat', 'AI Chat', vscode.ViewColumn.Beside, {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, 'media')],
    });

    this.panel.onDidDispose(() => this.dispose(), null, this.context.subscriptions);
    this.panel.webview.onDidReceiveMessage(msg => this.handleMessage(msg));
    this.panel.webview.html = this.renderHtml();

    this.initialize();
  }

  static createOrShow(context: vscode.ExtensionContext): void {
    if (ChatPanel.instance) {
      ChatPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }
    ChatPanel.instance = new ChatPanel(context);
  }

  static disposeInstance(): void {
    ChatPanel.instance?.dispose();
  }

  private dispose(): void {
    ChatPanel.instance = undefined;
  }

  private async initialize(): Promise<void> {
    await this.checkBackendHealth();
    if (this.backendReady) {
      await this.createSession();
    }
    this.pushState();
  }

  private fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs: number = HEALTH_CHECK_TIMEOUT_MS): Promise<Response> {
    return new Promise((resolve, reject) => {
      const timeoutId = setTimeout(() => reject(new Error(`Timeout after ${timeoutMs}ms`)), timeoutMs);
      fetch(url, options)
        .then(response => {
          clearTimeout(timeoutId);
          resolve(response);
        })
        .catch(error => {
          clearTimeout(timeoutId);
          reject(error);
        });
    });
  }

  private async checkBackendHealth(): Promise<void> {
    try {
      const response = await this.fetchWithTimeout(HEALTH_ENDPOINT, { method: 'GET' }, HEALTH_CHECK_TIMEOUT_MS);

      if (response.ok) {
        const data = (await response.json()) as { mcp_tools_loaded?: number; sessions_active?: number };
        this.backendReady = true;
        const mcpCount = data.mcp_tools_loaded ?? 0;
        const sessionCount = data.sessions_active ?? 0;
        this.serverStatus = `Ready | MCP: ${mcpCount} | Sessions: ${sessionCount}`;
      } else {
        this.serverStatus = `Error (${response.status})`;
        this.backendReady = false;
      }
    } catch (error) {
      this.serverStatus = `Cannot reach ${BACKEND_URL}`;
      this.backendReady = false;
      this.addMessage('assistant', 'Cannot connect to backend. Please ensure the server is running and accessible.');
    }
  }

  private async createSession(): Promise<void> {
    try {
      const response = await this.fetchWithTimeout(CREATE_SESSION_ENDPOINT, { method: 'POST' }, HEALTH_CHECK_TIMEOUT_MS);

      if (response.ok) {
        const data = (await response.json()) as { session_id?: string };
        this.sessionId = data.session_id ?? '';
        this.addMessage('assistant', `Session: ${this.sessionId.substring(0, 12)}...`);
      } else {
        throw new Error(`${response.status}`);
      }
    } catch (error) {
      this.addMessage('assistant', `Session error: ${error}`);
    }
  }

  private async handleMessage(message: { type?: string; text?: string; action?: string }): Promise<void> {
    if (message.action === 'webview-ready') {
      this.webviewReady = true;
      this.pushState();
      return;
    }

    if (message.action === 'webview-error' && message.text) {
      vscode.window.showErrorMessage(`AI Chat Webview: ${message.text}`);
      this.addMessage('assistant', `Webview error: ${message.text}`);
      this.pushState();
      return;
    }

    if (message.type === 'send' && message.text) {
      await this.sendMessage(message.text);
      return;
    }

    if (message.action === 'refresh-health') {
      await this.checkBackendHealth();
      if (!this.sessionId && this.backendReady) {
        await this.createSession();
      }
      this.pushState();
      return;
    }

    if (message.action === 'clear-chat') {
      await this.clearChat();
    }
  }

  private async sendMessage(userText: string): Promise<void> {
    const trimmed = userText.trim();
    if (!trimmed) return;

    this.messages.push({ id: this.nextId++, sender: 'user', text: trimmed });
    this.pushState();

    if (!this.backendReady) {
      this.addMessage('assistant', 'Backend not ready');
      this.pushState();
      return;
    }

    if (!this.sessionId) {
      this.addMessage('assistant', 'No session available');
      this.pushState();
      return;
    }

    this.isLoading = true;
    this.messages.push({ id: this.nextId++, sender: 'assistant', text: 'Processing...' });
    this.pushState();

    try {
      const startTime = Date.now();
      const response = await this.fetchWithTimeout(
        CHAT_ENDPOINT,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: trimmed, session_id: this.sessionId }),
        },
        REQUEST_TIMEOUT_MS,
      );

      if (!response.ok) {
        throw new Error(`${response.status}`);
      }

      const data = (await response.json()) as { 
        response?: string; 
        context_length?: number; 
        total_history?: number;
        message_count?: number;
        input_length?: number;
      };
      const time = ((Date.now() - startTime) / 1000).toFixed(2);
      const ctxInfo = `Latency: ${time}s | Context: ${data.context_length ?? 0} messages | Input size: ${data.input_length ?? 0} chars | History: ${data.total_history ?? 0}`;
      this.messages.pop();
      this.addMessage('assistant', `${data.response ?? ''}\n\n${ctxInfo}`);
    } catch (error) {
      this.messages.pop();
      this.addMessage('assistant', `Error: ${error}`);
    } finally {
      this.isLoading = false;
    }

    this.pushState();
  }

  private async clearChat(): Promise<void> {
    if (!this.sessionId) return;

    try {
      const response = await this.fetchWithTimeout(`${CLEAR_CHAT_ENDPOINT}/${this.sessionId}`, { method: 'POST' }, HEALTH_CHECK_TIMEOUT_MS);
      if (response.ok) {
        this.messages = [
          {
            id: this.nextId++,
            sender: 'assistant',
            text: 'Chat cleared.',
          },
        ];
      }
    } catch (error) {
      this.addMessage('assistant', `Clear failed: ${error}`);
    }
    this.pushState();
  }

  private addMessage(sender: 'user' | 'assistant', text: string): void {
    this.messages.push({ id: this.nextId++, sender, text });
  }

  private pushState(): void {
    this.panel.webview.postMessage({
      messages: this.messages.slice(-MAX_MESSAGES_IN_UI),
      status: this.serverStatus,
      isLoading: this.isLoading,
    });
  }

  private getMediaUri(fileName: string): string {
    const mediaUri = vscode.Uri.joinPath(this.context.extensionUri, 'media', fileName);
    return this.panel.webview.asWebviewUri(mediaUri).toString();
  }

  private getNonce(): string {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let nonce = '';
    for (let i = 0; i < 32; i += 1) {
      nonce += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return nonce;
  }

  private renderHtml(): string {
    const nonce = this.getNonce();
    const templatePath = path.join(this.context.extensionPath, 'media', 'chat.html');
    const template = fs.readFileSync(templatePath, 'utf8');
    const styleUri = this.getMediaUri('chat.css');
    const markedUri = this.getMediaUri('vendor/marked.umd.js');
    const scriptUri = this.getMediaUri('chat.js');
    const csp = [
      "default-src 'none'",
      `style-src ${this.panel.webview.cspSource}`,
      `script-src 'nonce-${nonce}'`,
      `connect-src ${this.panel.webview.cspSource}`,
    ].join('; ');

    return template
      .replace(/__CHAT_VERSION__/g, CHAT_VERSION)
      .replace(/__CSP__/g, csp)
      .replace(/__STYLE_URI__/g, styleUri)
      .replace(/__MARKED_URI__/g, markedUri)
      .replace(/__SCRIPT_URI__/g, scriptUri)
      .replace(/__NONCE__/g, nonce);
  }
}

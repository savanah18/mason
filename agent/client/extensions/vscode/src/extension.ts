import * as vscode from 'vscode';

type ChatMessage = { id: number; sender: 'user' | 'assistant'; text: string };

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8002';
const CHAT_VERSION = '0.4.0';
const CHAT_ENDPOINT = `${BACKEND_URL}/chat/send`;
const HEALTH_ENDPOINT = `${BACKEND_URL}/health`;
const CREATE_SESSION_ENDPOINT = `${BACKEND_URL}/session/create`;
const CLEAR_CHAT_ENDPOINT = `${BACKEND_URL}/chat/clear`;
const MAX_MESSAGES_IN_UI = 100;
const REQUEST_TIMEOUT_MS = 60000;
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
      this.addMessage('assistant', 'Cannot connect to backend. Start with: python agent/backend.py');
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
      const ctxInfo = `⏱️ ${time}s | Context: ${data.context_length ?? 0} msgs (${data.input_length ?? 0} chars) | History: ${data.total_history ?? 0}`;
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

  private renderHtml(): string {
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); display: flex; flex-direction: column; height: 100vh; }
    header { padding: 12px 16px; border-bottom: 1px solid var(--vscode-widget-border); }
    .title { font-weight: 600; }
    .status { font-size: 11px; color: var(--vscode-descriptionForeground); margin-top: 4px; }
    #messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
    .msg { padding: 10px 12px; border-radius: 6px; max-width: 85%; white-space: pre-wrap; word-wrap: break-word; }
    .assistant { background: var(--vscode-textBlockQuote-background); align-self: flex-start; }
    .user { background: var(--vscode-terminal-selectionBackground); align-self: flex-end; }
    footer { border-top: 1px solid var(--vscode-widget-border); padding: 12px 16px; display: flex; gap: 8px; }
    input { flex: 1; padding: 8px 12px; border: 1px solid var(--vscode-input-border); background: var(--vscode-input-background); color: var(--vscode-input-foreground); border-radius: 4px; }
    input:focus { outline: none; border-color: var(--vscode-focusBorder); }
    button { padding: 8px 16px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; border-radius: 4px; cursor: pointer; }
    button:hover { background: var(--vscode-button-hoverBackground); }
    button:disabled { opacity: 0.5; }
  </style>
</head>
<body>
  <header>
    <div class="title">AI Chat v${CHAT_VERSION}</div>
    <div class="status" id="status">Connecting...</div>
  </header>
  <main id="messages"></main>
  <footer>
    <input type="text" id="input" placeholder="Message..." />
    <button id="send">Send</button>
    <button id="clear">Clear</button>
    <button id="refresh">Refresh</button>
  </footer>

  <script>
    const vscode = acquireVsCodeApi();
    const msgs = document.getElementById('messages');
    const input = document.getElementById('input');
    const status = document.getElementById('status');
    const send = document.getElementById('send');
    const clear = document.getElementById('clear');
    const refresh = document.getElementById('refresh');

    window.addEventListener('message', e => {
      const { messages, status: s, isLoading } = e.data;
      if (s) status.textContent = s;
      send.disabled = isLoading;
      input.disabled = isLoading;
      msgs.innerHTML = '';
      (messages || []).forEach(msg => {
        const div = document.createElement('div');
        div.className = 'msg ' + msg.sender;
        div.textContent = msg.text;
        msgs.appendChild(div);
      });
      msgs.scrollTop = msgs.scrollHeight;
    });

    input.addEventListener('keypress', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send.click();
      }
    });

    send.addEventListener('click', () => {
      const text = input.value.trim();
      if (text) {
        vscode.postMessage({ type: 'send', text });
        input.value = '';
      }
    });

    clear.addEventListener('click', () => {
      vscode.postMessage({ action: 'clear-chat' });
    });

    refresh.addEventListener('click', () => {
      vscode.postMessage({ action: 'refresh-health' });
    });
  </script>
</body>
</html>`;
  }
}

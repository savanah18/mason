import * as vscode from 'vscode';
import { randomUUID } from 'crypto';

type ChatMessage = { id: number; sender: 'user' | 'assistant'; text: string };

// OpenAPI-compatible AI inference configuration
const MIDDLEWARE_URL = process.env.MIDDLEWARE_URL || 'http://localhost:8001';
const OPENAI_CHAT_ENDPOINT = `${MIDDLEWARE_URL}/v1/chat/completions`;
const HEALTH_ENDPOINT = `${MIDDLEWARE_URL}/health`;
const MODELS_ENDPOINT = `${MIDDLEWARE_URL}/v1/models`;
const MODEL_NAME = 'qwen3-tensorrtllm';
const MAX_MESSAGES_IN_UI = 100;
const MAX_TOKENS = 2048;
const TEMPERATURE = 0.7;

export function activate(context: vscode.ExtensionContext): void {
  try {
    console.log('[AI Chat] ✅ Extension activating...');
    
    // Show notification immediately to confirm extension is running
    vscode.window.showInformationMessage('🚀 AI Chat is starting...');
    
    const startDisposable = vscode.commands.registerCommand('aiChat.start', () => {
      console.log('[AI Chat] Start command executed');
      vscode.window.showInformationMessage('🚀 AI Chat Ready!');
    });

    const chatDisposable = vscode.commands.registerCommand('aiChat.openChat', () => {
      console.log('[AI Chat] Open chat command executed');
      ChatPanel.createOrShow(context);
    });

    context.subscriptions.push(startDisposable, chatDisposable);
    
    // Auto-open chat on startup
    console.log('[AI Chat] Opening chat panel automatically...');
    setTimeout(() => {
      try {
        ChatPanel.createOrShow(context);
        console.log('[AI Chat] ✅ Chat panel created successfully');
      } catch (err) {
        console.error('[AI Chat] ❌ Error creating chat panel:', err);
        vscode.window.showErrorMessage(`AI Chat Error: ${err}`);
      }
    }, 100);
  } catch (error) {
    console.error('[AI Chat] ❌ Activation error:', error);
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
      text: '🤖 AI Chat Assistant\n\nHello! I\'m an AI assistant powered by OpenAPI-compatible inference. I support:\n• Real-time text generation with customizable parameters\n• Fast inference with response timing\n• Persistent conversation context\n• Token usage statistics\n• Compatible with various AI models and backends\n\nWhat would you like to know or discuss?',
    },
  ];
  private nextId = 2;
  private serverStatus = 'Checking...';
  private modelLoaded = false;
  private isLoading = false;
  private sessionId: string = randomUUID();

  private constructor(private readonly context: vscode.ExtensionContext) {
    try {
      console.log('[AI Chat] Creating webview panel...');
      this.panel = vscode.window.createWebviewPanel(
        'aiChat',
        'AI Chat',
        vscode.ViewColumn.Beside,
        {
          enableScripts: true,
        },
      );
      console.log('[AI Chat] Webview panel created');

      this.panel.onDidDispose(() => this.dispose(), null, this.context.subscriptions);
      this.panel.webview.onDidReceiveMessage(msg => this.onMessage(msg));
      console.log('[AI Chat] Setting webview HTML...');
      this.panel.webview.html = this.renderHtml();
      console.log('[AI Chat] HTML set, sending initial state...');
      // Send initial state to webview immediately
      this.pushState();
      // Then check server health
      console.log('[AI Chat] Checking server health...');
      this.checkServerHealth();
      console.log('[AI Chat] ChatPanel constructor complete');
    } catch (err) {
      console.error('[AI Chat] Error in ChatPanel constructor:', err);
      throw err;
    }
  }

  static createOrShow(context: vscode.ExtensionContext): void {
    if (ChatPanel.instance) {
      ChatPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      ChatPanel.instance.pushState();
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

  private async checkServerHealth(): Promise<void> {
    try {
      console.log('[AI Chat] Checking health at:', HEALTH_ENDPOINT);
      // Check health endpoint
      const healthResponse = await fetch(HEALTH_ENDPOINT, {
        method: 'GET',
      });
      
      console.log('[AI Chat] Health response status:', healthResponse.status);
      
      if (healthResponse.ok) {
        // Try to parse JSON, but don't fail if it's not valid JSON
        let healthData: any = {};
        try {
          const contentType = healthResponse.headers.get('content-type');
          if (contentType?.includes('application/json')) {
            healthData = await healthResponse.json();
          }
        } catch (jsonError) {
          console.log('[AI Chat] Response body is not JSON, that\'s ok');
          // Response is 200 OK, even if body isn't JSON - server is running
        }
        
        this.modelLoaded = true;
        const tritonStatus = healthData?.triton_server === 'connected' ? 'connected' : (healthData?.triton_server || 'connected');
        this.serverStatus = `AI Server: Ready (${MIDDLEWARE_URL})`;
        console.log('[AI Chat] Server is healthy:', this.serverStatus);
      } else {
        console.error('[AI Chat] Health check returned non-200 status:', healthResponse.status);
        this.serverStatus = 'AI Server: Health check failed';
        this.modelLoaded = false;
      }
    } catch (error) {
      console.error('[AI Chat] Health check caught error:', error);
      this.serverStatus = `AI Server: Not reachable (${MIDDLEWARE_URL})`;
      this.modelLoaded = false;
    }
    this.pushState();
  }

  private async loadModel(): Promise<void> {
    // Check server health and available models
    await this.checkServerHealth();
    if (this.modelLoaded) {
      try {
        const modelsResponse = await fetch(MODELS_ENDPOINT);
        if (modelsResponse.ok) {
          const modelsData: any = await modelsResponse.json();
          const modelsList = modelsData?.data?.map((m: any) => m.id).join(', ') || MODEL_NAME;
          this.addMessage('assistant', `✓ AI Server ready at ${MIDDLEWARE_URL}\nAvailable models: ${modelsList}`);
        } else {
          this.addMessage('assistant', `✓ AI Server ready at ${MIDDLEWARE_URL}`);
        }
      } catch (error) {
        console.error('[AI Chat] Error loading models:', error);
        this.addMessage('assistant', `✓ AI Server ready at ${MIDDLEWARE_URL}`);
      }
    } else {
      this.addMessage('assistant', 'Error: AI Server not loaded. Please start the service first.');
    }
  }

  private async onMessage(message: { type: string; text?: string; action?: string }): Promise<void> {
    console.log('[AI Chat] Webview message received:', message);
    if (message.type === 'send' && message.text) {
      const userMsg: ChatMessage = {
        id: this.nextId++,
        sender: 'user',
        text: message.text.trim(),
      };
      if (!userMsg.text) {
        return;
      }
      console.log('[AI Chat] User message:', userMsg.text);
      this.messages.push(userMsg);
      this.pushState(); // Show user message immediately

      if (!this.modelLoaded) {
        this.addMessage('assistant', 'Error: AI Server not ready. Please start the service first.');
        this.pushState();
        return;
      }

      // Add loading message
      this.isLoading = true;
      const loadingMsg: ChatMessage = {
        id: this.nextId++,
        sender: 'assistant',
        text: '⏳ Processing...',
      };
      this.messages.push(loadingMsg);
      this.pushState();

      try {
        const startTime = Date.now();
        console.log('[AI Chat] Sending OpenAPI request:', userMsg.text);
        
        // Build conversation history in OpenAPI format
        const conversationHistory = this.messages
          .filter(msg => msg.sender !== 'assistant' || !msg.text.includes('⏳ Processing'))
          .slice(-10) // Keep last 10 messages for context
          .map(msg => ({
            role: msg.sender === 'user' ? 'user' : 'assistant',
            content: msg.text.replace(/\n\n⏱️ Total: [\d.]+s.*$/, '') // Remove timing info including token stats
          }));
        
        // Build OpenAPI compatible request
        const openaiRequest = {
          model: MODEL_NAME,
          messages: conversationHistory,
          max_tokens: MAX_TOKENS,
          temperature: TEMPERATURE,
          top_p: 0.9,
          stream: false
        };

        const response = await fetch(OPENAI_CHAT_ENDPOINT, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(openaiRequest),
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`AI server error (${response.status}): ${errorText}`);
        }

        const responseData = (await response.json()) as any;
        console.log('[AI Chat] Received OpenAPI response:', responseData);
        
        // Extract response text from OpenAPI format
        const responseText = responseData.choices?.[0]?.message?.content || 'No response received from model';
        const totalTime = (Date.now() - startTime) / 1000;
        const usage = responseData.usage;
        
        console.log('[AI Chat] Response time:', totalTime, 'Usage:', usage);
        
        const displayText = `${responseText}\n\n⏱️ Total: ${totalTime.toFixed(2)}s | Tokens: ${usage?.total_tokens || 'N/A'} (prompt: ${usage?.prompt_tokens || 'N/A'}, completion: ${usage?.completion_tokens || 'N/A'})`;
        
        // Remove loading message and add real response
        this.messages.pop();
        this.addMessage('assistant', displayText);
      } catch (error) {
        console.error('[AI Chat] Error:', error);
        this.messages.pop();
        this.addMessage('assistant', `Error: ${error}`);
      } finally {
        this.isLoading = false;
      }
      this.pushState();
    } else if (message.action === 'load-model') {
      await this.loadModel();
      this.pushState();
    } else if (message.action === 'clear-chat') {
      // Reset session ID when clearing chat to start fresh
      this.sessionId = randomUUID();
      console.log(`[AI Chat] Chat cleared, new session: ${this.sessionId}`);
      this.messages = [
        {
          id: this.nextId++,
          sender: 'assistant',
          text: 'Chat cleared. New session started.',
        },
      ];
      this.pushState();
    } else if (message.action === 'check-health') {
      console.log('[AI Chat] Checking server health...');
      await this.checkServerHealth();
      console.log('[AI Chat] Health check complete:', this.serverStatus);
      this.addMessage('assistant', `Status: ${this.serverStatus}`);
      this.pushState();
    }
  }

  private addMessage(sender: 'user' | 'assistant', text: string): void {
    this.messages.push({
      id: this.nextId++,
      sender,
      text,
    });
  }

  private renderHtml(): string {
    const nonce = getNonce();
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Chat</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; display: flex; flex-direction: column; height: 100vh; background: #0b1220; color: #e2e8f0; }
    header { padding: 12px 16px; background: #0f172a; border-bottom: 1px solid #1f2937; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
    .header-title { font-weight: 600; font-size: 14px; }
    .header-status { font-size: 12px; color: #94a3b8; }
    .controls { display: flex; gap: 6px; }
    #messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
    .bubble { max-width: 85%; padding: 10px 12px; border-radius: 10px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
    .assistant { background: #1e293b; align-self: flex-start; }
    .user { background: #1c3d5a; align-self: flex-end; }
    form { display: flex; flex-direction: column; gap: 8px; padding: 12px 16px; border-top: 1px solid #1f2937; background: #0f172a; }
    textarea { resize: none; padding: 10px; border-radius: 6px; border: 1px solid #334155; background: #111827; color: #e2e8f0; font-family: inherit; font-size: 14px; }
    textarea:focus { outline: none; border-color: #2563eb; }
    .button-group { display: flex; gap: 8px; }
    button { padding: 8px 12px; border: none; border-radius: 6px; background: #2563eb; color: #f8fafc; font-weight: 600; cursor: pointer; font-size: 13px; flex: 1; }
    button:hover { background: #1d4ed8; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    button.secondary { background: #334155; }
    button.secondary:hover { background: #475569; }
  </style>
</head>
<body>
  <header>
    <div>
      <div class="header-title">🤖 AI Chat</div>
      <div class="header-status" id="status-text">Checking server...</div>
    </div>
    <div class="controls">
      <button id="health-btn" class="secondary" style="flex: 0 1 auto;">Check Status</button>
    </div>
  </header>
  <main id="messages" aria-live="polite"></main>
  <form id="chat-form">
    <textarea id="chat-input" placeholder="Type a message and press Send..." style="min-height: 60px; max-height: 120px;"></textarea>
    <div class="button-group">
      <button type="submit" id="send-btn">Send</button>
      <button type="button" id="clear-btn" class="secondary">Clear</button>
    </div>
  </form>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const messagesEl = document.getElementById('messages');
    const formEl = document.getElementById('chat-form');
    const inputEl = document.getElementById('chat-input');
    const statusEl = document.getElementById('status-text');
    const sendBtn = document.getElementById('send-btn');
    const clearBtn = document.getElementById('clear-btn');
    const healthBtn = document.getElementById('health-btn');
    
    console.log('Button elements:', { sendBtn, clearBtn, healthBtn });

    const render = (messages) => {
      messagesEl.innerHTML = '';
      messages.forEach(msg => {
        const div = document.createElement('div');
        div.className = 'bubble ' + msg.sender;
        div.textContent = msg.text;
        messagesEl.appendChild(div);
      });
      messagesEl.scrollTop = messagesEl.scrollHeight;
    };

    window.addEventListener('message', event => {
      const { type, messages, serverStatus, modelLoaded, isLoading } = event.data;
      if (type === 'state') {
        render(messages ?? []);
        if (serverStatus !== undefined) {
          statusEl.textContent = serverStatus;
        }
        if (modelLoaded !== undefined || isLoading !== undefined) {
          sendBtn.disabled = !modelLoaded || isLoading;
          inputEl.disabled = !modelLoaded || isLoading;
        }
      }
    });

    formEl.addEventListener('submit', event => {
      event.preventDefault();
      const text = inputEl.value.trim();
      if (!text) return;
      inputEl.value = '';
      vscode.postMessage({ type: 'send', text });
    });

    healthBtn.addEventListener('click', () => {
      console.log('Health button clicked');
      vscode.postMessage({ action: 'check-health' });
    });

    clearBtn.addEventListener('click', () => {
      console.log('Clear button clicked');
      vscode.postMessage({ action: 'clear-chat' });
    });
  </script>
</body>
</html>`;
  }

  private pushState(): void {
    // Limit messages to prevent memory issues
    const messagesToSend = this.messages.slice(-MAX_MESSAGES_IN_UI);
    
    this.panel.webview.postMessage({
      type: 'state',
      messages: messagesToSend,
      serverStatus: this.serverStatus,
      modelLoaded: this.modelLoaded,
      isLoading: this.isLoading,
    });
  }
}

function getNonce(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < 16; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

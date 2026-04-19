import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import type { Consumer, SASLOptions } from 'kafkajs';

type ChatMessage = { id: number; sender: 'user' | 'assistant'; text: string };

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8002';
const CHAT_VERSION = '0.5.0';
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

type NotificationLevel = 'info' | 'warning' | 'error';

type NotificationAction = {
  label: string;
  ack?: boolean;
  value?: string;
};

type KafkaNotificationMessage = {
  id?: string;
  level?: string;
  title?: string;
  message?: string;
  actions?: Array<string | NotificationAction>;
  requires_ack?: boolean;
};

type NormalizedNotification = {
  id: string;
  level: NotificationLevel;
  title?: string;
  message: string;
  actions: NotificationAction[];
  requiresAck: boolean;
};

let kafkaSubscriber: KafkaNotificationSubscriber | undefined;

export function activate(context: vscode.ExtensionContext): void {
  try {
    console.log('[AI Chat] Activating extension');
    vscode.window.showInformationMessage('AI Chat is starting...');

    kafkaSubscriber = new KafkaNotificationSubscriber();
    void kafkaSubscriber.start().catch(error => {
      console.error('[AI Chat] Kafka subscriber startup failed:', error);
    });

    const startDisposable = vscode.commands.registerCommand('aiChat.start', () => {
      vscode.window.showInformationMessage('AI Chat Ready');
    });

    const chatDisposable = vscode.commands.registerCommand('aiChat.openChat', () => {
      ChatPanel.createOrShow(context);
    });

    const openChatAliasDisposable = vscode.commands.registerCommand('ai.openchat', () => {
      ChatPanel.createOrShow(context);
    });

    const openChatAliasDisposable2 = vscode.commands.registerCommand('aichat.openChat', () => {
      ChatPanel.createOrShow(context);
    });

    const kafkaStatusDisposable = vscode.commands.registerCommand('aiChat.notificationsStatus', () => {
      const status = kafkaSubscriber?.getStatus() ?? {
        enabled: false,
        running: false,
        brokers: [],
        topic: '',
        groupId: '',
        phase: 'subscriber-not-initialized',
        receivedCount: 0,
        lastMessageAt: null,
        lastError: 'subscriber-not-initialized',
      };

      const summary = [
        `enabled=${status.enabled}`,
        `running=${status.running}`,
        `phase=${status.phase || '-'}`,
        `brokers=${status.brokers.join(',') || '-'}`,
        `topic=${status.topic || '-'}`,
        `groupId=${status.groupId || '-'}`,
        `received=${status.receivedCount}`,
        `lastMessageAt=${status.lastMessageAt ?? '-'}`,
        `lastError=${status.lastError ?? '-'}`,
      ].join(' | ');

      vscode.window.showInformationMessage(`AI Chat Kafka status: ${summary}`);
      console.log('[AI Chat] Kafka status:', status);
    });

    const kafkaRestartDisposable = vscode.commands.registerCommand('aiChat.notificationsRestart', async () => {
      if (!kafkaSubscriber) {
        kafkaSubscriber = new KafkaNotificationSubscriber();
      }

      try {
        await kafkaSubscriber.stop();
      } catch {
        // Ignore stop errors; start will report status.
      }

      await kafkaSubscriber.start().catch(error => {
        console.error('[AI Chat] Kafka subscriber restart failed:', error);
      });

      const status = kafkaSubscriber.getStatus();
      const summary = [
        `enabled=${status.enabled}`,
        `running=${status.running}`,
        `phase=${status.phase || '-'}`,
        `brokers=${status.brokers.join(',') || '-'}`,
        `topic=${status.topic || '-'}`,
        `groupId=${status.groupId || '-'}`,
        `received=${status.receivedCount}`,
        `lastError=${status.lastError ?? '-'}`,
      ].join(' | ');

      vscode.window.showInformationMessage(`AI Chat Kafka restarted: ${summary}`);
      console.log('[AI Chat] Kafka restart status:', status);
    });

    const testNotificationDisposable = vscode.commands.registerCommand('aiChat.testNotification', async () => {
      const message = `AI Chat local test notification @ ${new Date().toLocaleTimeString()}`;
      await vscode.window.showInformationMessage(message);
      // ChatPanel.pushExternalNotification(message);
    });

    context.subscriptions.push(
      startDisposable,
      chatDisposable,
      openChatAliasDisposable,
      openChatAliasDisposable2,
      kafkaStatusDisposable,
      kafkaRestartDisposable,
      testNotificationDisposable,
    );

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
  void kafkaSubscriber?.stop();
  kafkaSubscriber = undefined;
  ChatPanel.disposeInstance();
}

class KafkaNotificationSubscriber {
  private consumer: Consumer | undefined;
  private running = false;
  private enabled = false;
  private brokers: string[] = [];
  private topic = '';
  private groupId = '';
  private phase = 'idle';
  private receivedCount = 0;
  private lastMessageAt: string | null = null;
  private lastError: string | null = null;
  private readonly seenIds = new Set<string>();
  private static readonly MAX_SEEN_IDS = 500;

  async start(): Promise<void> {
    this.phase = 'starting';
    const config = vscode.workspace.getConfiguration('aiChat.notifications');
    const enabled = config.get<boolean>('enabled', true);
    this.enabled = enabled;
    this.lastError = null;
    if (!enabled) {
      this.lastError = 'disabled-by-settings';
      this.phase = 'disabled';
      console.log('[AI Chat] Kafka notifications are disabled');
      vscode.window.showInformationMessage('AI Chat notifications are disabled in settings');
      return;
    }

    const brokers = this.parseCsv(config.get<string>('kafkaBrokers', 'localhost:9092'));
    const topic = config.get<string>('topic', 'ai.notifications')?.trim() ?? 'ai.notifications';
    const clientId = config.get<string>('clientId', 'ai-chat-vscode')?.trim() ?? 'ai-chat-vscode';
    const groupId = config.get<string>('groupId', 'ai-chat-vscode')?.trim() ?? 'ai-chat-vscode';
    this.brokers = brokers;
    this.topic = topic;
    this.groupId = groupId;
    const fromBeginning = config.get<boolean>('fromBeginning', false);
    const ssl = config.get<boolean>('ssl', false);
    this.phase = 'config-loaded';

    if (!brokers.length) {
      this.lastError = 'no-brokers-configured';
      this.phase = 'invalid-config';
      vscode.window.showWarningMessage('AI Chat notifications enabled but no Kafka brokers are configured');
      return;
    }

    const sasl = this.buildSaslFromConfig(config);
    let kafkaModule: typeof import('kafkajs');
    try {
      kafkaModule = await import('kafkajs');
    } catch (error) {
      this.lastError = `kafkajs-load-failed: ${String(error)}`;
      this.phase = 'module-load-failed';
      console.warn('[AI Chat] Kafka notifications disabled because kafkajs could not be loaded:', error);
      vscode.window.showWarningMessage('AI Chat notifications failed: kafkajs module could not be loaded');
      return;
    }
    this.phase = 'module-loaded';

    const kafka = new kafkaModule.Kafka({
      clientId,
      brokers,
      ssl,
      sasl,
      logLevel: kafkaModule.logLevel.NOTHING,
    });

    this.consumer = kafka.consumer({ groupId });
    this.phase = 'consumer-created';
    try {
      this.phase = 'connecting';
      await this.consumer.connect();
      this.phase = 'connected';
      await this.consumer.subscribe({ topic, fromBeginning });
      this.phase = 'subscribed';
    } catch (error) {
      console.error('[AI Chat] Kafka connect/subscribe failed:', error);
      this.lastError = String(error);
      this.phase = 'connect-or-subscribe-failed';
      vscode.window.showWarningMessage(`AI Chat notifications failed to connect to Kafka (${brokers.join(', ')})`);
      throw error;
    }

    this.running = true;
    this.lastError = null;
    this.phase = 'running';
    console.log(`[AI Chat] Kafka notifications listener started on topic '${topic}'`);
    vscode.window.showInformationMessage(`AI Chat notifications listening on ${topic}`);

    await this.consumer.run({
      eachMessage: async ({ message }) => {
        if (!this.running) {
          return;
        }

        const raw = message.value?.toString('utf-8');
        if (!raw) {
          return;
        }

        let parsed: unknown;
        try {
          parsed = JSON.parse(raw);
        } catch {
          console.warn('[AI Chat] Ignoring non-JSON Kafka notification payload');
          return;
        }

        const notification = this.normalizeNotification(parsed);
        if (!notification || this.isDuplicate(notification.id)) {
          return;
        }

        this.receivedCount += 1;
        this.lastMessageAt = new Date().toISOString();
        this.lastError = null;
        console.log(`[AI Chat] Kafka message received id=${notification.id} level=${notification.level}`);

        await this.showNotification(notification);
      },
    });
  }

  async stop(): Promise<void> {
    this.running = false;
    this.phase = 'stopping';
    if (!this.consumer) {
      this.phase = 'stopped';
      return;
    }

    try {
      await this.consumer.disconnect();
      console.log('[AI Chat] Kafka notifications listener stopped');
    } catch (error) {
      console.error('[AI Chat] Failed to stop Kafka listener:', error);
      this.lastError = String(error);
    } finally {
      this.consumer = undefined;
      this.phase = 'stopped';
    }
  }

  getStatus(): {
    enabled: boolean;
    running: boolean;
    brokers: string[];
    topic: string;
    groupId: string;
    phase: string;
    receivedCount: number;
    lastMessageAt: string | null;
    lastError: string | null;
  } {
    return {
      enabled: this.enabled,
      running: this.running,
      brokers: this.brokers,
      topic: this.topic,
      groupId: this.groupId,
      phase: this.phase,
      receivedCount: this.receivedCount,
      lastMessageAt: this.lastMessageAt,
      lastError: this.lastError,
    };
  }

  private parseCsv(value: string): string[] {
    return value
      .split(',')
      .map(item => item.trim())
      .filter(Boolean);
  }

  private buildSaslFromConfig(config: vscode.WorkspaceConfiguration): SASLOptions | undefined {
    const username = config.get<string>('username', '').trim();
    const password = config.get<string>('password', '').trim();
    const mechanism = config.get<string>('saslMechanism', 'plain').trim();

    if (!username || !password) {
      return undefined;
    }

    if (mechanism !== 'plain' && mechanism !== 'scram-sha-256' && mechanism !== 'scram-sha-512') {
      console.warn(`[AI Chat] Unsupported SASL mechanism '${mechanism}', defaulting to plain`);
      return { mechanism: 'plain', username, password };
    }

    return { mechanism, username, password } as SASLOptions;
  }

  private normalizeNotification(payload: unknown): NormalizedNotification | null {
    if (!payload || typeof payload !== 'object') {
      return null;
    }

    const candidate = payload as { notification?: KafkaNotificationMessage } & KafkaNotificationMessage;
    const source = (candidate.notification && typeof candidate.notification === 'object')
      ? candidate.notification
      : candidate;

    if (typeof source.message !== 'string' || !source.message.trim()) {
      return null;
    }

    const id = typeof source.id === 'string' && source.id.trim()
      ? source.id.trim()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

    const level = this.normalizeLevel(source.level);
    const actions = this.normalizeActions(source.actions);
    const requiresAck = Boolean(source.requires_ack);

    if (requiresAck && !actions.some(action => action.ack)) {
      actions.push({ label: 'Acknowledge', ack: true, value: 'ack' });
    }

    return {
      id,
      level,
      title: typeof source.title === 'string' ? source.title : undefined,
      message: source.message.trim(),
      actions,
      requiresAck,
    };
  }

  private normalizeLevel(level: string | undefined): NotificationLevel {
    const normalized = (level ?? 'info').toLowerCase();
    if (normalized === 'error') {
      return 'error';
    }
    if (normalized === 'warning' || normalized === 'warn') {
      return 'warning';
    }
    return 'info';
  }

  private normalizeActions(actions: Array<string | NotificationAction> | undefined): NotificationAction[] {
    if (!Array.isArray(actions)) {
      return [];
    }

    const normalized: NotificationAction[] = [];
    for (const action of actions) {
      if (typeof action === 'string' && action.trim()) {
        const lowered = action.trim().toLowerCase();
        normalized.push({
          label: action.trim(),
          ack: lowered === 'ack' || lowered === 'acknowledge',
          value: lowered,
        });
        continue;
      }

      if (
        action &&
        typeof action === 'object' &&
        typeof action.label === 'string' &&
        action.label.trim()
      ) {
        const label = action.label.trim();
        normalized.push({
          label,
          ack: Boolean(action.ack),
          value: typeof action.value === 'string' ? action.value : label.toLowerCase(),
        });
      }
    }

    return normalized;
  }

  private isDuplicate(id: string): boolean {
    if (this.seenIds.has(id)) {
      return true;
    }

    this.seenIds.add(id);
    if (this.seenIds.size > KafkaNotificationSubscriber.MAX_SEEN_IDS) {
      const [first] = this.seenIds;
      if (first) {
        this.seenIds.delete(first);
      }
    }
    return false;
  }

  private async showNotification(notification: NormalizedNotification): Promise<void> {
    const toast = notification.title
      ? `${notification.title}: ${notification.message}`
      : notification.message;

    const links = this.extractHyperlinks(notification.message);
    const linkActions = links.map((url, index) => ({
      label: index === 0 ? 'Open Link' : `Open Link ${index + 1}`,
      url,
    }));
    const actionLabels = [
      ...notification.actions.map(action => action.label),
      ...linkActions.map(action => action.label),
    ];

    let selected: string | undefined;
    if (notification.level === 'error') {
      selected = await vscode.window.showErrorMessage(toast, ...actionLabels);
    } else if (notification.level === 'warning') {
      selected = await vscode.window.showWarningMessage(toast, ...actionLabels);
    } else {
      selected = await vscode.window.showInformationMessage(toast, ...actionLabels);
    }

    ChatPanel.pushExternalNotification(toast);

    if (!selected) {
      return;
    }

    const selectedLinkAction = linkActions.find(action => action.label === selected);
    if (selectedLinkAction) {
      await vscode.env.openExternal(vscode.Uri.parse(selectedLinkAction.url));
      return;
    }

    const chosen = notification.actions.find(action => action.label === selected);
    if (!chosen) {
      return;
    }

    if (notification.requiresAck || chosen.ack) {
      await this.sendAck(notification.id, chosen.value ?? selected.toLowerCase());
    }
  }

  private extractHyperlinks(text: string): string[] {
    const matches = text.match(/(?:https?:\/\/|www\.)[^\s<>'"`]+/gi) ?? [];
    const normalized = matches.map(raw => {
      const trimmed = raw.replace(/[),.;!?]+$/g, '');
      return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
    });
    return [...new Set(normalized)];
  }

  private async sendAck(notificationId: string, action: string): Promise<void> {
    const ackEndpoint = vscode.workspace
      .getConfiguration('aiChat.notifications')
      .get<string>('ackEndpoint', '')
      .trim();

    if (!ackEndpoint) {
      return;
    }

    try {
      const response = await fetch(ackEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          notification_id: notificationId,
          action,
          seen_at: new Date().toISOString(),
        }),
      });

      if (!response.ok) {
        console.warn(`[AI Chat] Notification ack failed: HTTP ${response.status}`);
      }
    } catch (error) {
      console.warn('[AI Chat] Notification ack request failed:', error);
    }
  }
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

  static pushExternalNotification(text: string): void {
    if (!ChatPanel.instance) {
      return;
    }
    ChatPanel.instance.addMessage('assistant', `[Notification] ${text}`);
    ChatPanel.instance.pushState();
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

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as http from 'http';
import * as https from 'https';
import { URL } from 'url';
import { parse as parseYaml } from 'yaml';
import { BasePanel } from './base';

export class AgentManagementPanel extends BasePanel {
  private static instance: AgentManagementPanel | undefined;

  private constructor(
    panel: vscode.WebviewPanel,
    extensionRoot: string,
    private readonly redisClient: any
  ) {
    super(panel, extensionRoot);

    this.panel.onDidDispose(() => {
      AgentManagementPanel.instance = undefined;
    });

    this.panel.webview.onDidReceiveMessage(async (message) => {
      console.log('[Agent Management] Received command:', message.command);
      try {
        if (message.command === 'init') {
          await this.loadAndSendData();
        } else if (message.command === 'registerAgent') {
          await this.registerAgent(message.persona, message.files || {});
        } else if (message.command === 'deleteAgent') {
          await this.deleteAgent(message.persona);
        } else if (message.command === 'instantiateAgent') {
          await this.instantiateAgent(message.persona);
        } else if (message.command === 'terminateAgent') {
          await this.terminateAgent(message.persona);
        } else if (message.command === 'restartAgent') {
          await this.restartAgent(message.persona);
        }
      } catch (error) {
        console.error('[Agent Management] Error handling command:', message.command, error);
      }
    });

    this.panel.webview.html = this.loadHtmlFile('agent-management.html');
  }

  static async createOrShow(context: vscode.ExtensionContext, redisClient: any): Promise<void> {
    if (AgentManagementPanel.instance) {
      AgentManagementPanel.instance.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'taskViewerAgentManagement',
      'Agent Management',
      vscode.ViewColumn.Beside,
      { enableScripts: true }
    );

    AgentManagementPanel.instance = new AgentManagementPanel(panel, context.extensionPath, redisClient);
  }

  private async loadAndSendData(): Promise<void> {
    try {
      this.records = await this.loadAgentRecords();
      this.sendData(this.records);
    } catch (error) {
      console.error('[Agent Management] Error:', error);
      vscode.window.showErrorMessage(`Failed to load agent records: ${error}`);
    }
  }

  private async loadAgentRecords(): Promise<any[]> {
    // First, try to read from the authoritative registry in Redis (agent-records:...)
    try {
      if (this.redisClient) {
        const agentKeys = await this.redisClient.keys('agent-records:agent:*:latest');
        if (agentKeys && agentKeys.length > 0) {
          return await this.loadFromRedis(agentKeys);
        }
      }
    } catch (e) {
      console.warn('[Agent Management] Redis lookup failed, falling back to filesystem:', e);
    }

    // Fallback: scan local persona directories on disk
    return await this.loadFromFilesystem();
  }

  private async loadFromRedis(agentKeys: string[]): Promise<any[]> {
    const personas = agentKeys
      .map((k: string) => String(k).split(':')[2] || '')
      .filter(Boolean)
      .sort();

    const records: any[] = [];
    for (const persona of personas) {
      const sections = ['agent', 'goal', 'sensors', 'actuators'];
      const sectionRecords: any = {};
      let anyFound = false;
      let createdAt = '';
      let registryMetadata: any = {};

      for (const section of sections) {
        const key = `agent-records:${section}:${persona}:latest`;
        try {
          const data = await this.redisClient.hGetAll(key) as Record<string, string>;
          if (data && Object.keys(data).length > 0) {
            anyFound = true;
            const payload = this.parseJson(data.payload, {});
            const metadata = this.parseJson(data.metadata, {});
            const registry_meta = this.parseJson(data.registry_metadata, {});

            sectionRecords[section] = {
              schema: data.schema || section,
              persona,
              payload,
              created_at: data.created_at || '',
              metadata,
              registry_metadata: registry_meta,
              // propagate status fields (written by backend registry)
              status: data.status || '',
              status_updated_at: data.status_updated_at || '',
            };

            if (!createdAt && data.created_at) createdAt = data.created_at;
            if (!registryMetadata || Object.keys(registryMetadata).length === 0) registryMetadata = registry_meta || {};
          } else {
            sectionRecords[section] = null;
          }
        } catch (e) {
          console.warn(`[Agent Management] Failed to read ${key}:`, e);
          sectionRecords[section] = null;
        }
      }

      if (!anyFound) continue;

      records.push({
        persona,
        // prefer authoritative status from agent section when available
        status: (sectionRecords.agent && sectionRecords.agent.status) || 'registered',
        status_updated_at: (sectionRecords.agent && sectionRecords.agent.status_updated_at) || '',
        updated_at: createdAt || '',
        configured_files: {
          agent: !!sectionRecords.agent,
          goal: !!sectionRecords.goal,
          sensors: !!sectionRecords.sensors,
          actuators: !!sectionRecords.actuators,
        },
        general_details: (sectionRecords.agent && sectionRecords.agent.payload) || {},
        goals: (sectionRecords.goal && sectionRecords.goal.payload) || {},
        sensors: (sectionRecords.sensors && sectionRecords.sensors.payload) || {},
        actuators: (sectionRecords.actuators && sectionRecords.actuators.payload) || {},
        metadata: registryMetadata || {},
        created_at: createdAt || '',
        records: sectionRecords,
      });
    }

    return records;
  }

  private async loadFromFilesystem(): Promise<any[]> {
    const personasRoot = path.resolve(this.extensionRoot, '../../agent/personas');
    if (!fs.existsSync(personasRoot)) {
      return [];
    }

    const personas = fs
      .readdirSync(personasRoot, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .sort();

    const records: any[] = [];
    for (const persona of personas) {
      const personaDir = path.join(personasRoot, persona);
      const fileMap = {
        agent: path.join(personaDir, 'agent.yaml'),
        goal: path.join(personaDir, 'goal.yaml'),
        sensors: path.join(personaDir, 'sensors.yaml'),
        actuators: path.join(personaDir, 'actuators.yaml'),
      };

      const configuredFiles = Object.fromEntries(
        Object.entries(fileMap).map(([name, filePath]) => [name, fs.existsSync(filePath)])
      );

      const allRequiredPresent = Object.values(configuredFiles).every(Boolean);
      const agentYaml = this.readYamlFileIfExists(fileMap.agent);
      const goalYaml = this.readYamlFileIfExists(fileMap.goal);
      const sensorsYaml = this.readYamlFileIfExists(fileMap.sensors);
      const actuatorsYaml = this.readYamlFileIfExists(fileMap.actuators);

      records.push({
        persona,
        status: allRequiredPresent ? 'registered' : 'incomplete',
        updated_at: this.latestFileMtime(Object.values(fileMap)),
        configured_files: configuredFiles,
        general_details: {
          apiVersion: agentYaml?.apiVersion || '',
          kind: agentYaml?.kind || '',
          name: agentYaml?.metadata?.name || '',
          labels: agentYaml?.metadata?.labels || {},
          spec: agentYaml?.spec || {},
        },
        goals: goalYaml || {},
        sensors: sensorsYaml || {},
        actuators: actuatorsYaml || {},
      });
    }

    return records;
  }

  private readYamlFileIfExists(filePath: string): any {
    try {
      if (!fs.existsSync(filePath)) {
        return null;
      }
      const content = fs.readFileSync(filePath, 'utf-8');
      return parseYaml(content);
    } catch {
      return null;
    }
  }

  private latestFileMtime(filePaths: string[]): string {
    let latest = 0;
    for (const filePath of filePaths) {
      if (!fs.existsSync(filePath)) {
        continue;
      }
      const mtimeMs = fs.statSync(filePath).mtimeMs;
      if (mtimeMs > latest) {
        latest = mtimeMs;
      }
    }
    return latest > 0 ? new Date(latest).toISOString() : '';
  }

  private validateRegistrationPayload(
    persona: string,
    files: Record<string, { name?: string; content?: string }>
  ): { valid: boolean; warnings: string[]; parsed: Record<string, any> } {
    const warnings: string[] = [];
    const parsed: Record<string, any> = {};

    if (!persona || !String(persona).trim()) {
      warnings.push('Persona is required.');
    }

    const required = ['agent', 'goal', 'sensors', 'actuators'];
    for (const key of required) {
      const fileObj = files[key];
      const name = String(fileObj?.name || '').trim();
      const content = String(fileObj?.content || '');
      if (!name || !content.trim()) {
        warnings.push(`Missing required file: ${key}.yaml or ${key}.json`);
        continue;
      }

      try {
        if (name.toLowerCase().endsWith('.json')) {
          parsed[key] = JSON.parse(content);
        } else {
          parsed[key] = parseYaml(content);
        }
      } catch (error) {
        warnings.push(`Failed to parse ${name}: ${error}`);
      }
    }

    if (parsed.agent && !parsed.agent?.spec?.goal) {
      warnings.push('agent file is misconfigured: missing spec.goal.');
    }

    return {
      valid: warnings.length === 0,
      warnings,
      parsed,
    };
  }

  private async registerAgent(persona: string, files: Record<string, { name?: string; content?: string }>): Promise<void> {
    try {
      const validation = this.validateRegistrationPayload(persona, files);
      this.panel.webview.postMessage({
        type: 'registrationValidation',
        persona,
        valid: validation.valid,
        warnings: validation.warnings,
      });

      if (!validation.valid) {
        return;
      }

      const registrationPayload = {
        persona,
        agent: validation.parsed.agent,
        goal: validation.parsed.goal,
        sensors: validation.parsed.sensors,
        actuators: validation.parsed.actuators,
        metadata: {},
      };

      await this.postToBackend('/api/agents/register', 'POST', registrationPayload);

      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'register',
        success: true,
        message: `Registered agent for persona: ${persona}`,
      });

      await this.loadAndSendData();
    } catch (error) {
      console.error('[Agent Management] Register error:', error);
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'register',
        success: false,
        message: `Failed to register agent: ${error}`,
      });
    }
  }

  private async deleteAgent(persona: string): Promise<void> {
    const normalizedPersona = String(persona || '').trim();
    if (!normalizedPersona) {
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'delete',
        success: false,
        message: 'Delete failed: persona is required',
      });
      return;
    }

    try {
      console.log('[Agent Management] Deleting persona:', normalizedPersona);
      await this.postToBackend(`/api/agents/${encodeURIComponent(normalizedPersona)}`, 'DELETE', null);

      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'delete',
        success: true,
        message: `Deleted agent records for persona: ${normalizedPersona}`,
      });

      await this.loadAndSendData();
    } catch (error) {
      console.error('[Agent Management] Delete error:', error);
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'delete',
        success: false,
        message: `Delete failed: ${error}`,
      });
    }
  }

  private async postToBackend(path: string, method: string, payload: any): Promise<void> {
    const cfg = vscode.workspace.getConfiguration('taskViewer.agentManager');
    const backendBase = String(cfg.get('backendUrl') || 'http://localhost:8010').replace(/\/+$/, '');
    const url = new URL(path, backendBase);
    const body = payload ? JSON.stringify(payload) : undefined;

    return new Promise<void>((resolve, reject) => {
      const isHttps = url.protocol === 'https:';
      const lib = isHttps ? https : http;
      const opts: any = {
        method,
        headers: {},
      };

      if (body) {
        opts.headers['Content-Type'] = 'application/json';
        opts.headers['Content-Length'] = Buffer.byteLength(body);
      }

      const req = lib.request(url.toString(), opts, (res: any) => {
        let resp = '';
        res.on('data', (chunk: any) => {
          resp += chunk;
        });
        res.on('end', () => {
          if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
            resolve();
          } else {
            reject(new Error(`HTTP ${res.statusCode}: ${resp}`));
          }
        });
      });

      req.on('error', (err: any) => reject(err));
      if (body) {
        req.write(body);
      }
      req.end();
    });
  }

  private async instantiateAgent(persona: string): Promise<void> {
    const normalizedPersona = String(persona || '').trim();
    if (!normalizedPersona) {
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'instantiate',
        success: false,
        message: 'Instantiate failed: persona is required',
      });
      return;
    }

    try {
      console.log('[Agent Management] Instantiating persona:', normalizedPersona);
      const payload = { force_recreate: true, dry_run: false };
      await this.postToBackend(
        `/api/agents/${encodeURIComponent(normalizedPersona)}/instantiate`,
        'POST',
        payload
      );

      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'instantiate',
        success: true,
        message: `Instantiated agent for persona: ${normalizedPersona}`,
      });

      await this.loadAndSendData();
    } catch (error) {
      console.error('[Agent Management] Instantiate error:', error);
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'instantiate',
        success: false,
        message: `Instantiate failed: ${error}`,
      });
    }
  }

  private async terminateAgent(persona: string): Promise<void> {
    const normalizedPersona = String(persona || '').trim();
    if (!normalizedPersona) {
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'terminate',
        success: false,
        message: 'Terminate failed: persona is required',
      });
      return;
    }

    try {
      console.log('[Agent Management] Terminating persona:', normalizedPersona);
      await this.postToBackend(
        `/api/agents/${encodeURIComponent(normalizedPersona)}/terminate`,
        'POST',
        {}
      );

      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'terminate',
        success: true,
        message: `Terminated agent for persona: ${normalizedPersona}`,
      });

      await this.loadAndSendData();
    } catch (error) {
      console.error('[Agent Management] Terminate error:', error);
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'terminate',
        success: false,
        message: `Terminate failed: ${error}`,
      });
    }
  }

  private async restartAgent(persona: string): Promise<void> {
    const normalizedPersona = String(persona || '').trim();
    if (!normalizedPersona) {
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'restart',
        success: false,
        message: 'Restart failed: persona is required',
      });
      return;
    }

    try {
      console.log('[Agent Management] Restarting persona:', normalizedPersona);
      const payload = { force_recreate: true, dry_run: false };
      await this.postToBackend(
        `/api/agents/${encodeURIComponent(normalizedPersona)}/restart`,
        'POST',
        payload
      );

      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'restart',
        success: true,
        message: `Restarted agent for persona: ${normalizedPersona}`,
      });

      await this.loadAndSendData();
    } catch (error) {
      console.error('[Agent Management] Restart error:', error);
      this.panel.webview.postMessage({
        type: 'actionResult',
        action: 'restart',
        success: false,
        message: `Restart failed: ${error}`,
      });
    }
  }
}

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

/**
 * Base class for all webview panels with shared UI loading logic
 */
export abstract class BasePanel {
  protected records: any[] = [];

  protected constructor(protected readonly panel: vscode.WebviewPanel, protected readonly extensionRoot: string) {}

  /**
   * Load HTML from media folder and inject stylesheet path
   */
  protected loadHtmlFile(htmlFileName: string): string {
    const htmlPath = path.join(this.extensionRoot, 'media', htmlFileName);
    const stylePath = this.panel.webview.asWebviewUri(
      vscode.Uri.file(path.join(this.extensionRoot, 'media', 'styles.css'))
    );
    let html = fs.readFileSync(htmlPath, 'utf-8');
    html = html.replace('stylesheet" href="styles.css', `stylesheet" href="${stylePath}`);
    return html;
  }

  /**
   * Parse JSON safely, returning default on error
   */
  protected parseJson(val: any, defaultValue: any = null): any {
    if (typeof val === 'string') {
      try {
        return JSON.parse(val);
      } catch {
        return defaultValue;
      }
    }
    return val;
  }

  /**
   * Format date as compact timestamp: YYYYMMDDTHHMMSSz
   */
  protected formatDateTimeCompact(date: Date): string {
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, '0');
    const day = String(date.getUTCDate()).padStart(2, '0');
    const hours = String(date.getUTCHours()).padStart(2, '0');
    const minutes = String(date.getUTCMinutes()).padStart(2, '0');
    const seconds = String(date.getUTCSeconds()).padStart(2, '0');
    return `${year}${month}${day}T${hours}${minutes}${seconds}Z`;
  }

  /**
   * Send data message to webview
   */
  protected sendData(data: any): void {
    this.panel.webview.postMessage({
      type: 'setData',
      records: data,
    });
  }

  /**
   * Send action result message to webview
   */
  protected sendActionResult(action: string, success: boolean, message: string): void {
    this.panel.webview.postMessage({
      type: 'actionResult',
      action,
      success,
      message,
    });
  }
}

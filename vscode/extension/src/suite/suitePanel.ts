import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

export const SUITE_SELECTION_KEY = 'unitTestRunner.suiteSelection';

interface SuiteActionMessage {
  type: 'suiteAction';
  kind: 'register' | 'runSelected' | 'runTag' | 'runAllGreen' | 'openSuite' | 'openReport' | 'toggleEntry';
  entryId?: string;
  checked?: boolean;
}

export interface SuiteEntryView {
  entryId: string;
  enabled: boolean;
  selected: boolean;
  tags: string[];
  functionName: string;
  source: string;
  workspace: string;
  status: string;
}

export class SuitePanelProvider implements vscode.WebviewViewProvider {
  static readonly viewType = 'unitTestRunner.suite';

  private view?: vscode.WebviewView;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly suiteManifestPath: () => string,
  ) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.onDidReceiveMessage((message: SuiteActionMessage) => {
      void this.handleMessage(message);
    });
    this.refresh();
  }

  refresh(): void {
    if (!this.view) {
      return;
    }
    const suitePath = this.suiteManifestPath();
    const selected = new Set(this.context.workspaceState.get<string[]>(SUITE_SELECTION_KEY) ?? []);
    const entries = readSuiteEntries(suitePath, selected);
    this.view.webview.html = renderSuiteHtml(this.view.webview, suitePath, entries);
  }

  private async handleMessage(message: SuiteActionMessage): Promise<void> {
    if (message.kind === 'toggleEntry' && message.entryId) {
      const selected = new Set(this.context.workspaceState.get<string[]>(SUITE_SELECTION_KEY) ?? []);
      if (message.checked) {
        selected.add(message.entryId);
      } else {
        selected.delete(message.entryId);
      }
      await this.context.workspaceState.update(SUITE_SELECTION_KEY, Array.from(selected));
      this.refresh();
      return;
    }
    const commandMap = {
      register: 'unitTestRunner.registerCurrentFunctionInSuite',
      runSelected: 'unitTestRunner.runSelectedSuiteTests',
      runTag: 'unitTestRunner.runSuiteByTag',
      runAllGreen: 'unitTestRunner.runAllSuiteTestsRequireGreen',
      openSuite: 'unitTestRunner.openSuite',
      openReport: 'unitTestRunner.openSuiteRunReport',
    };
    const commandId = commandMap[message.kind as keyof typeof commandMap];
    await vscode.commands.executeCommand(commandId);
    this.refresh();
  }
}

export function readSelectedSuiteEntryIds(context: vscode.ExtensionContext): string[] {
  return context.workspaceState.get<string[]>(SUITE_SELECTION_KEY) ?? [];
}

function readSuiteEntries(suitePath: string, selected: Set<string>): SuiteEntryView[] {
  if (!suitePath || !fs.existsSync(suitePath)) {
    return [];
  }
  try {
    const payload = JSON.parse(fs.readFileSync(suitePath, 'utf-8')) as { entries?: Array<Record<string, unknown>> };
    return (payload.entries ?? []).map((entry) => {
      const functionPayload = objectValue(entry.function);
      const entryId = stringValue(entry.entry_id);
      const workspace = stringValue(entry.workspace);
      return {
        entryId,
        enabled: entry.enabled !== false,
        selected: selected.has(entryId),
        tags: arrayValue(entry.tags),
        functionName: stringValue(functionPayload.name),
        source: stringValue(functionPayload.source),
        workspace,
        status: readExecutionStatus(workspace),
      };
    });
  } catch {
    return [];
  }
}

function readExecutionStatus(workspace: string): string {
  if (!workspace) {
    return 'unknown';
  }
  const reportPath = path.join(workspace, 'reports', 'test_execution_report.json');
  if (!fs.existsSync(reportPath)) {
    return 'not_run';
  }
  try {
    const payload = JSON.parse(fs.readFileSync(reportPath, 'utf-8')) as { function?: { status?: unknown } };
    return typeof payload.function?.status === 'string' ? payload.function.status : 'unknown';
  } catch {
    return 'unknown';
  }
}

function renderSuiteHtml(webview: vscode.Webview, suitePath: string, entries: SuiteEntryView[]): string {
  const nonce = createNonce();
  return `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style nonce="${nonce}">
    body { color: var(--vscode-foreground); background: var(--vscode-sideBar-background); font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); margin: 0; padding: 12px; }
    .path { color: var(--vscode-descriptionForeground); overflow-wrap: anywhere; margin-bottom: 10px; }
    .actions { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
    button { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); border: 1px solid transparent; border-radius: 2px; min-height: 28px; padding: 4px 8px; text-align: left; cursor: pointer; }
    button.primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
    button.danger { border-color: var(--vscode-inputValidation-warningBorder); }
    .entry { border-left: 3px solid var(--vscode-editorGroup-border); margin: 0 0 8px 0; padding: 8px 0 8px 10px; }
    .entry.disabled { opacity: 0.55; }
    .title { align-items: center; display: flex; gap: 8px; font-weight: 700; }
    .meta { color: var(--vscode-descriptionForeground); margin-top: 4px; overflow-wrap: anywhere; }
    .empty { color: var(--vscode-descriptionForeground); }
  </style>
</head>
<body>
  <div class="path">${escapeHtml(suitePath || 'suite manifest未設定')}</div>
  <div class="actions">
    <button class="primary" data-kind="register">現在関数を登録</button>
    <button data-kind="runSelected">選択を実行</button>
    <button data-kind="runTag">タグ指定で実行</button>
    <button class="danger" data-kind="runAllGreen">全件GREEN確認</button>
    <button data-kind="openSuite">manifestを開く</button>
    <button data-kind="openReport">実行レポートを開く</button>
  </div>
  ${entries.length === 0 ? '<p class="empty">登録済み関数はありません。</p>' : entries.map(renderEntry).join('')}
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    document.querySelectorAll('button[data-kind]').forEach((button) => {
      button.addEventListener('click', () => vscode.postMessage({ type: 'suiteAction', kind: button.dataset.kind }));
    });
    document.querySelectorAll('input[data-entry-id]').forEach((input) => {
      input.addEventListener('change', () => vscode.postMessage({ type: 'suiteAction', kind: 'toggleEntry', entryId: input.dataset.entryId, checked: input.checked }));
    });
  </script>
</body>
</html>`;
}

function renderEntry(entry: SuiteEntryView): string {
  const tags = entry.tags.join(', ');
  return `<section class="entry ${entry.enabled ? '' : 'disabled'}">
  <label class="title"><input type="checkbox" data-entry-id="${escapeAttribute(entry.entryId)}" ${entry.selected ? 'checked' : ''}>${escapeHtml(entry.functionName || entry.entryId)}</label>
  <div class="meta">${escapeHtml(entry.source)} / ${escapeHtml(tags)}</div>
  <div class="meta">status: ${escapeHtml(entry.status)}</div>
</section>`;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function arrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttribute(value: string): string {
  return escapeHtml(value);
}

function createNonce(): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let nonce = '';
  for (let index = 0; index < 32; index += 1) {
    nonce += alphabet.charAt(Math.floor(Math.random() * alphabet.length));
  }
  return nonce;
}

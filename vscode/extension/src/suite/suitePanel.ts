import * as vscode from 'vscode';

import { readSuiteViewModel, SuiteEntryView, SuiteViewModel, SUITE_SELECTION_KEY } from './suiteViewModel';

interface SuiteActionMessage {
  type?: 'suiteAction';
  kind: 'register' | 'runSelected' | 'runTag' | 'runAllGreen' | 'openSuite' | 'openManifest' | 'openReport' | 'toggleEntry';
  entryId?: string;
  checked?: boolean;
  label?: string;
}

export class SuitePanelProvider implements vscode.WebviewViewProvider {
  static readonly viewType = 'unitTestRunner.suite';

  private view?: vscode.WebviewView;
  private runningLabel?: string;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly suiteManifestPath: () => string,
    private readonly lastError: () => string | undefined,
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
    const model = readSuiteViewModel(suitePath, selected, this.lastError());
    this.view.webview.html = renderSuiteHtml(this.view.webview, model, this.runningLabel);
  }

  private async handleMessage(message: SuiteActionMessage): Promise<void> {
    if (message.kind === 'toggleEntry') {
      if (this.runningLabel) {
        return;
      }
      if (!message.entryId) {
        return;
      }
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
    if (this.runningLabel) {
      void vscode.window.showInformationMessage(`UnitTestRunner: ${this.runningLabel}を実行中です。完了するまでお待ちください。`);
      return;
    }
    const commandMap = {
      register: 'unitTestRunner.registerCurrentFunctionInSuite',
      runSelected: 'unitTestRunner.runSelectedSuiteTests',
      runTag: 'unitTestRunner.runSuiteByTag',
      runAllGreen: 'unitTestRunner.runAllSuiteTestsRequireGreen',
      openSuite: 'unitTestRunner.openSuite',
      openManifest: 'unitTestRunner.openSuiteManifest',
      openReport: 'unitTestRunner.openSuiteRunReport',
    };
    const commandId = commandMap[message.kind as keyof typeof commandMap];
    if (!commandId) {
      return;
    }
    this.runningLabel = message.label || suiteActionLabel(message.kind);
    this.refresh();
    try {
      await vscode.commands.executeCommand(commandId);
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      void vscode.window.showErrorMessage(`UnitTestRunner: ${messageText}`);
    } finally {
      this.runningLabel = undefined;
      this.refresh();
    }
  }
}

export function readSelectedSuiteEntryIds(context: vscode.ExtensionContext): string[] {
  return context.workspaceState.get<string[]>(SUITE_SELECTION_KEY) ?? [];
}

function renderSuiteHtml(webview: vscode.Webview, model: SuiteViewModel, runningLabel?: string): string {
  const nonce = createNonce();
  const summary = model.reportExists
    ? `<div class="summary">GREEN ${model.summary.green} / Not GREEN ${model.summary.notGreen} / Total ${model.summary.total}</div>`
    : '<div class="summary muted">実行結果はまだありません。</div>';
  const error = model.lastError ? `<div class="error">${escapeHtml(model.lastError)}</div>` : '';
  const running = runningLabel ? `<div class="busy" role="status">実行中: ${escapeHtml(runningLabel)}<br><span>処理が完了するまでボタンと選択は無効です。</span></div>` : '';
  return `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style nonce="${nonce}">
    body { color: var(--vscode-foreground); background: var(--vscode-sideBar-background); font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); margin: 0; padding: 12px; }
    .path { color: var(--vscode-descriptionForeground); overflow-wrap: anywhere; margin-bottom: 10px; }
    .summary { border-bottom: 1px solid var(--vscode-editorGroup-border); margin-bottom: 10px; padding-bottom: 8px; }
    .muted { color: var(--vscode-descriptionForeground); }
    .error { border: 1px solid var(--vscode-inputValidation-errorBorder); background: var(--vscode-inputValidation-errorBackground); color: var(--vscode-inputValidation-errorForeground); margin: 8px 0; padding: 8px; overflow-wrap: anywhere; }
    .busy { border: 1px solid var(--vscode-focusBorder); background: var(--vscode-editorWidget-background); color: var(--vscode-foreground); font-weight: 700; margin: 8px 0; padding: 8px; overflow-wrap: anywhere; }
    .busy span { color: var(--vscode-descriptionForeground); font-weight: 400; }
    .actions { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
    button { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); border: 1px solid transparent; border-radius: 2px; min-height: 28px; padding: 4px 8px; text-align: left; cursor: pointer; }
    button.primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
    button.danger { border-color: var(--vscode-inputValidation-warningBorder); }
    button:disabled, input:disabled { cursor: wait; opacity: 0.65; }
    .entry { border-left: 3px solid var(--vscode-editorGroup-border); margin: 0 0 8px 0; padding: 8px 0 8px 10px; }
    .entry.disabled { opacity: 0.55; }
    .entry.green { border-left-color: var(--vscode-testing-iconPassed); }
    .entry.not-green { border-left-color: var(--vscode-testing-iconFailed); }
    .title { align-items: center; display: flex; gap: 8px; font-weight: 700; }
    .meta { color: var(--vscode-descriptionForeground); margin-top: 4px; overflow-wrap: anywhere; }
    .status { font-weight: 700; }
    .empty { color: var(--vscode-descriptionForeground); }
  </style>
</head>
<body>
  <div class="path">${escapeHtml(model.suitePath || 'suite manifest未設定')}</div>
  ${summary}
  ${error}
  ${running}
  <div class="actions">
    <button class="primary" data-kind="register">現在関数を登録</button>
    <button data-kind="openSuite">広い一覧を開く</button>
    <button data-kind="runSelected">選択を実行</button>
    <button data-kind="runTag">タグ指定で実行</button>
    <button class="danger" data-kind="runAllGreen">全件GREEN確認</button>
    <button data-kind="openManifest">manifestを開く</button>
    <button data-kind="openReport">実行レポートを開く</button>
  </div>
  ${model.entries.length === 0 ? '<p class="empty">登録済み関数はありません。</p>' : model.entries.map(renderEntry).join('')}
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const initialRunningLabel = ${JSON.stringify(runningLabel ?? '')};
    function disableControls(activeButton, label) {
      const runningText = label || '処理';
      document.querySelectorAll('button, input').forEach((control) => {
        control.disabled = true;
        control.setAttribute('aria-disabled', 'true');
      });
      if (activeButton) {
        activeButton.textContent = '実行中: ' + runningText;
      }
    }
    if (initialRunningLabel) {
      disableControls(null, initialRunningLabel);
    }
    document.querySelectorAll('button[data-kind]').forEach((button) => {
      button.addEventListener('click', () => {
        const label = button.textContent || '処理';
        disableControls(button, label);
        vscode.postMessage({ type: 'suiteAction', kind: button.dataset.kind, label });
      });
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
  const statusClass = entry.greenStatus === 'green' ? 'green' : entry.greenStatus === 'not_green' ? 'not-green' : '';
  const green = entry.greenStatus === 'green' ? 'GREEN' : entry.greenStatus === 'not_green' ? 'Not GREEN' : '未実行';
  return `<section class="entry ${entry.enabled ? '' : 'disabled'} ${statusClass}">
  <label class="title"><input type="checkbox" data-entry-id="${escapeAttribute(entry.entryId)}" ${entry.selected ? 'checked' : ''}>${escapeHtml(entry.functionName || entry.entryId)}</label>
  <div class="meta">${escapeHtml(entry.source)} / ${escapeHtml(tags)}</div>
  <div class="meta"><span class="status">${escapeHtml(green)}</span> / ${escapeHtml(entry.lastRunStatus)}</div>
</section>`;
}

function suiteActionLabel(kind: SuiteActionMessage['kind']): string {
  const labels: Record<SuiteActionMessage['kind'], string> = {
    register: '現在関数を登録',
    runSelected: '選択を実行',
    runTag: 'タグ指定で実行',
    runAllGreen: '全件GREEN確認',
    openSuite: '広い一覧を開く',
    openManifest: 'manifestを開く',
    openReport: '実行レポートを開く',
    toggleEntry: '選択を更新',
  };
  return labels[kind];
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

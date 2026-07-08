import * as vscode from 'vscode';

import { readSuiteViewModel, SuiteEntryView, SuiteViewModel, SUITE_SELECTION_KEY } from './suiteViewModel';

interface SuiteDashboardMessage {
  kind: 'register' | 'runSelected' | 'runTag' | 'runAllGreen' | 'openManifest' | 'openReport' | 'toggleEntry';
  entryId?: string;
  checked?: boolean;
  label?: string;
}

type SuiteDashboardCommandKind = Exclude<SuiteDashboardMessage['kind'], 'toggleEntry'>;

export class SuiteDashboardPanel {
  static readonly viewType = 'unitTestRunner.suiteDashboard';

  private panel?: vscode.WebviewPanel;
  private runningLabel?: string;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly suiteManifestPath: () => string,
    private readonly lastError: () => string | undefined,
  ) {}

  open(): void {
    if (this.panel) {
      this.panel.reveal(vscode.ViewColumn.Active);
      this.refresh();
      return;
    }
    this.panel = vscode.window.createWebviewPanel(
      SuiteDashboardPanel.viewType,
      'UnitTestRunner スイート',
      vscode.ViewColumn.Active,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    this.panel.onDidDispose(() => {
      this.panel = undefined;
    }, undefined, this.context.subscriptions);
    this.panel.webview.onDidReceiveMessage((message: SuiteDashboardMessage) => {
      void this.handleMessage(message);
    });
    this.refresh();
  }

  refresh(): void {
    if (!this.panel) {
      return;
    }
    const selected = new Set(this.context.workspaceState.get<string[]>(SUITE_SELECTION_KEY) ?? []);
    const model = readSuiteViewModel(this.suiteManifestPath(), selected, this.lastError());
    this.panel.webview.html = renderDashboardHtml(this.panel.webview, model, this.runningLabel);
  }

  private async handleMessage(message: SuiteDashboardMessage): Promise<void> {
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
    const commandMap: Record<SuiteDashboardCommandKind, string> = {
      register: 'unitTestRunner.registerCurrentFunctionInSuite',
      runSelected: 'unitTestRunner.runSelectedSuiteTests',
      runTag: 'unitTestRunner.runSuiteByTag',
      runAllGreen: 'unitTestRunner.runAllSuiteTestsRequireGreen',
      openManifest: 'unitTestRunner.openSuiteManifest',
      openReport: 'unitTestRunner.openSuiteRunReport',
    };
    const commandId = commandMap[message.kind as SuiteDashboardCommandKind];
    this.runningLabel = message.label || suiteDashboardActionLabel(message.kind);
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

function renderDashboardHtml(webview: vscode.Webview, model: SuiteViewModel, runningLabel?: string): string {
  const nonce = createNonce();
  const reportState = model.reportExists ? escapeHtml(model.lastRunStatus) : '実行結果なし';
  const error = model.lastError ? `<div class="error">直近エラー: ${escapeHtml(model.lastError)}</div>` : '';
  const running = runningLabel ? `<div class="busy" role="status">実行中: ${escapeHtml(runningLabel)}<br><span>処理が完了するまでボタンと選択は無効です。</span></div>` : '';
  return `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style nonce="${nonce}">
    body {
      background: var(--vscode-editor-background);
      color: var(--vscode-editor-foreground);
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      margin: 0;
      padding: 16px 18px;
    }
    header {
      border-bottom: 1px solid var(--vscode-editorGroup-border);
      margin-bottom: 14px;
      padding-bottom: 12px;
    }
    h1 {
      font-size: 18px;
      font-weight: 600;
      margin: 0 0 6px 0;
    }
    .path, .muted {
      color: var(--vscode-descriptionForeground);
      overflow-wrap: anywhere;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(5, minmax(86px, max-content));
      gap: 8px;
      margin: 12px 0;
    }
    .metric {
      border: 1px solid var(--vscode-editorGroup-border);
      padding: 7px 10px;
    }
    .metric span {
      color: var(--vscode-descriptionForeground);
      display: block;
      font-size: 11px;
      margin-bottom: 3px;
    }
    .metric strong {
      font-size: 16px;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    button {
      background: var(--vscode-button-secondaryBackground);
      color: var(--vscode-button-secondaryForeground);
      border: 1px solid transparent;
      border-radius: 2px;
      min-height: 28px;
      padding: 4px 10px;
      cursor: pointer;
    }
    button.primary {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
    }
    button.danger {
      border-color: var(--vscode-inputValidation-warningBorder);
    }
    button:disabled, input:disabled {
      cursor: wait;
      opacity: 0.65;
    }
    .error {
      border: 1px solid var(--vscode-inputValidation-errorBorder);
      background: var(--vscode-inputValidation-errorBackground);
      color: var(--vscode-inputValidation-errorForeground);
      margin: 10px 0;
      padding: 8px;
      overflow-wrap: anywhere;
    }
    .busy {
      border: 1px solid var(--vscode-focusBorder);
      background: var(--vscode-editorWidget-background);
      color: var(--vscode-foreground);
      font-weight: 700;
      margin: 10px 0;
      padding: 8px;
      overflow-wrap: anywhere;
    }
    .busy span {
      color: var(--vscode-descriptionForeground);
      font-weight: 400;
    }
    .table-wrap {
      overflow: auto;
      border: 1px solid var(--vscode-editorGroup-border);
    }
    table {
      border-collapse: collapse;
      min-width: 1180px;
      width: 100%;
    }
    th, td {
      border-bottom: 1px solid var(--vscode-editorGroup-border);
      padding: 7px 9px;
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }
    th {
      background: var(--vscode-sideBarSectionHeader-background, var(--vscode-editor-background));
      color: var(--vscode-descriptionForeground);
      font-weight: 600;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    td.wrap {
      max-width: 320px;
      overflow-wrap: anywhere;
      white-space: normal;
    }
    .green {
      color: var(--vscode-testing-iconPassed);
      font-weight: 700;
    }
    .not-green {
      color: var(--vscode-testing-iconFailed);
      font-weight: 700;
    }
    .disabled {
      opacity: 0.55;
    }
    .empty {
      color: var(--vscode-descriptionForeground);
      padding: 20px;
    }
  </style>
</head>
<body>
  <header>
    <h1>スイート</h1>
    <div class="path">${escapeHtml(model.suitePath || 'suite manifest未設定')}</div>
    <div class="muted">直近レポート: ${escapeHtml(model.reportPath)} / ${reportState}</div>
    ${error}
    ${running}
    <div class="summary">
      ${renderMetric('Total', model.summary.total)}
      ${renderMetric('GREEN', model.summary.green)}
      ${renderMetric('Not GREEN', model.summary.notGreen)}
      ${renderMetric('Executed', model.summary.executed)}
      ${renderMetric('Failed', model.summary.failed)}
    </div>
    <div class="actions">
      <button class="primary" data-kind="register">現在関数を登録</button>
      <button data-kind="runSelected">選択を実行</button>
      <button data-kind="runTag">タグ指定で実行</button>
      <button class="danger" data-kind="runAllGreen">全件GREEN確認</button>
      <button data-kind="openReport">実行レポートを開く</button>
      <button data-kind="openManifest">manifestを開く</button>
    </div>
  </header>
  <main>
    ${model.entries.length === 0 ? '<div class="empty">登録済み関数はありません。</div>' : renderTable(model.entries)}
  </main>
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
        vscode.postMessage({ kind: button.dataset.kind, label });
      });
    });
    document.querySelectorAll('input[data-entry-id]').forEach((input) => {
      input.addEventListener('change', () => vscode.postMessage({ kind: 'toggleEntry', entryId: input.dataset.entryId, checked: input.checked }));
    });
  </script>
</body>
</html>`;
}

function renderTable(entries: SuiteEntryView[]): string {
  return `<div class="table-wrap"><table>
  <thead>
    <tr>
      <th>選択</th>
      <th>関数</th>
      <th>ソース</th>
      <th>タグ</th>
      <th>GREEN</th>
      <th>実行status</th>
      <th>テスト</th>
      <th>失敗</th>
      <th>未解決</th>
      <th>エラー</th>
      <th>workspace</th>
    </tr>
  </thead>
  <tbody>${entries.map(renderRow).join('')}</tbody>
</table></div>`;
}

function renderRow(entry: SuiteEntryView): string {
  const greenClass = entry.greenStatus === 'green' ? 'green' : entry.greenStatus === 'not_green' ? 'not-green' : '';
  const greenLabel = entry.greenStatus === 'green' ? 'GREEN' : entry.greenStatus === 'not_green' ? 'Not GREEN' : '未実行';
  const tests = entry.totalTests > 0 ? `${entry.passedTests}/${entry.totalTests}` : '-';
  return `<tr class="${entry.enabled ? '' : 'disabled'}">
    <td><input type="checkbox" data-entry-id="${escapeAttribute(entry.entryId)}" ${entry.selected ? 'checked' : ''}></td>
    <td>${escapeHtml(entry.functionName)}</td>
    <td class="wrap">${escapeHtml(entry.source)}</td>
    <td class="wrap">${escapeHtml(entry.tags.join(', '))}</td>
    <td class="${greenClass}">${escapeHtml(greenLabel)}</td>
    <td>${escapeHtml(entry.lastRunStatus)}</td>
    <td>${escapeHtml(tests)}</td>
    <td>${entry.failedTests}</td>
    <td>${entry.unresolvedReviewCount}</td>
    <td class="wrap">${escapeHtml(entry.error)}</td>
    <td class="wrap">${escapeHtml(entry.workspace)}</td>
  </tr>`;
}

function renderMetric(label: string, value: number): string {
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`;
}

function suiteDashboardActionLabel(kind: SuiteDashboardMessage['kind']): string {
  const labels: Record<SuiteDashboardMessage['kind'], string> = {
    register: '現在関数を登録',
    runSelected: '選択を実行',
    runTag: 'タグ指定で実行',
    runAllGreen: '全件GREEN確認',
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

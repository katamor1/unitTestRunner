import * as fs from 'fs';
import * as vscode from 'vscode';

import { SettingsActionKind, SettingsFieldId, SettingsViewModel } from '../config/settingsViewModel';
import { ReportPaths, resolveReportPaths } from '../reports/reportPathResolver';
import { openReport } from '../reports/reportOpener';
import { renderSettings } from './settingsPanelRenderer';
import {
  buildWorkflowStepViews,
  completeWorkflowStep,
  createInitialWorkflowState,
  markStepAwaitingSave,
  OPTIONAL_WORKFLOW_ACTIONS,
  reportAvailabilityFromPaths,
  setWorkflowSettingsReady,
  WorkflowAction,
  WorkflowState,
  WorkflowStepId,
  WORKFLOW_STATE_KEY,
} from './workflowState';

interface WorkflowActionMessage {
  type: 'workflowAction';
  kind: WorkflowAction['kind'];
  commandId?: string;
  reportKey?: keyof ReportPaths;
  stepId?: WorkflowStepId;
  label?: string;
}

interface SettingsActionMessage {
  type: 'settingsAction';
  kind: SettingsActionKind;
  fieldId: SettingsFieldId;
  label?: string;
}

type WorkflowMessage = WorkflowActionMessage | SettingsActionMessage;
type WorkflowStepViews = ReturnType<typeof buildWorkflowStepViews>;

export const SIMPLE_WORKFLOW_ACTIONS: WorkflowAction[] = [
  { id: 'quickCheckCurrent', kind: 'command', label: 'Quick Check', commandId: 'unitTestRunner.quickCheckCurrentFunction', primary: true },
  { id: 'openQuickSummary', kind: 'command', label: 'Quick Summaryを開く', commandId: 'unitTestRunner.openQuickSummary' },
  { id: 'runFullGate', kind: 'command', label: 'Full Gateへ進む', commandId: 'unitTestRunner.runFullGateForCurrentFunction', danger: true },
  { id: 'openDossier', kind: 'openReport', label: 'dossierを開く', reportKey: 'functionDossierMd' },
  { id: 'openOutputWorkspace', kind: 'openOutputWorkspace', label: '出力workspaceを開く' },
];

export class WorkflowPanelProvider implements vscode.WebviewViewProvider {
  static readonly viewType = 'unitTestRunner.workflow';

  private view?: vscode.WebviewView;
  private runningLabel?: string;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly settingsReady: () => boolean,
    private readonly settingsViewModel: () => SettingsViewModel,
    private readonly handleSettingsAction: (fieldId: SettingsFieldId, kind: SettingsActionKind) => Promise<void>,
  ) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.onDidReceiveMessage((message: WorkflowMessage) => {
      void this.handleMessage(message);
    });
    this.refresh();
  }

  refresh(): void {
    if (!this.view) {
      return;
    }
    const webview = this.view.webview;
    const state = this.readState();
    const reports = resolveWorkflowReports(state);
    const availability = reportAvailabilityFromPaths(reports, fs.existsSync);
    const steps = buildWorkflowStepViews(state, availability);
    const settings = this.settingsViewModel();
    webview.html = renderWorkflowHtml(webview, state, settings, steps, OPTIONAL_WORKFLOW_ACTIONS, this.runningLabel);
  }

  private async handleMessage(message: WorkflowMessage): Promise<void> {
    if (this.runningLabel) {
      void vscode.window.showInformationMessage(`UnitTestRunner: ${this.runningLabel}を実行中です。完了するまでお待ちください。`);
      return;
    }
    this.runningLabel = message.label || fallbackWorkflowActionLabel(message);
    this.refresh();
    try {
      if (message.type === 'settingsAction') {
        await this.handleSettingsAction(message.fieldId, message.kind);
      } else if (message.kind === 'command' && message.commandId) {
        await vscode.commands.executeCommand(message.commandId);
      } else if (message.kind === 'openReport' && message.reportKey) {
        await this.openWorkflowReport(message.reportKey, message.stepId);
      } else if (message.kind === 'confirmStep' && message.stepId) {
        await this.updateState(completeWorkflowStep(this.readState(), message.stepId));
      } else if (message.kind === 'openSettings') {
        await vscode.commands.executeCommand('workbench.action.openSettings', 'unitTestRunner');
      } else if (message.kind === 'openOutputWorkspace') {
        await vscode.commands.executeCommand('unitTestRunner.openOutputWorkspace');
      } else if (message.kind === 'copyLastCommand') {
        await vscode.commands.executeCommand('unitTestRunner.copyLastCommand');
      }
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      void vscode.window.showErrorMessage(`UnitTestRunner: ${messageText}`);
    } finally {
      this.runningLabel = undefined;
      this.refresh();
    }
  }

  private async openWorkflowReport(reportKey: keyof ReportPaths, stepId?: WorkflowStepId): Promise<void> {
    const state = this.readState();
    const reports = resolveWorkflowReports(state);
    const reportPath = reports?.[reportKey];
    if (typeof reportPath !== 'string' || !reportPath) {
      void vscode.window.showWarningMessage('UnitTestRunner: 対象レポートがまだ記録されていません。');
      return;
    }
    if (!fs.existsSync(reportPath)) {
      void vscode.window.showWarningMessage(`UnitTestRunner: レポートが見つかりません: ${reportPath}`);
      return;
    }
    await openReport(reportPath);
    if (stepId) {
      await this.updateState(markStepAwaitingSave(state, stepId, reportPath, reportKey));
    }
  }

  private readState(): WorkflowState {
    const stored = this.context.workspaceState.get<WorkflowState>(WORKFLOW_STATE_KEY);
    const base = stored ?? createInitialWorkflowState(this.settingsReady());
    return setWorkflowSettingsReady(base, this.settingsReady());
  }

  private async updateState(state: WorkflowState): Promise<void> {
    await this.context.workspaceState.update(WORKFLOW_STATE_KEY, state);
  }
}

export function resolveWorkflowReports(state: WorkflowState): Partial<ReportPaths> | undefined {
  const workspace = state.outputWorkspace || state.reports?.workspace;
  const conventional = workspace ? resolveReportPaths(workspace) : undefined;
  if (!conventional && !state.reports) {
    return undefined;
  }
  return {
    ...conventional,
    ...state.reports,
    workspace,
  };
}

export function renderWorkflowHtml(webview: vscode.Webview, state: WorkflowState, settings: SettingsViewModel, steps: WorkflowStepViews, optionalActions: WorkflowAction[], runningLabel?: string): string {
  void webview;
  const nonce = createNonce();
  const functionName = state.functionName || '対象関数未選択';
  const workspace = state.outputWorkspace || state.reports?.workspace || '出力workspace未選択';
  const awaiting = state.awaitingSave ? `<div class="notice">保存待ち: ${escapeHtml(state.awaitingSave.filePath)}</div>` : '';
  const error = state.lastError ? `<div class="error">直近エラー: ${escapeHtml(state.lastError)}</div>` : '';
  const running = runningLabel ? `<div class="busy" role="status">実行中: ${escapeHtml(runningLabel)}<br><span>大きいプロジェクトでは時間がかかります。完了までボタンは無効です。</span></div>` : '';
  const fullPanel = renderFullWorkflowPanel(functionName, workspace, steps, optionalActions);
  const simplePanel = renderSimpleWorkflowPanel(functionName, workspace, steps);
  return `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style nonce="${nonce}">
    body {
      color: var(--vscode-foreground);
      background: var(--vscode-sideBar-background);
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      margin: 0;
      padding: 12px;
    }
    .summary {
      border-bottom: 1px solid var(--vscode-sideBarSectionHeader-border, var(--vscode-editorGroup-border));
      padding-bottom: 10px;
      margin-bottom: 10px;
    }
    .settings {
      border-bottom: 1px solid var(--vscode-sideBarSectionHeader-border, var(--vscode-editorGroup-border));
      margin-bottom: 10px;
      padding-bottom: 10px;
    }
    .settings-summary {
      align-items: center;
      cursor: pointer;
      display: flex;
      gap: 8px;
      justify-content: space-between;
      list-style: none;
      margin-bottom: 8px;
    }
    .settings-summary::-webkit-details-marker {
      display: none;
    }
    .settings h2, .optional h2, .simple-card h2 {
      font-size: 12px;
      margin: 0 0 8px 0;
      text-transform: uppercase;
      color: var(--vscode-descriptionForeground);
    }
    .settings-toggle {
      color: var(--vscode-descriptionForeground);
      font-size: 11px;
      white-space: nowrap;
    }
    .settings[open] .settings-collapsed-label,
    .settings:not([open]) .settings-expanded-label {
      display: none;
    }
    .settings-ready {
      color: var(--vscode-descriptionForeground);
      margin: 0 0 8px 0;
    }
    .setting-field {
      border-left: 3px solid var(--vscode-editorGroup-border);
      margin: 0 0 8px 0;
      padding: 8px 0 8px 10px;
    }
    .setting-field.default {
      border-left-color: var(--vscode-testing-iconQueued);
    }
    .setting-field.configured,
    .setting-field.optional {
      border-left-color: var(--vscode-testing-iconPassed);
    }
    .setting-field.missing,
    .setting-field.warning {
      border-left-color: var(--vscode-inputValidation-warningBorder);
      background: var(--vscode-inputValidation-warningBackground);
    }
    .setting-title {
      align-items: baseline;
      display: flex;
      gap: 6px;
      justify-content: space-between;
    }
    .setting-title h3 {
      font-size: 12px;
      line-height: 1.3;
      margin: 0;
    }
    .setting-status {
      color: var(--vscode-descriptionForeground);
      font-size: 11px;
      white-space: nowrap;
    }
    .setting-value, .path, .simple-meta {
      color: var(--vscode-descriptionForeground);
      overflow-wrap: anywhere;
    }
    .setting-value {
      margin-top: 4px;
    }
    .setting-message {
      color: var(--vscode-inputValidation-warningForeground);
      margin-top: 4px;
      overflow-wrap: anywhere;
    }
    .name {
      font-weight: 700;
      margin-bottom: 4px;
    }
    .notice, .error, .busy {
      border: 1px solid var(--vscode-inputValidation-warningBorder);
      background: var(--vscode-inputValidation-warningBackground);
      color: var(--vscode-inputValidation-warningForeground);
      padding: 8px;
      margin: 8px 0;
    }
    .error {
      border-color: var(--vscode-inputValidation-errorBorder);
      background: var(--vscode-inputValidation-errorBackground);
      color: var(--vscode-inputValidation-errorForeground);
    }
    .busy {
      border-color: var(--vscode-focusBorder);
      background: var(--vscode-editorWidget-background);
      color: var(--vscode-foreground);
      font-weight: 700;
    }
    .busy span {
      color: var(--vscode-descriptionForeground);
      font-weight: 400;
    }
    .view-switch {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin: 0 0 10px 0;
    }
    .panel-view.hidden {
      display: none;
    }
    .simple-card {
      border-left: 3px solid var(--vscode-focusBorder);
      background: var(--vscode-editorWidget-background);
      margin: 0 0 10px 0;
      padding: 10px;
    }
    .simple-card h3 {
      font-size: 14px;
      line-height: 1.35;
      margin: 0 0 6px 0;
    }
    .simple-counts {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin: 8px 0;
    }
    .simple-count {
      border: 1px solid var(--vscode-editorGroup-border);
      padding: 8px;
    }
    .simple-count strong {
      display: block;
      font-size: 16px;
    }
    .simple-count span {
      color: var(--vscode-descriptionForeground);
      font-size: 11px;
    }
    .step {
      border-left: 3px solid var(--vscode-editorGroup-border);
      padding: 9px 0 10px 10px;
      margin: 0 0 8px 0;
      opacity: 0.72;
    }
    .step.done {
      border-left-color: var(--vscode-testing-iconPassed);
      opacity: 0.82;
    }
    .step.current {
      border-left-color: var(--vscode-focusBorder);
      background: var(--vscode-list-activeSelectionBackground);
      color: var(--vscode-list-activeSelectionForeground);
      opacity: 1;
      padding-right: 8px;
    }
    .step h3 {
      font-size: 13px;
      line-height: 1.3;
      margin: 0 0 6px 0;
    }
    .status {
      display: inline-block;
      font-size: 11px;
      color: var(--vscode-descriptionForeground);
      margin-bottom: 4px;
    }
    .current .status {
      color: var(--vscode-list-activeSelectionForeground);
      font-weight: 700;
    }
    p {
      margin: 4px 0;
      line-height: 1.45;
    }
    .required {
      color: var(--vscode-descriptionForeground);
    }
    .current .required {
      color: var(--vscode-list-activeSelectionForeground);
    }
    .actions {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-top: 8px;
    }
    button {
      background: var(--vscode-button-secondaryBackground);
      color: var(--vscode-button-secondaryForeground);
      border: 1px solid transparent;
      border-radius: 2px;
      min-height: 28px;
      padding: 4px 8px;
      text-align: left;
      cursor: pointer;
      overflow-wrap: anywhere;
    }
    button:hover {
      background: var(--vscode-button-secondaryHoverBackground);
    }
    button:disabled {
      cursor: wait;
      opacity: 0.65;
    }
    button.primary, button.active-mode {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
    }
    button.primary:hover, button.active-mode:hover {
      background: var(--vscode-button-hoverBackground);
    }
    button.danger {
      border-color: var(--vscode-inputValidation-warningBorder);
    }
    .optional {
      margin-top: 14px;
      border-top: 1px solid var(--vscode-editorGroup-border);
      padding-top: 10px;
    }
  </style>
</head>
<body data-default-mode="simple">
  ${renderSettings(settings)}
  <div class="view-switch" role="group" aria-label="表示切替">
    <button type="button" data-view-mode="simple" class="active-mode">簡易</button>
    <button type="button" data-view-mode="full">従来</button>
  </div>
  ${awaiting}
  ${error}
  ${running}
  <section id="simplePanel" class="panel-view simple-panel">${simplePanel}</section>
  <section id="fullPanel" class="panel-view full-panel hidden">${fullPanel}</section>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const initialRunningLabel = ${JSON.stringify(runningLabel ?? '')};
    const persistedState = vscode.getState() || {};
    function setPanelMode(mode) {
      const safeMode = mode === 'full' ? 'full' : 'simple';
      document.getElementById('simplePanel')?.classList.toggle('hidden', safeMode !== 'simple');
      document.getElementById('fullPanel')?.classList.toggle('hidden', safeMode !== 'full');
      document.querySelectorAll('button[data-view-mode]').forEach((button) => {
        button.classList.toggle('active-mode', button.dataset.viewMode === safeMode);
      });
      vscode.setState({ ...persistedState, panelMode: safeMode });
    }
    setPanelMode(persistedState.panelMode || 'simple');
    function disableButtons(activeButton, label) {
      const runningText = label || '処理';
      document.querySelectorAll('button[data-kind], button[data-setting-kind]').forEach((button) => {
        button.disabled = true;
        button.setAttribute('aria-disabled', 'true');
      });
      if (activeButton) {
        activeButton.textContent = '実行中: ' + runningText;
      }
    }
    if (initialRunningLabel) {
      disableButtons(null, initialRunningLabel);
    }
    document.querySelectorAll('button[data-view-mode]').forEach((button) => {
      button.addEventListener('click', () => setPanelMode(button.dataset.viewMode));
    });
    document.querySelectorAll('button[data-kind]').forEach((button) => {
      button.addEventListener('click', () => {
        const label = button.dataset.label || button.textContent || '処理';
        disableButtons(button, label);
        vscode.postMessage({
          type: 'workflowAction',
          kind: button.dataset.kind,
          commandId: button.dataset.commandId,
          reportKey: button.dataset.reportKey,
          stepId: button.dataset.stepId,
          label
        });
      });
    });
    document.querySelectorAll('button[data-setting-kind]').forEach((button) => {
      button.addEventListener('click', () => {
        const label = button.textContent || '設定操作';
        disableButtons(button, label);
        vscode.postMessage({
          type: 'settingsAction',
          kind: button.dataset.settingKind,
          fieldId: button.dataset.fieldId,
          label
        });
      });
    });
  </script>
</body>
</html>`;
}

function renderSimpleWorkflowPanel(functionName: string, workspace: string, steps: WorkflowStepViews): string {
  const current = steps.find((step) => step.status === 'current') ?? steps[0];
  const doneCount = steps.filter((step) => step.status === 'done').length;
  return `<div class="summary">
  <div class="name">${escapeHtml(functionName)}</div>
  <div class="path">${escapeHtml(workspace)}</div>
</div>
<div class="simple-card">
  <h2>現在の状態</h2>
  <h3>${escapeHtml(current?.title ?? '設定確認')}</h3>
  <p>${escapeHtml(current?.requiredAction ?? '設定を確認してください。')}</p>
  <div class="simple-counts">
    <div class="simple-count"><strong>${doneCount}</strong><span>完了工程</span></div>
    <div class="simple-count"><strong>${steps.length}</strong><span>全工程</span></div>
  </div>
</div>
<div class="simple-card">
  <h2>よく使う操作</h2>
  <div class="actions">${SIMPLE_WORKFLOW_ACTIONS.map(renderAction).join('')}</div>
</div>
<div class="simple-card">
  <h2>表示切替</h2>
  <p class="simple-meta">正式レビューや証跡確認の全工程を見る場合は従来表示に切り替えます。</p>
  <button type="button" data-view-mode="full">従来パネルを表示</button>
</div>`;
}

function renderFullWorkflowPanel(functionName: string, workspace: string, steps: WorkflowStepViews, optionalActions: WorkflowAction[]): string {
  return `<div class="summary">
  <div class="name">${escapeHtml(functionName)}</div>
  <div class="path">${escapeHtml(workspace)}</div>
</div>
${steps.map(renderStep).join('')}
<div class="optional">
  <h2>任意操作</h2>
  <div class="actions">${optionalActions.map(renderAction).join('')}</div>
</div>`;
}

function renderStep(step: WorkflowStepViews[number]): string {
  const label = step.status === 'done' ? '完了' : step.status === 'current' ? '現在の推奨' : '未実施';
  return `<section class="step ${step.status}">
  <span class="status">${label}</span>
  <h3>${escapeHtml(step.title)}</h3>
  <p>${escapeHtml(step.purpose)}</p>
  <p class="required">${escapeHtml(step.requiredAction)}</p>
  <div class="actions">${step.actions.map(renderAction).join('')}</div>
</section>`;
}

function renderAction(action: WorkflowAction): string {
  const classes = [action.primary ? 'primary' : '', action.danger ? 'danger' : ''].filter(Boolean).join(' ');
  const attributes = [
    `data-kind="${escapeAttribute(action.kind)}"`,
    `data-label="${escapeAttribute(action.label)}"`,
    action.commandId ? `data-command-id="${escapeAttribute(action.commandId)}"` : '',
    action.reportKey ? `data-report-key="${escapeAttribute(String(action.reportKey))}"` : '',
    action.stepId ? `data-step-id="${escapeAttribute(action.stepId)}"` : '',
  ].filter(Boolean).join(' ');
  return `<button class="${classes}" ${attributes}>${escapeHtml(action.label)}</button>`;
}

function fallbackWorkflowActionLabel(message: WorkflowMessage): string {
  if (message.type === 'settingsAction') {
    return '設定操作';
  }
  if (message.kind === 'command') {
    return commandLabel(message.commandId);
  }
  if (message.kind === 'openReport') {
    return 'レポートを開く';
  }
  if (message.kind === 'confirmStep') {
    return '工程を更新';
  }
  if (message.kind === 'openSettings') {
    return '設定を開く';
  }
  if (message.kind === 'openOutputWorkspace') {
    return '出力workspaceを開く';
  }
  if (message.kind === 'copyLastCommand') {
    return '最後のCLIコマンドをコピー';
  }
  return '処理';
}

function commandLabel(commandId?: string): string {
  const labels: Record<string, string> = {
    'unitTestRunner.quickCheckCurrentFunction': 'Quick Check',
    'unitTestRunner.quickCheckSelectedFunction': 'Quick Check',
    'unitTestRunner.openQuickSummary': 'Quick Summaryを開く',
    'unitTestRunner.runFullGateForCurrentFunction': 'Full Gateへ進む',
    'unitTestRunner.analyzeCurrentFunction': '現在関数を解析',
    'unitTestRunner.analyzeSelectedFunction': '選択関数を解析',
    'unitTestRunner.reanalyzeCurrentFunction': '現在関数を再解析',
    'unitTestRunner.finalizeDossier': 'dossierを確定',
    'unitTestRunner.generateTestDesign': 'テスト設計を生成',
    'unitTestRunner.generateHarnessSkeleton': 'ハーネスを生成',
    'unitTestRunner.buildProbeDryRun': 'ビルドプローブをdry-run',
    'unitTestRunner.runBuildProbe': 'ビルドプローブを実行',
    'unitTestRunner.runTests': 'テストを実行',
    'unitTestRunner.prepareEvidence': 'エビデンスを準備',
  };
  return commandId ? labels[commandId] ?? commandId : 'コマンド実行';
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
    nonce += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return nonce;
}

import * as fs from 'fs';
import type * as vscode from 'vscode';

import { SettingsActionKind, SettingsFieldId, SettingsViewModel } from '../config/settingsViewModel';
import { ReportPaths, resolveReportPaths } from '../reports/reportPathResolver';
import { openReport } from '../reports/reportOpener';
import { renderSettings } from './settingsPanelRenderer';
import {
  buildWorkflowStepViews,
  completeWorkflowStep,
  OPTIONAL_WORKFLOW_ACTIONS,
  reportAvailabilityFromPaths,
  setWorkflowSettingsReady,
  WorkflowAction,
  WorkflowState,
  WorkflowStepId,
  WorkflowStepStatus,
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

export interface WorkflowActionPresentation {
  label: string;
  classes: string;
  primary: boolean;
  hidden: boolean;
}

export const SIMPLE_WORKFLOW_ACTIONS: WorkflowAction[] = [
  { id: 'analyzeCurrent', kind: 'command', label: '現在の関数を解析', commandId: 'unitTestRunner.analyzeCurrentFunction', primary: true },
  { id: 'openTestInputEditor', kind: 'command', label: 'TestSpecをレビュー', commandId: 'unitTestRunner.openTestInputEditor', primary: true },
  { id: 'runBuildProbe', kind: 'command', label: 'ビルドを実行', commandId: 'unitTestRunner.runBuildProbe', primary: true, danger: true },
  { id: 'runTests', kind: 'command', label: 'テストを実行', commandId: 'unitTestRunner.runTests', primary: true, danger: true },
];

export const SIMPLE_SECONDARY_ACTIONS: WorkflowAction[] = [
  { id: 'openDossier', kind: 'openReport', label: 'function_dossierを開く', reportKey: 'functionDossierMd' },
  { id: 'openBuildProbe', kind: 'openReport', label: 'ビルド結果を開く', reportKey: 'buildProbeReportMd' },
  { id: 'openTestRun', kind: 'openReport', label: 'テスト結果を開く', reportKey: 'testRunReportMd' },
  { id: 'openOutputWorkspace', kind: 'openOutputWorkspace', label: '出力ワークスペースを開く' },
];

export function workflowStatusLabel(status: WorkflowStepStatus): string {
  return status === 'done' ? '完了' : status === 'current' ? '次の操作' : '未実施';
}

export function resolveWorkflowActionPresentation(
  action: WorkflowAction,
  status?: WorkflowStepStatus,
  _state?: WorkflowState,
): WorkflowActionPresentation {
  const label = status === 'done' && action.repeatLabel ? action.repeatLabel : action.label;
  const primary = status === 'current' && action.primary === true;
  return {
    label,
    primary,
    hidden: status === 'done' && action.kind === 'confirmStep',
    classes: [primary ? 'primary' : '', action.danger ? 'danger' : ''].filter(Boolean).join(' '),
  };
}

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
    webviewView.webview.onDidReceiveMessage((message: WorkflowMessage) => void this.handleMessage(message));
    this.refresh();
  }

  refresh(): void {
    if (!this.view) return;
    const state = this.readState();
    const reports = resolveWorkflowReports(state);
    const availability = reportAvailabilityFromPaths(reports, fs.existsSync);
    const steps = buildWorkflowStepViews(state, availability);
    this.view.webview.html = renderWorkflowHtml(
      this.view.webview,
      state,
      this.settingsViewModel(),
      steps,
      OPTIONAL_WORKFLOW_ACTIONS,
      this.runningLabel,
    );
  }

  private async handleMessage(message: WorkflowMessage): Promise<void> {
    const vscode = vscodeApi();
    if (this.runningLabel) {
      void vscode.window.showInformationMessage(`UnitTestRunner: 「${this.runningLabel}」を実行中です。`);
      return;
    }
    this.runningLabel = message.label || '処理';
    this.refresh();
    try {
      if (message.type === 'settingsAction') {
        await this.handleSettingsAction(message.fieldId, message.kind);
      } else if (message.kind === 'command' && message.commandId) {
        await vscode.commands.executeCommand(message.commandId);
      } else if (message.kind === 'openReport' && message.reportKey) {
        const reportPath = resolveWorkflowReports(this.readState())?.[message.reportKey];
        if (typeof reportPath !== 'string' || !fs.existsSync(reportPath)) {
          throw new Error('対象レポートがまだ生成されていません。');
        }
        await openReport(reportPath);
      } else if (message.kind === 'confirmStep' && message.stepId) {
        await this.updateState(completeWorkflowStep(this.readState(), message.stepId));
      } else if (message.kind === 'openSettings') {
        await vscode.commands.executeCommand('workbench.action.openSettings', '@ext:local.unit-test-runner-vscode');
      } else if (message.kind === 'openOutputWorkspace') {
        await vscode.commands.executeCommand('unitTestRunner.openOutputWorkspace');
      } else if (message.kind === 'copyLastCommand') {
        await vscode.commands.executeCommand('unitTestRunner.copyLastCommand');
      }
    } catch (error) {
      void vscode.window.showErrorMessage(`UnitTestRunner: ${errorMessage(error)}`);
    } finally {
      this.runningLabel = undefined;
      this.refresh();
    }
  }

  private readState(): WorkflowState {
    const ready = this.settingsReady();
    const stored = this.context.workspaceState.get<WorkflowState>(WORKFLOW_STATE_KEY);
    return stored ? setWorkflowSettingsReady(stored, ready) : { settingsReady: ready, completedStepIds: ready ? ['settings'] : [] };
  }

  private async updateState(state: WorkflowState): Promise<void> {
    await this.context.workspaceState.update(WORKFLOW_STATE_KEY, state);
  }
}

export function resolveWorkflowReports(state: WorkflowState): Partial<ReportPaths> | undefined {
  if (!state.outputWorkspace) return state.reports;
  return { ...resolveReportPaths(state.outputWorkspace), ...state.reports, workspace: state.outputWorkspace };
}

export function renderWorkflowHtml(
  _webview: vscode.Webview,
  state: WorkflowState,
  settings: SettingsViewModel,
  steps: WorkflowStepViews,
  optionalActions: WorkflowAction[],
  runningLabel?: string,
): string {
  const nonce = createNonce();
  const running = runningLabel
    ? `<div class="busy" role="status">「${escapeHtml(runningLabel)}」を実行しています。</div>`
    : '';
  const error = state.lastError ? `<div class="error" role="alert">${escapeHtml(state.lastError)}</div>` : '';
  return `<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style nonce="${nonce}">
body{color:var(--vscode-foreground);background:var(--vscode-sideBar-background);font-family:var(--vscode-font-family);font-size:var(--vscode-font-size);margin:0;padding:12px}
h1{font-size:1.2rem}.step{border-left:3px solid var(--vscode-editorGroup-border);margin:10px 0;padding:4px 0 8px 10px}.step.current{border-left-color:var(--vscode-focusBorder)}.step.done{border-left-color:var(--vscode-testing-iconPassed)}
.status,.meta{color:var(--vscode-descriptionForeground)}.actions{display:flex;flex-direction:column;gap:6px}.optional{border-top:1px solid var(--vscode-editorGroup-border);margin-top:14px;padding-top:10px}
button{background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground);border:1px solid transparent;border-radius:2px;min-height:28px;padding:4px 8px;text-align:left}button.primary{background:var(--vscode-button-background);color:var(--vscode-button-foreground)}button.danger{border-color:var(--vscode-inputValidation-warningBorder)}button:disabled{opacity:.65}
.busy,.error{margin:8px 0;padding:8px}.busy{border:1px solid var(--vscode-focusBorder)}.error{border:1px solid var(--vscode-inputValidation-errorBorder)}
</style></head><body>
<h1>Unit Test Runner</h1>${running}${error}${renderSettings(settings)}
<div class="meta" role="status">対象: ${escapeHtml(state.functionName ?? '未選択')}</div>
${steps.map((step) => renderStep(step, state, Boolean(runningLabel))).join('')}
<section class="optional"><h2>再解析と補助操作</h2><div class="actions">${optionalActions.map((action) => renderAction(action, undefined, state, Boolean(runningLabel))).join('')}</div></section>
<script nonce="${nonce}">
const vscode=acquireVsCodeApi();let lastFocus;
document.querySelectorAll('button[data-action-kind]').forEach((button)=>button.addEventListener('click',()=>{lastFocus=button.dataset.focusKey;vscode.setState({lastFocus});vscode.postMessage({type:'workflowAction',kind:button.dataset.actionKind,commandId:button.dataset.commandId||undefined,reportKey:button.dataset.reportKey||undefined,stepId:button.dataset.stepId||undefined,label:button.textContent||undefined});}));
document.querySelectorAll('button[data-setting-kind]').forEach((button)=>button.addEventListener('click',()=>{lastFocus=button.dataset.focusKey;vscode.setState({lastFocus});vscode.postMessage({type:'settingsAction',kind:button.dataset.settingKind,fieldId:button.dataset.fieldId,label:button.textContent||undefined});}));
const saved=vscode.getState();if(saved&&saved.lastFocus){requestAnimationFrame(()=>{const target=document.querySelector('[data-focus-key="'+CSS.escape(saved.lastFocus)+'"]');if(target)target.focus();});}
</script></body></html>`;
}

function renderStep(step: WorkflowStepViews[number], state: WorkflowState, disabled: boolean): string {
  return `<section class="step ${step.status}"><h2>${escapeHtml(step.title)}</h2><div class="status">${workflowStatusLabel(step.status)}</div><p>${escapeHtml(step.purpose)}</p><p>${escapeHtml(step.requiredAction)}</p><div class="actions">${step.actions.map((action) => renderAction(action, step.status, state, disabled)).join('')}</div></section>`;
}

function renderAction(action: WorkflowAction, status: WorkflowStepStatus | undefined, state: WorkflowState, disabled: boolean): string {
  const presentation = resolveWorkflowActionPresentation(action, status, state);
  if (presentation.hidden) return '';
  return `<button class="${presentation.classes}" aria-label="${escapeAttribute(presentation.label)}" data-action-kind="${escapeAttribute(action.kind)}" data-command-id="${escapeAttribute(action.commandId ?? '')}" data-report-key="${escapeAttribute(action.reportKey ?? '')}" data-step-id="${escapeAttribute(action.stepId ?? '')}" data-focus-key="action:${escapeAttribute(action.id)}"${disabled ? ' disabled' : ''}>${escapeHtml(presentation.label)}</button>`;
}

function createNonce(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function escapeAttribute(value: string): string {
  return escapeHtml(value);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function vscodeApi(): typeof import('vscode') {
  return require('vscode') as typeof import('vscode');
}

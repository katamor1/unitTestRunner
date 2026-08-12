import type * as vscode from 'vscode';

import { readSuiteViewModel, SuiteEntryView, SuiteViewModel, SUITE_SELECTION_KEY } from './suiteViewModel';

interface SuiteActionMessage {
  type?: 'suiteAction';
  kind: 'register' | 'runSelected' | 'openReport' | 'toggleEntry' | 'toggleEnabled';
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
    private readonly toggleEnabled?: (entryId: string, enabled: boolean) => Promise<void>,
  ) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.onDidReceiveMessage((message: SuiteActionMessage) => void this.handleMessage(message));
    this.refresh();
  }

  refresh(): void {
    if (!this.view) return;
    const suitePath = this.suiteManifestPath();
    const selected = new Set(this.context.workspaceState.get<string[]>(SUITE_SELECTION_KEY) ?? []);
    const model = readSuiteViewModel(suitePath, selected, this.lastError());
    this.view.webview.html = renderSuiteHtml(model, this.runningLabel);
  }

  private async handleMessage(message: SuiteActionMessage): Promise<void> {
    const vscode = vscodeApi();
    if (message.kind === 'toggleEntry') {
      if (!message.entryId || this.runningLabel) return;
      const selected = new Set(this.context.workspaceState.get<string[]>(SUITE_SELECTION_KEY) ?? []);
      if (message.checked) selected.add(message.entryId); else selected.delete(message.entryId);
      await this.context.workspaceState.update(SUITE_SELECTION_KEY, [...selected]);
      this.refresh();
      return;
    }
    if (this.runningLabel) {
      void vscode.window.showInformationMessage(`UnitTestRunner: 「${this.runningLabel}」を実行中です。`);
      return;
    }
    this.runningLabel = message.label || suiteActionLabel(message.kind);
    this.refresh();
    try {
      if (message.kind === 'toggleEnabled' && message.entryId && this.toggleEnabled) {
        await this.toggleEnabled(message.entryId, Boolean(message.checked));
      } else {
        const commandId: string | undefined = ({
          register: 'unitTestRunner.registerCurrentFunctionInSuite',
          runSelected: 'unitTestRunner.runSelectedSuiteTests',
          openReport: 'unitTestRunner.openSuiteRunReport',
        } as Partial<Record<SuiteActionMessage['kind'], string>>)[message.kind];
        if (commandId) await vscode.commands.executeCommand(commandId);
      }
    } catch (error) {
      void vscode.window.showErrorMessage(`UnitTestRunner: ${errorMessage(error)}`);
    } finally {
      this.runningLabel = undefined;
      this.refresh();
    }
  }
}

export function readSelectedSuiteEntryIds(context: vscode.ExtensionContext): string[] {
  return context.workspaceState.get<string[]>(SUITE_SELECTION_KEY) ?? [];
}

export function renderSuiteHtml(model: SuiteViewModel, runningLabel?: string): string {
  const nonce = createNonce();
  const summary = model.reportExists
    ? `<div class="summary">合計 ${model.summary.total}件 / 合格 ${model.summary.green}件 / 不合格 ${model.summary.notGreen}件</div>`
    : '<div class="summary muted">実行結果はまだありません。</div>';
  const error = model.lastError ? `<div class="error" role="alert">${escapeHtml(model.lastError)}</div>` : '';
  const running = runningLabel ? `<div class="busy" role="status">「${escapeHtml(runningLabel)}」を実行しています。</div>` : '';
  return `<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><style nonce="${nonce}">
body{color:var(--vscode-foreground);background:var(--vscode-sideBar-background);font-family:var(--vscode-font-family);font-size:var(--vscode-font-size);margin:0;padding:12px}.path,.meta,.muted{color:var(--vscode-descriptionForeground)}.path{overflow-wrap:anywhere;margin-bottom:8px}.summary{margin-bottom:8px}.actions{display:flex;flex-direction:column;gap:6px;margin:8px 0}button{background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground);border:1px solid transparent;min-height:28px;padding:4px 8px;text-align:left}button.primary{background:var(--vscode-button-background);color:var(--vscode-button-foreground)}button.danger{border-color:var(--vscode-inputValidation-warningBorder)}button:disabled,input:disabled{opacity:.65}.filter{box-sizing:border-box;width:100%;margin:8px 0;padding:5px}.entry{border-left:3px solid var(--vscode-editorGroup-border);margin:8px 0;padding:7px 0 7px 9px}.entry.disabled{opacity:.6}.entry.green{border-left-color:var(--vscode-testing-iconPassed)}.entry.not-green{border-left-color:var(--vscode-testing-iconFailed)}.title{font-weight:700}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.busy,.error{margin:8px 0;padding:8px}.busy{border:1px solid var(--vscode-focusBorder)}.error{border:1px solid var(--vscode-inputValidation-errorBorder)}</style></head><body>
<div class="path">${escapeHtml(model.suitePath || 'スイート定義ファイルが未設定です')}</div>${summary}${error}${running}
<div class="actions"><button class="primary" data-kind="register" data-focus-key="action:register">現在の関数をスイートに登録</button><button data-kind="runSelected" data-focus-key="action:runSelected">選択したテストを実行</button><button data-kind="openReport" data-focus-key="action:openReport">最新レポートを開く</button></div>
<label for="suiteFilter">関数名またはタグで絞り込み</label><input id="suiteFilter" class="filter" type="search" data-focus-key="filter" aria-label="関数名またはタグで絞り込み">
<div id="suiteEntries">${model.entries.length ? model.entries.map(renderEntry).join('') : '<p class="muted">登録済みの関数はありません。</p>'}</div>
<script nonce="${nonce}">const vscode=acquireVsCodeApi();const disabled=${JSON.stringify(Boolean(runningLabel))};
function remember(element){const state=vscode.getState()||{};vscode.setState({...state,focusKey:element.dataset.focusKey,filter:document.getElementById('suiteFilter').value});}
document.querySelectorAll('[data-focus-key]').forEach((element)=>element.addEventListener('focus',()=>remember(element)));
document.querySelectorAll('button[data-kind]').forEach((button)=>button.addEventListener('click',()=>vscode.postMessage({type:'suiteAction',kind:button.dataset.kind,label:button.textContent||undefined})));
document.querySelectorAll('input[data-entry-id]').forEach((input)=>input.addEventListener('change',()=>vscode.postMessage({type:'suiteAction',kind:'toggleEntry',entryId:input.dataset.entryId,checked:input.checked})));
document.querySelectorAll('input[data-enable-id]').forEach((input)=>input.addEventListener('change',()=>vscode.postMessage({type:'suiteAction',kind:'toggleEnabled',entryId:input.dataset.enableId,checked:input.checked,label:'有効状態を更新'})));
const filter=document.getElementById('suiteFilter');function applyFilter(){const q=filter.value.trim().toLowerCase();document.querySelectorAll('.entry').forEach((entry)=>{entry.hidden=q.length>0&&!entry.dataset.search.includes(q);});const state=vscode.getState()||{};vscode.setState({...state,filter:filter.value});}filter.addEventListener('input',applyFilter);
const state=vscode.getState()||{};filter.value=state.filter||'';applyFilter();requestAnimationFrame(()=>{const target=[...document.querySelectorAll('[data-focus-key]')].find((element)=>element.dataset.focusKey===state.focusKey&&!element.disabled);(target||document.querySelector('button:not([disabled]),input:not([disabled])'))?.focus();});
if(disabled)document.querySelectorAll('button,input').forEach((control)=>{control.disabled=true;control.setAttribute('aria-disabled','true');});</script></body></html>`;
}

function renderEntry(entry: SuiteEntryView): string {
  const statusClass = entry.greenStatus === 'green' ? 'green' : entry.greenStatus === 'not_green' ? 'not-green' : '';
  const result = entry.greenStatus === 'green' ? '合格' : entry.greenStatus === 'not_green' ? '不合格' : '未実行';
  const search = `${entry.functionName} ${entry.tags.join(' ')}`.toLowerCase();
  return `<section class="entry ${entry.enabled ? '' : 'disabled'} ${statusClass}" data-search="${escapeAttribute(search)}"><div class="title">${escapeHtml(entry.functionName || entry.entryId)}</div><div class="row"><label><input type="checkbox" data-entry-id="${escapeAttribute(entry.entryId)}" data-focus-key="select:${escapeAttribute(entry.entryId)}" aria-label="実行対象を選択: ${escapeAttribute(entry.functionName || entry.entryId)}" ${entry.selected ? 'checked' : ''}>実行対象</label><label><input type="checkbox" data-enable-id="${escapeAttribute(entry.entryId)}" data-focus-key="enabled:${escapeAttribute(entry.entryId)}" aria-label="有効化: ${escapeAttribute(entry.functionName || entry.entryId)}" ${entry.enabled ? 'checked' : ''}>有効</label></div><div class="meta">${escapeHtml(entry.source)} / ${escapeHtml(entry.tags.join(', '))}</div><div class="meta">${escapeHtml(result)} / ${escapeHtml(entry.lastRunStatus || 'not_run')}</div></section>`;
}

function suiteActionLabel(kind: SuiteActionMessage['kind']): string {
  return { register: 'スイート登録', runSelected: '選択実行', openReport: 'レポートを開く', toggleEntry: '選択更新', toggleEnabled: '有効状態更新' }[kind];
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function escapeAttribute(value: string): string { return escapeHtml(value); }
function errorMessage(error: unknown): string { return error instanceof Error ? error.message : String(error); }
function createNonce(): string { return Math.random().toString(36).slice(2) + Date.now().toString(36); }
function vscodeApi(): typeof import('vscode') { return require('vscode') as typeof import('vscode'); }

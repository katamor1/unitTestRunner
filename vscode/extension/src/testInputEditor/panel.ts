import * as path from 'path';
import * as vscode from 'vscode';

import { openReport } from '../reports/reportOpener';
import {
  parseTestInputEditorMessage,
  TestInputApplyResult,
  TestInputEditorMessage,
  TestInputFormModel,
} from './contracts';
import { TestInputCliError, TestInputFormClient } from './cliClient';
import {
  buildChangeDrafts,
  createDraftState,
  discardDrafts,
  editControl,
  mergeReloadedModel,
  resolveConflict,
  selectCase,
  setItemConfirmed,
  TestInputEditorDraftState,
  dirtyCount,
} from './draftState';
import { renderTestInputEditor } from './renderer';

export interface TestInputEditorPanelDependencies {
  client: TestInputFormClient;
  onSaved?: (workspace: string, result: TestInputApplyResult, model?: TestInputFormModel) => Promise<void> | void;
}

export class TestInputEditorPanel {
  private static readonly panels = new Map<string, TestInputEditorPanel>();
  private state?: TestInputEditorDraftState;
  private loading = false;

  static async open(
    context: vscode.ExtensionContext,
    workspace: string,
    dependencies: TestInputEditorPanelDependencies,
  ): Promise<TestInputEditorPanel> {
    const key = normalizeWorkspace(workspace);
    const existing = this.panels.get(key);
    if (existing) {
      existing.panel.reveal(vscode.ViewColumn.Active, false);
      await existing.reload(true);
      return existing;
    }
    const panel = vscode.window.createWebviewPanel(
      'unitTestRunner.testInputEditor',
      '未確定テスト項目',
      vscode.ViewColumn.Active,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    const instance = new TestInputEditorPanel(context, workspace, panel, dependencies, key);
    this.panels.set(key, instance);
    context.subscriptions.push(panel);
    panel.onDidDispose(() => this.panels.delete(key), undefined, context.subscriptions);
    panel.webview.onDidReceiveMessage((message: unknown) => {
      void instance.receive(message);
    }, undefined, context.subscriptions);
    await instance.reload(false);
    return instance;
  }

  private constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly workspace: string,
    private readonly panel: vscode.WebviewPanel,
    private readonly dependencies: TestInputEditorPanelDependencies,
    private readonly key: string,
  ) {
    void this.context;
    void this.key;
  }

  private async receive(raw: unknown): Promise<void> {
    let message: TestInputEditorMessage;
    try {
      message = parseTestInputEditorMessage(raw);
    } catch (error) {
      void vscode.window.showErrorMessage(`UnitTestRunner: 編集画面から不正な操作を受信しました。 ${errorMessage(error)}`);
      return;
    }
    if (this.loading) {
      return;
    }
    if (message.type === 'reload') {
      await this.reload(true);
      return;
    }
    if (!this.state) {
      return;
    }
    if (message.type === 'selectCase') {
      this.state = selectCase(this.state, message.caseId);
      this.render();
    } else if (message.type === 'editControl') {
      this.state = editControl(this.state, message.itemId, message.control, message.value);
      this.render();
    } else if (message.type === 'setConfirmed') {
      this.state = setItemConfirmed(this.state, message.itemId, message.confirmed);
      this.render();
    } else if (message.type === 'discard') {
      const selected = await vscode.window.showWarningMessage(
        '未保存の入力内容を破棄しますか？',
        { modal: true },
        '変更を破棄',
      );
      if (selected === '変更を破棄') {
        this.state = discardDrafts(this.state);
        this.render();
      }
    } else if (message.type === 'save') {
      await this.save();
    } else if (message.type === 'openCanonical') {
      await openReport(path.join(this.workspace, 'reports', 'test_spec.json'));
    } else if (message.type === 'resolveConflict') {
      this.state = resolveConflict(this.state, message.itemId, message.choice);
      this.render();
    }
  }

  private async reload(preserveDraft: boolean): Promise<void> {
    if (this.loading) {
      return;
    }
    this.loading = true;
    this.panel.title = '未確定テスト項目 — 読み込み中';
    try {
      const model = await this.dependencies.client.load(this.workspace, false);
      this.state = preserveDraft && this.state
        ? mergeReloadedModel(this.state, model)
        : createDraftState(model);
      this.render();
    } catch (error) {
      this.panel.webview.html = renderLoadError(errorMessage(error), createNonce());
      this.panel.title = '未確定テスト項目 — エラー';
      void vscode.window.showErrorMessage(`UnitTestRunner: テスト入力フォームを開けません。 ${errorMessage(error)}`);
    } finally {
      this.loading = false;
    }
  }

  private async save(): Promise<void> {
    if (!this.state) {
      return;
    }
    const changes = buildChangeDrafts(this.state);
    if (changes.length === 0) {
      void vscode.window.showInformationMessage('UnitTestRunner: 保存する変更はありません。');
      return;
    }
    this.loading = true;
    this.panel.title = '未確定テスト項目 — 保存中';
    try {
      const result = await this.dependencies.client.apply(this.workspace, this.state.model.revision, changes);
      let model: TestInputFormModel;
      try {
        model = await this.dependencies.client.load(this.workspace, false);
      } catch (reloadError) {
        this.state = undefined;
        await this.dependencies.onSaved?.(this.workspace, result, undefined);
        this.panel.title = '未確定テスト項目 — 保存済み / 再読込エラー';
        this.panel.webview.html = renderLoadError(
          `入力内容は保存されましたが、最新状態を再読み込みできませんでした。［再読み込み］を実行してください。 ${errorMessage(reloadError)}`,
          createNonce(),
        );
        void vscode.window.showWarningMessage('UnitTestRunner: 入力内容は保存されましたが、最新状態の再読み込みに失敗しました。');
        return;
      }
      this.state = createDraftState(model);
      await this.dependencies.onSaved?.(this.workspace, result, model);
      this.render();
      const promotion = result.promotedCaseIds.length ? ` ${result.promotedCaseIds.length}ケースを実行対象へ移動しました。` : '';
      const viewWarning = result.viewsWritten ? '' : ' Markdown/CSVの再生成には失敗しています。';
      void vscode.window.showInformationMessage(`UnitTestRunner: ${result.updatedItemCount}項目を保存しました。${promotion}${viewWarning}`);
    } catch (error) {
      if (error instanceof TestInputCliError && (
        error.code === 'test_input_revision_conflict'
        || error.code === 'test_input_subject_conflict'
      )) {
        try {
          const latest = await this.dependencies.client.load(this.workspace, false);
          this.state = mergeReloadedModel(this.state, latest);
          this.render();
          void vscode.window.showWarningMessage('UnitTestRunner: テスト仕様が別の操作で更新されています。下書きを保持したまま競合項目を表示しました。');
        } catch (reloadError) {
          void vscode.window.showErrorMessage(`UnitTestRunner: 競合後の再読み込みに失敗しました。 ${errorMessage(reloadError)}`);
        }
      } else {
        void vscode.window.showErrorMessage(`UnitTestRunner: 入力内容を保存できません。 ${errorMessage(error)}`);
        this.render();
      }
    } finally {
      this.loading = false;
    }
  }

  private render(): void {
    if (!this.state) {
      return;
    }
    this.panel.title = `未確定テスト項目${dirtyCount(this.state) > 0 ? ' *' : ''}`;
    this.panel.webview.html = renderTestInputEditor(this.state, createNonce());
  }
}

export function renderTestInputLoadError(message: string, nonce: string): string {
  const safe = escapeHtml(message);
  return `<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';"><style nonce="${nonce}">body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);background:var(--vscode-editor-background);padding:24px}.error{border-left:4px solid var(--vscode-inputValidation-errorBorder);padding:10px;background:var(--vscode-inputValidation-errorBackground)}button{margin-top:14px;border:0;padding:7px 12px;color:var(--vscode-button-foreground);background:var(--vscode-button-background);cursor:pointer}</style></head><body><h1>テスト入力フォームを開けません</h1><div class="error">${safe}</div><p>テスト仕様が古い場合は、現在の関数を再解析してください。</p><button id="reload">再読み込み</button><script nonce="${nonce}">const vscode=acquireVsCodeApi();document.getElementById('reload')?.addEventListener('click',()=>vscode.postMessage({type:'reload'}));</script></body></html>`;
}

function renderLoadError(message: string, nonce: string): string {
  return renderTestInputLoadError(message, nonce);
}

function normalizeWorkspace(value: string): string {
  return path.resolve(value).toLowerCase();
}

function createNonce(): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let value = '';
  for (let index = 0; index < 32; index += 1) {
    value += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return value;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character] ?? character));
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

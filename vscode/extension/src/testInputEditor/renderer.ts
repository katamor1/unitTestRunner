import { TestInputFormCase, TestInputFormItem } from './contracts';
import {
  conflictCount,
  dirtyCount,
  draftSummary,
  isUnresolvedDraftValue,
  TestInputEditorDraftState,
} from './draftState';

const SECTION_NAMES: Readonly<Record<string, string>> = {
  input_assignment: '入力値',
  state_setup: '事前状態',
  stub_setup: 'スタブ設定',
  expected_observation: '期待値',
  precondition: '前提条件',
  execution_step: '実行手順',
  dependency_override: '依存関係',
};

const CONTROL_LABELS: Readonly<Record<string, string>> = {
  value_expression: '値（C式）',
  expected_expression: '期待値（C式）',
  call_behavior: '呼び出し動作',
  setup_method_hint: '設定方法',
  description: '説明',
  detail: '手順の詳細',
  mode: '依存関係モード',
  rationale: '理由',
  note: '補足',
};

const ITEM_KIND_LABELS: Readonly<Record<string, string>> = {
  input_assignment: '入力値',
  state_setup: '事前状態',
  stub_setup: 'スタブ設定',
  expected_observation: '期待値',
  precondition: '前提条件',
  execution_step: '実行手順',
  dependency_override: '依存関係',
};

export function renderTestInputEditor(state: TestInputEditorDraftState, nonce: string): string {
  const model = state.model;
  const cases = model.cases ?? [];
  const selected = cases.find((entry) => entry.caseId === state.selectedCaseId) ?? cases[0];
  const dirty = dirtyCount(state);
  const summary = draftSummary(state);
  const conflicts = conflictCount(state);
  const title = dirty > 0 ? `未確定テスト項目 *` : '未確定テスト項目';
  return `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${escapeAttribute(nonce)}'; script-src 'nonce-${escapeAttribute(nonce)}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${escapeHtml(title)}</title>
<style nonce="${escapeAttribute(nonce)}">
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; color: var(--vscode-foreground); background: var(--vscode-editor-background); font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); }
header { padding: 14px 18px; border-bottom: 1px solid var(--vscode-editorGroup-border); display: flex; gap: 16px; align-items: flex-start; justify-content: space-between; }
h1 { font-size: 17px; margin: 0 0 4px; }
.meta { color: var(--vscode-descriptionForeground); font-size: 12px; overflow-wrap: anywhere; }
.summary { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 9px; }
.badge { border: 1px solid var(--vscode-editorGroup-border); border-radius: 999px; padding: 3px 8px; font-size: 11px; }
.badge.blocking, .case-count.blocking { border-color: var(--vscode-inputValidation-warningBorder); color: var(--vscode-inputValidation-warningForeground, var(--vscode-foreground)); }
.layout { min-height: calc(100vh - 166px); display: grid; grid-template-columns: minmax(230px, 28%) 1fr; }
aside { border-right: 1px solid var(--vscode-editorGroup-border); padding: 10px; overflow: auto; }
.case { width: 100%; border: 0; border-left: 3px solid transparent; padding: 9px 10px; margin: 0 0 6px; text-align: left; color: var(--vscode-foreground); background: transparent; cursor: pointer; }
.case:hover { background: var(--vscode-list-hoverBackground); }
.case.selected { border-left-color: var(--vscode-focusBorder); background: var(--vscode-list-activeSelectionBackground); color: var(--vscode-list-activeSelectionForeground); }
.case-id { display: block; font-weight: 600; overflow-wrap: anywhere; }
.case-meta { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; font-size: 11px; color: var(--vscode-descriptionForeground); }
main { padding: 15px 18px 90px; overflow: auto; }
section.group { margin: 0 0 20px; }
section.group > h2 { font-size: 13px; color: var(--vscode-descriptionForeground); border-bottom: 1px solid var(--vscode-editorGroup-border); padding-bottom: 5px; }
.card { border: 1px solid var(--vscode-editorGroup-border); border-radius: 5px; padding: 12px; margin: 0 0 10px; }
.card.blocking { border-left: 4px solid var(--vscode-inputValidation-warningBorder); }
.card.conflict { border-color: var(--vscode-inputValidation-errorBorder); background: var(--vscode-inputValidation-errorBackground); }
.card-header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; margin-bottom: 9px; }
.card-title { font-weight: 600; }
.card-kind { color: var(--vscode-descriptionForeground); font-size: 11px; }
.control { display: grid; gap: 5px; margin: 0 0 10px; }
.control label { font-size: 12px; }
input[type="text"], textarea, select { width: 100%; color: var(--vscode-input-foreground); background: var(--vscode-input-background); border: 1px solid var(--vscode-input-border, transparent); padding: 6px 8px; font-family: var(--vscode-editor-font-family); }
textarea { min-height: 84px; resize: vertical; }
input:focus, textarea:focus, select:focus { outline: 1px solid var(--vscode-focusBorder); }
.suggestions { display: flex; flex-wrap: wrap; gap: 5px; }
button.suggestion { border: 1px solid var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); background: var(--vscode-button-secondaryBackground); padding: 3px 7px; cursor: pointer; }
.confirm { display: flex; gap: 7px; align-items: center; }
.warning { color: var(--vscode-inputValidation-warningForeground, var(--vscode-foreground)); background: var(--vscode-inputValidation-warningBackground); border-left: 3px solid var(--vscode-inputValidation-warningBorder); padding: 6px 8px; margin-top: 6px; }
.conflict-actions { display: flex; gap: 7px; margin-top: 8px; }
.empty { color: var(--vscode-descriptionForeground); padding: 32px 12px; text-align: center; }
footer { position: fixed; z-index: 3; left: 0; right: 0; bottom: 0; border-top: 1px solid var(--vscode-editorGroup-border); background: var(--vscode-editor-background); padding: 10px 18px; display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.actions { display: flex; gap: 8px; }
button.action { border: 0; padding: 7px 12px; color: var(--vscode-button-foreground); background: var(--vscode-button-background); cursor: pointer; }
button.action.secondary { color: var(--vscode-button-secondaryForeground); background: var(--vscode-button-secondaryBackground); }
button.action:disabled { opacity: .55; cursor: default; }
@media (max-width: 760px) { .layout { grid-template-columns: 1fr; } aside { border-right: 0; border-bottom: 1px solid var(--vscode-editorGroup-border); max-height: 220px; } }
</style>
</head>
<body>
<header>
<div><h1>${escapeHtml(model.functionName)} — 未確定テスト項目</h1><div class="meta">revision ${model.revision} / ${escapeHtml(model.specSha256.slice(0, 12))}…</div>
<div class="summary">
<span class="badge">要確認 ${summary.attentionCount}</span>
<span class="badge">未入力 ${summary.unresolvedCount}</span>
<span class="badge">未確認 ${summary.unconfirmedCount}</span>
<span class="badge blocking">実行阻害 ${summary.executionBlockingCount}</span>
<span class="badge">警告 ${summary.warningCount}</span>
</div></div>
<div class="actions"><button class="action secondary" data-action="reload">最新状態を読み込む</button><button class="action secondary" data-action="open-canonical">test_spec.jsonを開く</button></div>
</header>
${cases.length === 0 ? renderEmpty() : `<div class="layout"><aside>${cases.map((entry) => renderCaseButton(entry, selected?.caseId, state)).join('')}</aside><main>${selected ? renderCase(selected, state) : ''}</main></div>`}
<footer><div>${dirty}件の未保存変更${conflicts ? ` / ${conflicts}件の競合` : ''}</div><div class="actions"><button class="action secondary" data-action="discard" ${dirty === 0 ? 'disabled' : ''}>変更を破棄</button><button class="action" data-action="save" ${dirty === 0 || conflicts > 0 ? 'disabled' : ''}>保存して反映</button></div></footer>
<script nonce="${escapeAttribute(nonce)}">
const vscode = acquireVsCodeApi();
const post = (message) => vscode.postMessage(message);
document.addEventListener('click', (event) => {
  const target = event.target instanceof Element ? event.target.closest('button') : null;
  if (!target) return;
  const action = target.getAttribute('data-action');
  if (action === 'select-case') post({type:'selectCase', caseId: target.getAttribute('data-case-id')});
  if (action === 'save') post({type:'save'});
  if (action === 'discard') post({type:'discard'});
  if (action === 'reload') post({type:'reload'});
  if (action === 'open-canonical') post({type:'openCanonical'});
  if (action === 'suggest') {
    const itemId = target.getAttribute('data-item-id');
    const control = target.getAttribute('data-control');
    const value = target.getAttribute('data-value') || '';
    const input = document.querySelector('[data-item-id="' + CSS.escape(itemId || '') + '"][data-control="' + CSS.escape(control || '') + '"]');
    if (input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement || input instanceof HTMLSelectElement) input.value = value;
    post({type:'editControl', itemId, control, value});
  }
  if (action === 'resolve-conflict') post({type:'resolveConflict', itemId: target.getAttribute('data-item-id'), choice: target.getAttribute('data-choice')});
});
document.addEventListener('change', (event) => {
  const target = event.target;
  if (target instanceof HTMLInputElement && target.type === 'checkbox' && target.hasAttribute('data-confirm-item')) {
    post({type:'setConfirmed', itemId: target.getAttribute('data-confirm-item'), confirmed: target.checked});
    return;
  }
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) {
    const itemId = target.getAttribute('data-item-id'); const control = target.getAttribute('data-control');
    if (itemId && control) post({type:'editControl', itemId, control, value: target.value});
  }
});
</script>
</body></html>`;
}

function renderEmpty(): string {
  return '<div class="empty"><p>現在、入力が必要な項目はありません。</p><button class="action secondary" data-action="open-canonical">test_spec.jsonを開く</button></div>';
}

function renderCaseButton(entry: TestInputFormCase, selectedId: string | undefined, state: TestInputEditorDraftState): string {
  const items = entry.items;
  const unresolved = items.filter((item) => item.controls.some((control) => control.requiredForConfirmation && isUnresolvedDraftValue(state.drafts[item.itemId]?.values[control.name]))).length;
  const unconfirmed = items.filter((item) => !state.drafts[item.itemId]?.confirmed).length;
  const warnings = items.filter((item) => item.warnings.length > 0).length;
  const blocking = items.filter((item) => item.blocking && item.controls.some((control) => control.requiredForConfirmation && isUnresolvedDraftValue(state.drafts[item.itemId]?.values[control.name]))).length;
  return `<button class="case ${entry.caseId === selectedId ? 'selected' : ''}" data-action="select-case" data-case-id="${escapeAttribute(entry.caseId)}"><span class="case-id">${escapeHtml(entry.caseId)}</span><span class="case-meta"><span>未入力 ${unresolved}</span><span>未確認 ${unconfirmed}</span><span>警告 ${warnings}</span>${blocking ? `<span class="case-count blocking">阻害 ${blocking}</span>` : ''}</span></button>`;
}

function renderCase(entry: TestInputFormCase, state: TestInputEditorDraftState): string {
  const groups = new Map<string, TestInputFormItem[]>();
  for (const item of entry.items) {
    const key = SECTION_NAMES[item.kind] ? item.kind : 'other';
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  const order = [...Object.keys(SECTION_NAMES), 'other'];
  return `<div class="meta">${entry.location === 'test_cases' ? '実行対象' : '追加候補'}${entry.promotionEligible ? ' / 入力完了後に昇格可能' : ''}</div>${order.filter((key) => groups.has(key)).map((key) => `<section class="group"><h2>${escapeHtml(SECTION_NAMES[key] ?? 'その他のレビュー項目')}</h2>${groups.get(key)!.map((item) => renderItem(item, state)).join('')}</section>`).join('')}`;
}

function renderItem(item: TestInputFormItem, state: TestInputEditorDraftState): string {
  const draft = state.drafts[item.itemId];
  if (!draft) return '';
  const classes = ['card', item.blocking ? 'blocking' : '', draft.conflict ? 'conflict' : ''].filter(Boolean).join(' ');
  return `<article class="${classes}"><div class="card-header"><div><div class="card-title">${escapeHtml(item.label)}</div><div class="card-kind">${escapeHtml(ITEM_KIND_LABELS[item.kind] ?? item.kind)}${draft.dirty ? ' / 未保存' : ''}</div></div><label class="confirm"><input type="checkbox" data-confirm-item="${escapeAttribute(item.itemId)}" ${draft.confirmed ? 'checked' : ''} ${!item.editable || draft.conflict ? 'disabled' : ''}>確認済み</label></div>
${item.controls.map((control) => renderControl(item, control.name, state)).join('')}
${item.warnings.map((warning) => `<div class="warning">${escapeHtml(warning.message)}</div>`).join('')}
${draft.conflict ? `<div class="warning">${draft.orphaned ? '項目が最新仕様に存在しません。' : '最新仕様でも同じ項目が変更されています。'} 自動上書きは行いません。</div><div class="conflict-actions"><button class="action secondary" data-action="resolve-conflict" data-item-id="${escapeAttribute(item.itemId)}" data-choice="latest">最新値を使う</button>${draft.orphaned ? '' : `<button class="action" data-action="resolve-conflict" data-item-id="${escapeAttribute(item.itemId)}" data-choice="draft">下書きを採用</button>`}</div>` : ''}</article>`;
}

function renderControl(item: TestInputFormItem, controlName: string, state: TestInputEditorDraftState): string {
  const control = item.controls.find((entry) => entry.name === controlName)!;
  const value = state.drafts[item.itemId]?.values[control.name] ?? '';
  const attrs = `data-item-id="${escapeAttribute(item.itemId)}" data-control="${escapeAttribute(control.name)}" ${!item.editable || state.drafts[item.itemId]?.conflict ? 'disabled' : ''}`;
  let input: string;
  if (control.controlKind === 'multiline') {
    input = `<textarea ${attrs}>${escapeHtml(value)}</textarea>`;
  } else if (control.controlKind === 'enum') {
    input = `<select ${attrs}>${control.enumValues.map((entry) => `<option value="${escapeAttribute(entry)}" ${entry === value ? 'selected' : ''}>${escapeHtml(entry)}</option>`).join('')}</select>`;
  } else {
    input = `<input type="text" value="${escapeAttribute(value)}" ${attrs}>`;
  }
  return `<div class="control"><label>${escapeHtml(CONTROL_LABELS[control.name] ?? control.name)}${control.requiredForConfirmation ? ' *' : ''}</label>${input}${control.suggestions.length ? `<div class="suggestions">${control.suggestions.map((suggestion) => `<button class="suggestion" data-action="suggest" data-item-id="${escapeAttribute(item.itemId)}" data-control="${escapeAttribute(control.name)}" data-value="${escapeAttribute(suggestion.value)}" title="${escapeAttribute(`${suggestion.source} / ${suggestion.confidence}`)}">${escapeHtml(suggestion.label)}</button>`).join('')}</div>` : ''}</div>`;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character] ?? character));
}

function escapeAttribute(value: string): string {
  return escapeHtml(value).replace(/\r?\n/g, '&#10;');
}

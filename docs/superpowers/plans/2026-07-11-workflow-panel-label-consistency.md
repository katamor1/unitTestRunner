# Workflow Panel Label Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Workflowパネルの簡易表示と詳細表示で、状態ラベル、工程見出し、説明、操作ボタンの役割を統一し、完了済み操作を「再実行／再生成」として表示する。

**Architecture:** `WorkflowAction` に完了後ラベル `repeatLabel` を追加し、`workflowPanelBase.ts` の単一の表示解決関数でラベル、Primary強調、非表示判定を決める。簡易表示と詳細表示は同じ解決関数を利用し、`workflowPanel.ts` にあるHTML文字列置換ラッパーは不要になるため単純な再エクスポートへ戻す。

**Tech Stack:** TypeScript 5、VS Code Webview API、Node.js built-in test runner、既存 `npm.cmd test` ビルド・テストフロー

## Global Constraints

- 状態表示は `done = 完了`、`current = 次の操作`、`pending = 未実施` とする。
- `現在の推奨` はユーザー向けHTMLへ出力しない。
- ステップ番号は工程見出しだけに付け、操作ボタンには付けない。
- 完了済みコマンドは `repeatLabel` があれば再実行・再生成ラベルを表示する。
- レポートやファイルを開く操作は完了後も同じ「〜を開く」ラベルを使う。
- `保存済みとして確定` は完了済み工程では表示しない。
- Primary強調は `current` 工程の `primary: true` アクションだけに付ける。
- `danger` 属性とbuild/test実行前の確認ダイアログは変更しない。
- Workflow工程順序、コマンドID、状態遷移、pending工程の実行可否は変更しない。
- 表示切替は `簡易` / `詳細` とし、旧表示名はユーザー向けHTMLへ出力しない。

---

## File Structure

- `vscode/extension/src/workflow/workflowState.ts`
  - `WorkflowStepStatus` と `WorkflowAction.repeatLabel` の型定義を持つ。
  - 詳細Workflowの各コマンドに初回ラベルと完了後ラベルを定義する。
- `vscode/extension/src/workflow/workflowPanelBase.ts`
  - 簡易Workflowの文言を定義する。
  - 状態ラベルとアクション表示を一元的に解決する。
  - 簡易表示・詳細表示を同じレンダリングポリシーで描画する。
- `vscode/extension/src/workflow/workflowPanel.ts`
  - `workflowPanelBase.ts` の公開APIをそのまま再エクスポートする。
  - HTML文字列の事後置換を行わない。
- `vscode/extension/src/test/workflowPanel.test.ts`
  - 簡易表示・詳細表示の状態別ラベル、再実行ラベル、Primary強調、確定ボタン非表示を検証する。
- `vscode/extension/README.md`
  - 表示切替と状態別ボタン表現を利用者向けに記載する。

---

### Task 1: 状態別アクション表示モデルを追加する

**Files:**
- Modify: `vscode/extension/src/workflow/workflowState.ts:74-95`
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts:10-22, 175-185`
- Test: `vscode/extension/src/test/workflowPanel.test.ts`

**Interfaces:**
- Produces: `WorkflowStepStatus = 'done' | 'current' | 'pending'`
- Produces: `WorkflowAction.repeatLabel?: string`
- Produces: `resolveWorkflowActionPresentation(action: WorkflowAction, status?: WorkflowStepStatus): WorkflowActionPresentation`
- Produces: `workflowStatusLabel(status: WorkflowStepStatus): string`
- Consumes: existing `WorkflowAction.primary`, `WorkflowAction.danger`, and `WorkflowAction.kind`

- [ ] **Step 1: Write failing unit tests for the presentation resolver**

Add these imports to `vscode/extension/src/test/workflowPanel.test.ts`:

```ts
import {
  renderWorkflowHtml,
  resolveWorkflowActionPresentation,
  SIMPLE_SECONDARY_ACTIONS,
  SIMPLE_WORKFLOW_ACTIONS,
  workflowStatusLabel,
} from '../workflow/workflowPanel';
import { WorkflowAction } from '../workflow/workflowState';
```

Add a focused test block:

```ts
describe('workflow action presentation', () => {
  const action: WorkflowAction = {
    id: 'build',
    kind: 'command',
    label: 'ビルドを実行',
    repeatLabel: 'ビルドを再実行',
    primary: true,
    danger: true,
  };

  it('uses the repeat label for completed command actions', () => {
    const presentation = resolveWorkflowActionPresentation(action, 'done');
    assert.equal(presentation.label, 'ビルドを再実行');
    assert.equal(presentation.primary, false);
    assert.equal(presentation.hidden, false);
    assert.match(presentation.classes, /danger/);
    assert.doesNotMatch(presentation.classes, /primary/);
  });

  it('only applies primary emphasis to the current action', () => {
    assert.equal(resolveWorkflowActionPresentation(action, 'current').primary, true);
    assert.equal(resolveWorkflowActionPresentation(action, 'pending').primary, false);
  });

  it('hides a completed confirmation action', () => {
    const confirmation: WorkflowAction = {
      id: 'confirm',
      kind: 'confirmStep',
      label: '保存済みとして確定',
    };
    assert.equal(resolveWorkflowActionPresentation(confirmation, 'done').hidden, true);
    assert.equal(resolveWorkflowActionPresentation(confirmation, 'current').hidden, false);
  });

  it('uses the same status labels in both panel modes', () => {
    assert.equal(workflowStatusLabel('done'), '完了');
    assert.equal(workflowStatusLabel('current'), '次の操作');
    assert.equal(workflowStatusLabel('pending'), '未実施');
  });
});
```

- [ ] **Step 2: Run the targeted test and verify it fails**

Run:

```powershell
cd vscode/extension
npm.cmd run compile
node --test dist/test/workflowPanel.test.js
```

Expected: TypeScript compilation fails because `repeatLabel`, `resolveWorkflowActionPresentation`, and `workflowStatusLabel` do not exist.

- [ ] **Step 3: Add the shared status and action presentation types**

In `vscode/extension/src/workflow/workflowState.ts`, add the status alias and use it from `WorkflowStepView`:

```ts
export type WorkflowStepStatus = 'done' | 'current' | 'pending';

export interface WorkflowAction {
  id: string;
  kind: WorkflowActionKind;
  label: string;
  repeatLabel?: string;
  commandId?: string;
  reportKey?: keyof ReportPaths;
  stepId?: WorkflowStepId;
  primary?: boolean;
  danger?: boolean;
}

export interface WorkflowStepView extends WorkflowStepDefinition {
  status: WorkflowStepStatus;
}
```

In `vscode/extension/src/workflow/workflowPanelBase.ts`, import `WorkflowStepStatus` and add:

```ts
export interface WorkflowActionPresentation {
  label: string;
  classes: string;
  primary: boolean;
  hidden: boolean;
}

export function workflowStatusLabel(status: WorkflowStepStatus): string {
  if (status === 'done') {
    return '完了';
  }
  if (status === 'current') {
    return '次の操作';
  }
  return '未実施';
}

export function resolveWorkflowActionPresentation(
  action: WorkflowAction,
  status?: WorkflowStepStatus,
): WorkflowActionPresentation {
  const label = status === 'done' && action.repeatLabel ? action.repeatLabel : action.label;
  const primary = status === 'current' && action.primary === true;
  const hidden = status === 'done' && action.kind === 'confirmStep';
  const classes = [primary ? 'primary' : '', action.danger ? 'danger' : '']
    .filter(Boolean)
    .join(' ');
  return { label, classes, primary, hidden };
}
```

- [ ] **Step 4: Update `renderAction` to use the shared resolver**

Replace the existing renderer in `workflowPanelBase.ts` with:

```ts
function renderAction(action: WorkflowAction, status?: WorkflowStepStatus): string {
  const presentation = resolveWorkflowActionPresentation(action, status);
  if (presentation.hidden) {
    return '';
  }
  const attributes = [
    `data-kind="${escapeAttribute(action.kind)}"`,
    `data-label="${escapeAttribute(presentation.label)}"`,
    action.commandId ? `data-command-id="${escapeAttribute(action.commandId)}"` : '',
    action.reportKey ? `data-report-key="${escapeAttribute(String(action.reportKey))}"` : '',
    action.stepId ? `data-step-id="${escapeAttribute(action.stepId)}"` : '',
  ].filter(Boolean).join(' ');
  return `<button class="${presentation.classes}" ${attributes}>${escapeHtml(presentation.label)}</button>`;
}
```

- [ ] **Step 5: Export the new helpers from `workflowPanel.ts`**

When `workflowPanel.ts` is simplified in Task 4 it will re-export these helpers. Until then, add them to its export list so the targeted test compiles:

```ts
export {
  resolveWorkflowActionPresentation,
  SIMPLE_SECONDARY_ACTIONS,
  SIMPLE_WORKFLOW_ACTIONS,
  resolveWorkflowReports,
  workflowStatusLabel,
} from './workflowPanelBase';
```

- [ ] **Step 6: Run the targeted test and verify it passes**

Run:

```powershell
cd vscode/extension
npm.cmd run compile
node --test dist/test/workflowPanel.test.js
```

Expected: the new presentation resolver tests pass; the existing panel HTML test may still fail until Tasks 2 and 3 update the rendered labels.

- [ ] **Step 7: Commit Task 1**

```bash
git add vscode/extension/src/workflow/workflowState.ts vscode/extension/src/workflow/workflowPanelBase.ts vscode/extension/src/workflow/workflowPanel.ts vscode/extension/src/test/workflowPanel.test.ts
git commit -m "Add state-aware workflow action presentation"
```

---

### Task 2: 詳細表示へ再実行ポリシーを適用する

**Files:**
- Modify: `vscode/extension/src/workflow/workflowState.ts:121-260`
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts:152-185`
- Test: `vscode/extension/src/test/workflowPanel.test.ts`

**Interfaces:**
- Consumes: `WorkflowAction.repeatLabel`
- Consumes: `resolveWorkflowActionPresentation(action, status)`
- Consumes: `workflowStatusLabel(status)`
- Produces: detailed panel HTML with state-aware action labels and no completed confirmation button

- [ ] **Step 1: Write a failing detailed-panel rendering test**

Add this helper to `workflowPanel.test.ts`:

```ts
function testSettings() {
  return buildSettingsViewModel(
    {
      cliPath: 'unit-test-runner',
      sourceRoot: 'C:\\work\\product',
      dswPath: 'C:\\work\\product\\Product.dsw',
      outputRoot: 'D:\\unit-test-output',
      defaultConfiguration: 'Win32 Debug',
    },
    'C:\\work\\product',
  );
}
```

Add this test:

```ts
it('applies the same status and repeat-label policy to the detailed panel', () => {
  const state: WorkflowState = {
    settingsReady: true,
    functionName: 'Control_Update',
    outputWorkspace: 'D:\\unit-test-output\\Control_Update',
    completedStepIds: ['settings', 'analyze', 'reviewDossier'],
  };
  const steps = buildWorkflowStepViews(state, EMPTY_REPORT_AVAILABILITY);
  const html = renderWorkflowHtml({} as never, state, testSettings(), steps, OPTIONAL_WORKFLOW_ACTIONS);

  assert.match(html, /現在関数の解析を再実行/);
  assert.match(html, /data-label="現在関数の解析を再実行"/);
  assert.match(html, /次の操作/);
  assert.match(html, /未実施/);
  assert.doesNotMatch(html, /現在の推奨/);

  const completedDossier = html.match(/<section class="step done">[\s\S]*?<\/section>/g)?.find((section) => section.includes('function_dossier.md')) ?? '';
  assert.doesNotMatch(completedDossier, /保存済みとして確定/);
});
```

- [ ] **Step 2: Run the targeted test and verify it fails**

Run:

```powershell
cd vscode/extension
npm.cmd run compile
node --test dist/test/workflowPanel.test.js
```

Expected: FAIL because detailed steps still render `現在の推奨`, command actions do not have `repeatLabel`, and completed confirmation actions are still rendered.

- [ ] **Step 3: Add repeat labels to detailed command actions**

Update only repeatable command definitions in `WORKFLOW_STEP_DEFINITIONS`:

```ts
{
  id: 'analyzeCurrent',
  kind: 'command',
  label: '現在関数を解析',
  repeatLabel: '現在関数の解析を再実行',
  commandId: 'unitTestRunner.analyzeCurrentFunction',
  primary: true,
},
{
  id: 'analyzeSelected',
  kind: 'command',
  label: '選択関数を解析',
  repeatLabel: '選択関数の解析を再実行',
  commandId: 'unitTestRunner.analyzeSelectedFunction',
},
```

Apply the same property to these actions:

```ts
{ id: 'generateTestDesign', repeatLabel: 'テスト設計を再生成' }
{ id: 'generateHarnessSkeleton', repeatLabel: 'ハーネスを再生成' }
{ id: 'buildProbeDryRun', repeatLabel: 'dry-runを再実行' }
{ id: 'runBuildProbe', repeatLabel: 'ビルドプローブを再実行' }
{ id: 'runTests', repeatLabel: 'テストを再実行' }
{ id: 'prepareEvidence', repeatLabel: 'エビデンスを再生成' }
```

Keep each action's existing `kind`, `commandId`, `primary`, and `danger` fields unchanged.

- [ ] **Step 4: Pass the detailed step status into action rendering**

Replace the detailed step renderer with:

```ts
function renderStep(step: WorkflowStepViews[number]): string {
  return `<section class="step ${step.status}">
  <span class="status">${workflowStatusLabel(step.status)}</span>
  <h3>${escapeHtml(step.title)}</h3>
  <p>${escapeHtml(step.purpose)}</p>
  <p class="required">${escapeHtml(step.requiredAction)}</p>
  <div class="actions">${step.actions.map((action) => renderAction(action, step.status)).join('')}</div>
</section>`;
}
```

Keep optional actions state-independent:

```ts
<div class="actions">${optionalActions.map((action) => renderAction(action)).join('')}</div>
```

- [ ] **Step 5: Run the targeted test and verify it passes**

Run:

```powershell
cd vscode/extension
npm.cmd run compile
node --test dist/test/workflowPanel.test.js
```

Expected: the detailed-panel test passes. Completed command labels use `repeatLabel`, current status reads `次の操作`, and completed confirmation actions are absent.

- [ ] **Step 6: Commit Task 2**

```bash
git add vscode/extension/src/workflow/workflowState.ts vscode/extension/src/workflow/workflowPanelBase.ts vscode/extension/src/test/workflowPanel.test.ts
git commit -m "Align detailed workflow action labels with state"
```

---

### Task 3: 簡易4ステップの文言と状態別ボタンを統一する

**Files:**
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts:43-48, 75-150`
- Test: `vscode/extension/src/test/workflowPanel.test.ts`

**Interfaces:**
- Consumes: `resolveWorkflowActionPresentation(action, status)` through `renderAction`
- Produces: approved four-step headings, descriptions, initial labels, and completed labels

- [ ] **Step 1: Replace the existing simple-panel assertions with exact policy assertions**

Update the first panel test so it verifies headings and state-aware buttons separately:

```ts
it('renders the simple panel with consistent headings and action labels', () => {
  const state: WorkflowState = {
    settingsReady: true,
    functionName: 'Control_Update',
    outputWorkspace: 'D:\\unit-test-output\\Control_Update',
    completedStepIds: ['settings', 'analyze', 'generateHarnessSkeleton', 'buildProbeRun', 'runTests'],
  };
  const steps = buildWorkflowStepViews(state, EMPTY_REPORT_AVAILABILITY);
  const html = renderWorkflowHtml({} as never, state, testSettings(), steps, OPTIONAL_WORKFLOW_ACTIONS);

  assert.match(html, /<h3>1\. Quick Check<\/h3>/);
  assert.match(html, /<h3>2\. テストソース確認<\/h3>/);
  assert.match(html, /<h3>3\. ビルド<\/h3>/);
  assert.match(html, /<h3>4\. テスト実行<\/h3>/);

  assert.match(html, />Quick Checkを再実行<\/button>/);
  assert.match(html, />テストソースを開く<\/button>/);
  assert.match(html, />ビルドを再実行<\/button>/);
  assert.match(html, />テストを再実行<\/button>/);

  assert.doesNotMatch(html, />[1-4]\. (?:Quick Check|テストソース|ビルド|テスト実行).*<\/button>/);
  assert.match(html, /data-label="Quick Checkを再実行"/);
  assert.match(html, /data-label="ビルドを再実行"/);
  assert.match(html, /data-label="テストを再実行"/);
});
```

Add a current-step emphasis test:

```ts
it('emphasizes only the current simple workflow action', () => {
  const state: WorkflowState = {
    settingsReady: true,
    functionName: 'Control_Update',
    outputWorkspace: 'D:\\unit-test-output\\Control_Update',
    completedStepIds: ['settings', 'analyze', 'generateHarnessSkeleton'],
  };
  const steps = buildWorkflowStepViews(state, EMPTY_REPORT_AVAILABILITY);
  const html = renderWorkflowHtml({} as never, state, testSettings(), steps, OPTIONAL_WORKFLOW_ACTIONS);

  const buildButton = html.match(/<button class="[^"]*"[^>]*>ビルドを実行<\/button>/)?.[0] ?? '';
  const quickButton = html.match(/<button class="[^"]*"[^>]*>Quick Checkを再実行<\/button>/)?.[0] ?? '';
  assert.match(buildButton, /class="[^"]*primary/);
  assert.doesNotMatch(quickButton, /class="[^"]*primary/);
});
```

- [ ] **Step 2: Run the targeted test and verify it fails**

Run:

```powershell
cd vscode/extension
npm.cmd run compile
node --test dist/test/workflowPanel.test.js
```

Expected: FAIL because simple action labels still contain numbers, headings use verb-heavy wording, and status is not passed into `renderAction`.

- [ ] **Step 3: Replace simple action definitions with operation-only labels**

Replace `SIMPLE_WORKFLOW_ACTIONS` with:

```ts
export const SIMPLE_WORKFLOW_ACTIONS: WorkflowAction[] = [
  {
    id: 'quickCheckCurrent',
    kind: 'command',
    label: 'Quick Checkを実行',
    repeatLabel: 'Quick Checkを再実行',
    commandId: 'unitTestRunner.quickCheckCurrentFunction',
    primary: true,
  },
  {
    id: 'openGeneratedTestSource',
    kind: 'command',
    label: 'テストソースを開く',
    commandId: 'unitTestRunner.openGeneratedTestSource',
    primary: true,
  },
  {
    id: 'runBuildProbe',
    kind: 'command',
    label: 'ビルドを実行',
    repeatLabel: 'ビルドを再実行',
    commandId: 'unitTestRunner.runBuildProbe',
    primary: true,
    danger: true,
  },
  {
    id: 'runTests',
    kind: 'command',
    label: 'テストを実行',
    repeatLabel: 'テストを再実行',
    commandId: 'unitTestRunner.runTests',
    primary: true,
    danger: true,
  },
];
```

- [ ] **Step 4: Replace simple step titles and descriptions with the approved copy**

Use exactly:

```ts
return [
  {
    title: '1. Quick Check',
    description: '解析とテスト生成を行います。',
    status: statuses[0],
    action: SIMPLE_WORKFLOW_ACTIONS[0],
  },
  {
    title: '2. テストソース確認',
    description: '入力値・期待値・スタブ設定を確認し、必要に応じて修正します。',
    status: statuses[1],
    action: SIMPLE_WORKFLOW_ACTIONS[1],
  },
  {
    title: '3. ビルド',
    description: '生成・修正したテストをコンパイルし、リンク結果を確認します。',
    status: statuses[2],
    action: SIMPLE_WORKFLOW_ACTIONS[2],
  },
  {
    title: '4. テスト実行',
    description: '生成されたテストを実行し、結果レポートを確認します。',
    status: statuses[3],
    action: SIMPLE_WORKFLOW_ACTIONS[3],
  },
];
```

- [ ] **Step 5: Pass simple-step status into the shared action renderer**

Replace `renderSimpleFlowStep` with:

```ts
function renderSimpleFlowStep(step: SimpleFlowStepView): string {
  return `<section class="simple-flow-step ${step.status}">
  <span class="status">${workflowStatusLabel(step.status)}</span>
  <h3>${escapeHtml(step.title)}</h3>
  <p class="simple-meta">${escapeHtml(step.description)}</p>
  <div class="actions">${renderAction(step.action, step.status)}</div>
</section>`;
}
```

- [ ] **Step 6: Run the targeted test and verify it passes**

Run:

```powershell
cd vscode/extension
npm.cmd run compile
node --test dist/test/workflowPanel.test.js
```

Expected: all simple-panel label tests pass. Buttons contain no step number, completed commands use their repeat labels, and only the current action has the `primary` class.

- [ ] **Step 7: Commit Task 3**

```bash
git add vscode/extension/src/workflow/workflowPanelBase.ts vscode/extension/src/test/workflowPanel.test.ts
git commit -m "Align simple workflow headings and repeat actions"
```

---

### Task 4: 表示名ラッパーを除去し、文書と全体テストを仕上げる

**Files:**
- Modify: `vscode/extension/src/workflow/workflowPanelBase.ts:240-330`
- Modify: `vscode/extension/src/workflow/workflowPanel.ts`
- Modify: `vscode/extension/src/test/workflowPanel.test.ts`
- Modify: `vscode/extension/README.md:133-151`

**Interfaces:**
- Produces: `workflowPanel.ts` as a stable re-export boundary
- Produces: user-facing HTML with `簡易` / `詳細` terminology directly in the base renderer
- Consumes: all shared helpers completed in Tasks 1-3

- [ ] **Step 1: Add final terminology and regression assertions**

Add to the panel rendering test:

```ts
assert.match(html, />簡易<\/button>/);
assert.match(html, />詳細<\/button>/);
assert.match(html, />詳細パネルを表示<\/button>/);
assert.doesNotMatch(html, /従来/);
assert.doesNotMatch(html, /現在の推奨/);
```

Also assert that `data-label` and button text stay aligned:

```ts
for (const match of html.matchAll(/<button[^>]*data-label="([^"]+)"[^>]*>([^<]+)<\/button>/g)) {
  assert.equal(match[1], match[2]);
}
```

- [ ] **Step 2: Run the targeted test and verify it fails before base terminology cleanup**

Run:

```powershell
cd vscode/extension
npm.cmd run compile
node --test dist/test/workflowPanel.test.js
```

Expected: FAIL if the base renderer still contains the old display label and relies on `workflowPanel.ts` string replacement.

- [ ] **Step 3: Render `簡易` / `詳細` directly from `workflowPanelBase.ts`**

Replace the view switch and helper copy with:

```html
<div class="view-switch" role="group" aria-label="表示切替">
  <button type="button" data-view-mode="simple" class="active-mode">簡易</button>
  <button type="button" data-view-mode="full">詳細</button>
</div>
```

```html
<div class="simple-card">
  <h2>表示切替</h2>
  <p class="simple-meta">正式レビューや証跡確認の全工程を見る場合は詳細表示に切り替えます。</p>
  <button type="button" data-view-mode="full">詳細パネルを表示</button>
</div>
```

- [ ] **Step 4: Replace `workflowPanel.ts` with direct re-exports**

Use the entire file content below:

```ts
export {
  WorkflowPanelProvider,
  renderWorkflowHtml,
  resolveWorkflowActionPresentation,
  resolveWorkflowReports,
  SIMPLE_SECONDARY_ACTIONS,
  SIMPLE_WORKFLOW_ACTIONS,
  workflowStatusLabel,
} from './workflowPanelBase';
```

This removes private-view access and HTML post-processing.

- [ ] **Step 5: Update the README with the state/action policy**

In the Workflow panel section, replace the current display explanation with:

```markdown
Workflowパネルは `簡易` と `詳細` を切り替えられます。両表示で状態は `完了`、`次の操作`、`未実施` に統一されています。

工程番号は見出しだけに表示され、ボタンは `ビルドを実行` のような操作名を表示します。完了済みの実行操作は `ビルドを再実行`、`テストを再実行` のように変わります。レポートやファイルを開く操作は、状態にかかわらず `〜を開く` のままです。
```

- [ ] **Step 6: Run the full VS Code extension test suite**

Run:

```powershell
cd vscode/extension
npm.cmd test
```

Expected: TypeScript compilation succeeds and all `dist/test/*.test.js` tests pass.

- [ ] **Step 7: Scan runtime UI and user documentation for retired wording**

Run from the repository root:

```powershell
rg "従来|現在の推奨" vscode/extension/src/workflow vscode/extension/README.md docs/vscode_quick_check_usage.md docs/verification_build_toolchain.md
```

Expected: no matches in runtime UI or user-facing documents. The approved design/spec documents under `docs/superpowers/` are intentionally outside this scan because they describe the retired wording as a requirement.

- [ ] **Step 8: Commit Task 4**

```bash
git add vscode/extension/src/workflow/workflowPanelBase.ts vscode/extension/src/workflow/workflowPanel.ts vscode/extension/src/test/workflowPanel.test.ts vscode/extension/README.md
git commit -m "Unify simple and detailed workflow panel wording"
```

---

## Final Verification

- [ ] Run Python tests to ensure the extension-only change does not disturb repository-wide CI setup:

```powershell
py -m unittest discover -s tests -p "test_*.py"
```

Expected: all Python tests pass.

- [ ] Run VS Code extension tests once more from a clean compile:

```powershell
cd vscode/extension
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
npm.cmd test
```

Expected: compile succeeds and all Node tests pass.

- [ ] Verify the rendered UI manually in an Extension Development Host:

```powershell
cd vscode/extension
npm.cmd run compile
code --extensionDevelopmentPath="$PWD"
```

Expected:

- Initial display shows `簡易` selected and `詳細` as the alternate view.
- Completed Quick Check shows `Quick Checkを再実行`.
- Completed build shows `ビルドを再実行`.
- Completed test execution shows `テストを再実行`.
- `テストソースを開く` does not change after completion.
- Detailed display uses `完了` / `次の操作` / `未実施`.
- Completed detailed command steps show their repeat labels.
- Completed review steps do not show `保存済みとして確定`.
- No user-facing text contains `従来` or `現在の推奨`.

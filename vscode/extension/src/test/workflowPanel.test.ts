import * as assert from 'assert';
import { describe, it } from 'node:test';

import { buildSettingsViewModel } from '../config/settingsViewModel';
import {
  renderWorkflowHtml,
  resolveWorkflowActionPresentation,
  SIMPLE_SECONDARY_ACTIONS,
  SIMPLE_WORKFLOW_ACTIONS,
  workflowStatusLabel,
} from '../workflow/workflowPanel';
import {
  buildWorkflowStepViews,
  EMPTY_REPORT_AVAILABILITY,
  OPTIONAL_WORKFLOW_ACTIONS,
  WorkflowAction,
  WorkflowState,
} from '../workflow/workflowState';

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

function renderState(state: WorkflowState): string {
  const steps = buildWorkflowStepViews(state, EMPTY_REPORT_AVAILABILITY);
  return renderWorkflowHtml({} as never, state, testSettings(), steps, OPTIONAL_WORKFLOW_ACTIONS);
}

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


  it('shows the unresolved item count and blocking emphasis for the input editor', () => {
    const inputAction: WorkflowAction = {
      id: 'openTestInputEditor',
      kind: 'command',
      label: '未確定項目を入力',
      commandId: 'unitTestRunner.openTestInputEditor',
      primary: true,
    };
    const readyState: WorkflowState = {
      settingsReady: true,
      outputWorkspace: 'D:\\unit-test-output\\Control_Update',
      completedStepIds: ['settings', 'generateTestDesign'],
      testInputSummary: {
        status: 'ready',
        workspace: 'D:\\unit-test-output\\Control_Update',
        revision: 3,
        specSha256: 'a'.repeat(64),
        summary: {
          attentionCount: 7,
          unresolvedCount: 4,
          unconfirmedCount: 7,
          executionBlockingCount: 4,
          warningCount: 1,
        },
        updatedAt: '2026-07-19T00:00:00.000Z',
      },
    };

    const blocked = resolveWorkflowActionPresentation(inputAction, 'current', readyState);
    assert.equal(blocked.label, '未確定項目を入力（7件）');
    assert.match(blocked.classes, /primary/);
    assert.match(blocked.classes, /danger/);
    assert.equal(blocked.hidden, false);

    const completeState: WorkflowState = {
      ...readyState,
      testInputSummary: {
        status: 'ready',
        workspace: 'D:\\unit-test-output\\Control_Update',
        revision: 3,
        specSha256: 'a'.repeat(64),
        summary: {
          attentionCount: 0,
          unresolvedCount: 0,
          unconfirmedCount: 0,
          executionBlockingCount: 0,
          warningCount: 0,
        },
        updatedAt: '2026-07-19T00:00:00.000Z',
      },
    };
    const complete = resolveWorkflowActionPresentation(inputAction, 'current', completeState);
    assert.equal(complete.label, '入力内容を確認（0件）');
    assert.doesNotMatch(complete.classes, /danger/);
  });

  it('hides the editor until a test specification summary is available', () => {
    const inputAction: WorkflowAction = {
      id: 'openTestInputEditor',
      kind: 'command',
      label: '未確定項目を入力',
      commandId: 'unitTestRunner.openTestInputEditor',
    };
    const state: WorkflowState = {
      settingsReady: true,
      completedStepIds: ['settings'],
    };
    assert.equal(resolveWorkflowActionPresentation(inputAction, 'pending', state).hidden, true);
  });

  it('uses the same status labels in both panel modes', () => {
    assert.equal(workflowStatusLabel('done'), '完了');
    assert.equal(workflowStatusLabel('current'), '次の操作');
    assert.equal(workflowStatusLabel('pending'), '未実施');
  });
});

describe('UnitTestRunner workflow panel view modes', () => {
  it('renders the simple panel with consistent headings and completed action labels', () => {
    const state: WorkflowState = {
      settingsReady: true,
      functionName: 'Control_Update',
      outputWorkspace: 'D:\\unit-test-output\\Control_Update',
      completedStepIds: ['settings', 'analyze', 'generateHarnessSkeleton', 'buildProbeRun', 'runTests'],
    };

    const html = renderState(state);

    assert.match(html, /data-default-mode="simple"/);
    assert.match(html, /id="simplePanel" class="panel-view simple-panel"/);
    assert.match(html, /id="fullPanel" class="panel-view full-panel hidden"/);
    assert.match(html, /<h3>1\. クイックチェック<\/h3>/);
    assert.match(html, /<h3>2\. テストソースを確認<\/h3>/);
    assert.match(html, /<h3>3\. ビルド<\/h3>/);
    assert.match(html, /<h3>4\. テストを実行<\/h3>/);
    assert.match(html, />クイックチェックを再実行<\/button>/);
    assert.match(html, />テストソースを開く<\/button>/);
    assert.match(html, />ビルドを再実行<\/button>/);
    assert.match(html, />テストを再実行<\/button>/);
    assert.doesNotMatch(html, />[1-4]\. (?:クイックチェック|テストソース|ビルド|テスト).*<\/button>/);
    assert.match(html, /data-label="クイックチェックを再実行"/);
    assert.match(html, /data-label="ビルドを再実行"/);
    assert.match(html, /data-label="テストを再実行"/);
    assert.ok(SIMPLE_WORKFLOW_ACTIONS.some((item) => item.commandId === 'unitTestRunner.quickCheckCurrentFunction'));
    assert.ok(SIMPLE_WORKFLOW_ACTIONS.some((item) => item.commandId === 'unitTestRunner.openGeneratedTestSource'));
    assert.ok(SIMPLE_WORKFLOW_ACTIONS.some((item) => item.commandId === 'unitTestRunner.runBuildProbe'));
    assert.ok(SIMPLE_WORKFLOW_ACTIONS.some((item) => item.commandId === 'unitTestRunner.runTests'));
    assert.ok(SIMPLE_SECONDARY_ACTIONS.some((item) => item.commandId === 'unitTestRunner.runFullGateForCurrentFunction'));
  });

  it('emphasizes only the current simple workflow action', () => {
    const state: WorkflowState = {
      settingsReady: true,
      functionName: 'Control_Update',
      outputWorkspace: 'D:\\unit-test-output\\Control_Update',
      completedStepIds: ['settings'],
    };

    const html = renderState(state);
    const quickButton = html.match(/<button class="[^"]*"[^>]*>クイックチェックを実行<\/button>/)?.[0] ?? '';
    const buildButton = html.match(/<button class="[^"]*"[^>]*>ビルドを実行<\/button>/)?.[0] ?? '';

    assert.match(quickButton, /class="[^"]*primary/);
    assert.doesNotMatch(buildButton, /class="[^"]*primary/);
  });

  it('applies the same status and repeat-label policy to the detailed panel', () => {
    const state: WorkflowState = {
      settingsReady: true,
      functionName: 'Control_Update',
      outputWorkspace: 'D:\\unit-test-output\\Control_Update',
      completedStepIds: ['settings', 'analyze', 'reviewDossier'],
    };

    const html = renderState(state);

    assert.match(html, /現在の関数を再解析/);
    assert.match(html, /data-label="現在の関数を再解析"/);
    assert.match(html, /次の操作/);
    assert.match(html, /未実施/);
    assert.doesNotMatch(html, /現在の推奨/);

    const completedDossier = html.match(
      /<section class="step done">[\s\S]*?<h3>3\. 関数分析レポート（function_dossier\.md）を確認<\/h3>[\s\S]*?<\/section>/,
    )?.[0] ?? '';
    assert.ok(completedDossier);
    assert.doesNotMatch(completedDossier, /保存済みとして確定/);
  });

  it('renders the approved display terminology and keeps data labels aligned', () => {
    const state: WorkflowState = {
      settingsReady: true,
      functionName: 'Control_Update',
      outputWorkspace: 'D:\\unit-test-output\\Control_Update',
      completedStepIds: ['settings'],
    };

    const html = renderState(state);

    assert.match(html, />簡易<\/button>/);
    assert.match(html, />詳細<\/button>/);
    assert.match(html, />詳細パネルを表示<\/button>/);
    assert.doesNotMatch(html, /従来/);
    assert.doesNotMatch(html, /現在の推奨/);

    for (const match of html.matchAll(/<button[^>]*data-label="([^"]+)"[^>]*>([^<]+)<\/button>/g)) {
      assert.equal(match[1], match[2]);
    }
  });
});

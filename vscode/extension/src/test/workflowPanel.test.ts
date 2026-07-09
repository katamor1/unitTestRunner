import * as assert from 'assert';
import { describe, it } from 'node:test';

import { buildSettingsViewModel } from '../config/settingsViewModel';
import { renderWorkflowHtml, SIMPLE_SECONDARY_ACTIONS, SIMPLE_WORKFLOW_ACTIONS } from '../workflow/workflowPanel';
import { buildWorkflowStepViews, EMPTY_REPORT_AVAILABILITY, OPTIONAL_WORKFLOW_ACTIONS, WorkflowState } from '../workflow/workflowState';

describe('UnitTestRunner workflow panel view modes', () => {
  it('renders the simple panel first with a four-step test flow', () => {
    const settings = buildSettingsViewModel(
      {
        cliPath: 'unit-test-runner',
        sourceRoot: 'C:\\work\\product',
        dswPath: 'C:\\work\\product\\Product.dsw',
        outputRoot: 'D:\\unit-test-output',
        defaultConfiguration: 'Win32 Debug',
      },
      'C:\\work\\product',
    );
    const state: WorkflowState = {
      settingsReady: true,
      functionName: 'Control_Update',
      outputWorkspace: 'D:\\unit-test-output\\Control_Update',
      completedStepIds: ['settings'],
    };
    const steps = buildWorkflowStepViews(state, EMPTY_REPORT_AVAILABILITY);

    const html = renderWorkflowHtml({} as never, state, settings, steps, OPTIONAL_WORKFLOW_ACTIONS);

    assert.match(html, /data-default-mode="simple"/);
    assert.match(html, /id="simplePanel" class="panel-view simple-panel"/);
    assert.match(html, /id="fullPanel" class="panel-view full-panel hidden"/);
    assert.match(html, /4ステップで実行/);
    assert.match(html, /Quick Check/);
    assert.match(html, /テストソースを開く・修正/);
    assert.match(html, /ビルド実行/);
    assert.match(html, /テスト実行/);
    assert.match(html, /Full Gateへ進む/);
    assert.match(html, /従来パネルを表示/);
    assert.match(html, /現在の状態/);
    assert.ok(SIMPLE_WORKFLOW_ACTIONS.some((action) => action.commandId === 'unitTestRunner.quickCheckCurrentFunction'));
    assert.ok(SIMPLE_WORKFLOW_ACTIONS.some((action) => action.commandId === 'unitTestRunner.openGeneratedTestSource'));
    assert.ok(SIMPLE_WORKFLOW_ACTIONS.some((action) => action.commandId === 'unitTestRunner.runBuildProbe'));
    assert.ok(SIMPLE_WORKFLOW_ACTIONS.some((action) => action.commandId === 'unitTestRunner.runTests'));
    assert.ok(SIMPLE_SECONDARY_ACTIONS.some((action) => action.commandId === 'unitTestRunner.runFullGateForCurrentFunction'));
  });
});

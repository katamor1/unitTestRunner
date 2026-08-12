import * as assert from 'assert';
import { describe, it } from 'node:test';

import { buildSettingsViewModel } from '../config/settingsViewModel';
import { renderWorkflowHtml, resolveWorkflowActionPresentation, SIMPLE_WORKFLOW_ACTIONS } from '../workflow/workflowPanel';
import {
  buildWorkflowStepViews,
  createInitialWorkflowState,
  EMPTY_REPORT_AVAILABILITY,
  markWorkflowCommandFailed,
  markWorkflowCommandSucceeded,
  OPTIONAL_WORKFLOW_ACTIONS,
  WORKFLOW_STEP_DEFINITIONS,
} from '../workflow/workflowState';

function settingsModel() {
  return buildSettingsViewModel({
    cliPath: 'unit-test-runner', sourceRoot: 'C:\\work', dswPath: 'C:\\work\\P.dsw',
    outputRoot: 'D:\\out', defaultConfiguration: 'Win32 Debug',
  }, 'C:\\work');
}

function html(state = createInitialWorkflowState(true)): string {
  return renderWorkflowHtml({} as never, state, settingsModel(), buildWorkflowStepViews(state, EMPTY_REPORT_AVAILABILITY), OPTIONAL_WORKFLOW_ACTIONS);
}

describe('workflow panel', () => {
  it('presents a fixed nine-step one-way workflow without old meta-governance', () => {
    assert.equal(WORKFLOW_STEP_DEFINITIONS.length, 9);
    assert.deepEqual(WORKFLOW_STEP_DEFINITIONS.map((step) => step.id), [
      'settings', 'analyze', 'finalizeDossier', 'reviewTestSpec', 'prepareHarness',
      'buildProbeDryRun', 'buildProbeRun', 'runTests', 'complete',
    ]);
    const rendered = html();
    assert.match(rendered, /TestSpecをレビュー/);
    assert.match(rendered, /ハーネスを準備/);
    assert.doesNotMatch(rendered, /クイック|フルゲート|検証資料|evidence/);
  });

  it('marks only validated command success and leaves failures incomplete', () => {
    const initial = createInitialWorkflowState(true);
    const analyzed = markWorkflowCommandSucceeded(initial, { kind: 'analyze', outputWorkspace: 'D:\\out', sourcePath: 'C:\\src\\x.c', functionName: 'f' });
    assert.equal(analyzed.completedStepIds.includes('analyze'), true);
    const failed = markWorkflowCommandFailed(analyzed, 'timeout');
    assert.equal(failed.completedStepIds.includes('finalizeDossier'), false);
    assert.match(html(failed), /timeout/);
  });

  it('renders accessible named actions and focus restoration keys', () => {
    const rendered = html();
    assert.match(rendered, /aria-label="現在の関数を解析"/);
    assert.match(rendered, /data-focus-key="action:analyzeCurrent"/);
    assert.match(rendered, /role="alert"|role="status"/);
    assert.match(rendered, /requestAnimationFrame/);
  });

  it('keeps the simple view on direct product actions', () => {
    assert.deepEqual(SIMPLE_WORKFLOW_ACTIONS.map((item) => item.commandId), [
      'unitTestRunner.analyzeCurrentFunction',
      'unitTestRunner.openTestInputEditor',
      'unitTestRunner.runBuildProbe',
      'unitTestRunner.runTests',
    ]);
  });

  it('uses repeat labels only after a step succeeds', () => {
    const action = WORKFLOW_STEP_DEFINITIONS.find((step) => step.id === 'analyze')!.actions[0];
    assert.equal(resolveWorkflowActionPresentation(action, 'current').label, '現在の関数を解析');
    assert.equal(resolveWorkflowActionPresentation(action, 'done').label, '現在の関数を再解析');
  });
});

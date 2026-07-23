import * as assert from 'assert';
import { describe, it } from 'node:test';

import { resolveWorkflowActionPresentation } from '../workflow/workflowPanel';
import { WorkflowState } from '../workflow/workflowState';
import {
  blockerPrimaryActionTarget,
  clearWorkflowRunBlocked,
  markWorkflowBlockerAutoOpened,
  markWorkflowRunBlocked,
} from '../testExecutionBlockers/workflowIntegration';
import { VerifiedBlockedRun } from '../testExecutionBlockers/verification';

function blocker(): VerifiedBlockedRun {
  return {
    workspace: 'C:\\out\\sample',
    runId: 'run-001',
    count: 3,
    primaryAction: 'open_test_input_editor',
    primaryActionLabel: '未確定項目を入力',
    reportJson: 'C:\\out\\sample\\reports\\test_execution_blockers.json',
    reportMarkdown: 'C:\\out\\sample\\reports\\test_execution_blockers.md',
    reportSha256: 'a'.repeat(64),
    publicationDiagnostics: [],
    updatedAt: '2026-07-20T00:00:00.000Z',
  };
}

describe('blocked workflow integration', () => {
  it('moves the workflow back to the blocked test step and exposes report paths', () => {
    const state: WorkflowState = {
      settingsReady: true,
      outputWorkspace: 'C:\\out\\sample',
      reports: { workspace: 'C:\\out\\sample' },
      completedStepIds: ['settings', 'runTests', 'prepareEvidence', 'reviewEvidence', 'complete'],
    };

    const next = markWorkflowRunBlocked(state, blocker());

    assert.equal(next.testExecutionBlockers?.count, 3);
    assert.equal(next.reports?.testExecutionBlockersMd, blocker().reportMarkdown);
    assert.ok(!next.completedStepIds.includes('runTests'));
    assert.ok(!next.completedStepIds.includes('prepareEvidence'));
  });

  it('emphasizes the corrective action and suppresses rerun emphasis', () => {
    const state = markWorkflowRunBlocked({ settingsReady: true, completedStepIds: ['settings'] }, blocker());
    const corrective = resolveWorkflowActionPresentation(
      { id: 'resolveExecutionBlocker', kind: 'command', label: 'ブロックを解消', primary: true },
      undefined,
      state,
    );
    const rerun = resolveWorkflowActionPresentation(
      { id: 'runTests', kind: 'command', label: 'テストを実行', primary: true },
      'current',
      state,
    );

    assert.equal(corrective.label, '未確定項目を入力');
    assert.equal(corrective.primary, true);
    assert.match(corrective.classes, /danger/);
    assert.equal(rerun.primary, false);
  });

  it('tracks one-time auto-open and clears only the active workspace', () => {
    const marked = markWorkflowRunBlocked({ settingsReady: true, completedStepIds: [] }, blocker());
    const opened = markWorkflowBlockerAutoOpened(marked, 'run-001');
    assert.equal(opened.testExecutionBlockers?.autoOpenedRunId, 'run-001');
    assert.equal(clearWorkflowRunBlocked(opened, 'C:\\other'), opened);
    assert.equal(clearWorkflowRunBlocked(opened, 'C:\\out\\sample').testExecutionBlockers, undefined);
  });

  it('maps stable action codes without using localized labels', () => {
    assert.deepEqual(blockerPrimaryActionTarget('open_test_input_editor'), {
      kind: 'command',
      commandId: 'unitTestRunner.openTestInputEditor',
    });
    assert.deepEqual(blockerPrimaryActionTarget('open_execution_log'), { kind: 'path' });
  });
});

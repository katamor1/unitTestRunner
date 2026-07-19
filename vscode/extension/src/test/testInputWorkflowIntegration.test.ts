import * as assert from 'assert';
import { describe, it } from 'node:test';

import {
  applyTestInputSummaryForWorkspace,
  currentTestInputWorkspace,
  clearTestInputSummaryForWorkspace,
} from '../testInputEditor/workflowIntegration';
import { TestInputSummaryState, WorkflowState } from '../workflow/workflowState';

function state(overrides: Partial<WorkflowState> = {}): WorkflowState {
  return {
    settingsReady: true,
    completedStepIds: ['settings'],
    ...overrides,
  };
}

function ready(workspace: string): TestInputSummaryState {
  return {
    status: 'ready',
    workspace,
    revision: 4,
    specSha256: 'a'.repeat(64),
    summary: {
      attentionCount: 3,
      unresolvedCount: 2,
      unconfirmedCount: 3,
      executionBlockingCount: 1,
      warningCount: 0,
    },
    updatedAt: '2026-07-19T00:00:00.000Z',
  };
}

describe('test input workflow integration', () => {
  it('uses the active workflow output workspace before a legacy report workspace', () => {
    const value = state({
      outputWorkspace: 'C:\\out\\Current',
      reports: { workspace: 'C:\\out\\Old' },
    });

    assert.equal(currentTestInputWorkspace(value), 'C:\\out\\Current');
  });

  it('accepts a summary only while the same workspace is still active', () => {
    const current = state({ outputWorkspace: 'C:\\out\\Control_Update' });
    const summary = ready('c:/out/control_update');

    const updated = applyTestInputSummaryForWorkspace(
      current,
      'C:\\out\\Control_Update',
      summary,
    );
    assert.equal(updated.testInputSummary, summary);

    const switched = state({
      outputWorkspace: 'C:\\out\\Other',
      testInputSummary: ready('C:\\out\\Other'),
    });
    assert.equal(
      applyTestInputSummaryForWorkspace(switched, 'C:\\out\\Control_Update', summary),
      switched,
    );
  });

  it('clears only the summary that belongs to the active workspace', () => {
    const current = state({
      outputWorkspace: 'C:\\out\\Control_Update',
      testInputSummary: ready('C:\\out\\Control_Update'),
    });
    const cleared = clearTestInputSummaryForWorkspace(current, 'c:/out/control_update');
    assert.equal(cleared.testInputSummary, undefined);

    const switched = state({
      outputWorkspace: 'C:\\out\\Other',
      testInputSummary: ready('C:\\out\\Other'),
    });
    assert.equal(clearTestInputSummaryForWorkspace(switched, 'C:\\out\\Control_Update'), switched);
  });
});

import * as assert from 'assert';
import { describe, it } from 'node:test';

import { TestInputFormClient } from '../testInputEditor/cliClient';
import { TestInputApplyResult, TestInputFormModel } from '../testInputEditor/contracts';
import {
  loadTestInputSummaryState,
  readyTestInputSummaryStateFromApply,
} from '../testInputEditor/summaryCache';

const model: TestInputFormModel = {
  schemaVersion: '1.0',
  revision: 3,
  specSha256: 'a'.repeat(64),
  functionName: 'Control_Update',
  summary: {
    attentionCount: 4,
    unresolvedCount: 2,
    unconfirmedCount: 4,
    executionBlockingCount: 1,
    warningCount: 0,
  },
};

const applied: TestInputApplyResult = {
  revision: 4,
  specSha256: 'b'.repeat(64),
  updatedItemCount: 2,
  confirmedItemCount: 1,
  promotedCaseIds: [],
  demotedCaseIds: [],
  summary: {
    attentionCount: 2,
    unresolvedCount: 1,
    unconfirmedCount: 2,
    executionBlockingCount: 0,
    warningCount: 0,
  },
  viewsWritten: true,
  warnings: [],
};

describe('test input summary cache', () => {
  it('loads only the lightweight summary model', async () => {
    const calls: Array<{ workspace: string; summaryOnly: boolean | undefined }> = [];
    const client: TestInputFormClient = {
      async load(workspace, summaryOnly) {
        calls.push({ workspace, summaryOnly });
        return model;
      },
      async apply() {
        throw new Error('not used');
      },
    };

    const state = await loadTestInputSummaryState(client, 'C:\\out\\Control_Update');
    assert.deepEqual(calls, [{ workspace: 'C:\\out\\Control_Update', summaryOnly: true }]);
    assert.equal(state.status, 'ready');
    if (state.status === 'ready') {
      assert.equal(state.revision, 3);
      assert.equal(state.summary.attentionCount, 4);
    }
  });

  it('keeps a summary error distinct from zero unresolved items', async () => {
    const client: TestInputFormClient = {
      async load() {
        throw new Error('stale test spec');
      },
      async apply() {
        throw new Error('not used');
      },
    };

    const state = await loadTestInputSummaryState(client, 'C:\\out\\Control_Update');
    assert.equal(state.status, 'error');
    if (state.status === 'error') {
      assert.match(state.message, /stale test spec/);
    }
  });

  it('can refresh workflow counts from a successful save even when reload fails', () => {
    const state = readyTestInputSummaryStateFromApply('C:\\out\\Control_Update', applied);
    assert.equal(state.status, 'ready');
    if (state.status !== 'ready') {
      assert.fail('expected a ready summary');
    }
    assert.equal(state.revision, 4);
    assert.equal(state.specSha256, 'b'.repeat(64));
    assert.equal(state.summary.attentionCount, 2);
  });
});

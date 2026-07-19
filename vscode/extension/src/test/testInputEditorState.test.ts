import * as assert from 'assert';
import { describe, it } from 'node:test';

import {
  buildChangeDrafts,
  createDraftState,
  draftSummary,
  editControl,
  mergeReloadedModel,
  setItemConfirmed,
} from '../testInputEditor/draftState';
import { TestInputFormModel } from '../testInputEditor/contracts';

function model(fingerprint = 'a'.repeat(64)): TestInputFormModel {
  return {
    schemaVersion: '1.0',
    revision: 2,
    specSha256: 'b'.repeat(64),
    functionName: 'Control_Update',
    summary: { attentionCount: 1, unresolvedCount: 1, unconfirmedCount: 1, executionBlockingCount: 1, warningCount: 0 },
    cases: [{
      caseId: 'TC_1', location: 'additional_case_candidates', promotionEligible: true,
      items: [{
        itemId: `item-${'c'.repeat(64)}`, subjectFingerprint: fingerprint, kind: 'input_assignment', label: 'parameter: mode',
        confirmed: false, blocking: true, editable: true, warnings: [],
        controls: [{ name: 'value_expression', controlKind: 'c_expression', requiredForConfirmation: true, value: 'TBD_VALUE', suggestions: [], enumValues: [] }],
      }],
    }],
  };
}

describe('test input editor draft state', () => {
  it('editing a control marks only that item dirty and clears confirmation', () => {
    let state = createDraftState(model());
    const itemId = model().cases![0].items[0].itemId;
    state = setItemConfirmed(state, itemId, true);
    state = editControl(state, itemId, 'value_expression', 'MODE_AUTO');
    const changes = buildChangeDrafts(state);
    assert.equal(changes.length, 1);
    assert.equal(changes[0].confirmed, false);
    assert.equal(changes[0].values.value_expression, 'MODE_AUTO');
  });


  it('removes a no-op draft after values and confirmation return to baseline', () => {
    const baseline = model();
    const itemId = baseline.cases![0].items[0].itemId;
    let state = createDraftState(baseline);
    state = editControl(state, itemId, 'value_expression', 'MODE_AUTO');
    state = editControl(state, itemId, 'value_expression', 'TBD_VALUE');
    assert.deepEqual(buildChangeDrafts(state), []);

    state = setItemConfirmed(state, itemId, true);
    state = setItemConfirmed(state, itemId, false);
    assert.deepEqual(buildChangeDrafts(state), []);
  });


  it('updates progress counts from the unsaved draft', () => {
    const baseline = model();
    const itemId = baseline.cases![0].items[0].itemId;
    let state = createDraftState(baseline);
    assert.equal(draftSummary(state).attentionCount, 1);
    assert.equal(draftSummary(state).executionBlockingCount, 1);

    state = editControl(state, itemId, 'value_expression', 'MODE_AUTO');
    state = setItemConfirmed(state, itemId, true);
    assert.deepEqual(draftSummary(state), {
      attentionCount: 0,
      unresolvedCount: 0,
      unconfirmedCount: 0,
      executionBlockingCount: 0,
      warningCount: 0,
    });
  });

  it('keeps a draft on same fingerprint and marks a conflict on changed fingerprint', () => {
    const itemId = model().cases![0].items[0].itemId;
    const dirty = editControl(createDraftState(model()), itemId, 'value_expression', 'MODE_AUTO');
    const safe = mergeReloadedModel(dirty, model());
    assert.equal(safe.drafts[itemId].conflict, false);
    const conflicted = mergeReloadedModel(dirty, model('d'.repeat(64)));
    assert.equal(conflicted.drafts[itemId].conflict, true);
  });
});

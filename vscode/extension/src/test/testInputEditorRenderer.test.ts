import * as assert from 'assert';
import { describe, it } from 'node:test';

import { createDraftState, editControl, setItemConfirmed } from '../testInputEditor/draftState';
import { renderTestInputEditor } from '../testInputEditor/renderer';
import { TestInputFormModel } from '../testInputEditor/contracts';

const form: TestInputFormModel = {
  schemaVersion: '1.0', revision: 1, specSha256: 'a'.repeat(64), functionName: '<script>alert(1)</script>',
  summary: { attentionCount: 1, unresolvedCount: 1, unconfirmedCount: 1, executionBlockingCount: 1, warningCount: 0 },
  cases: [{ caseId: 'TC_1', location: 'additional_case_candidates', promotionEligible: true, items: [{
    itemId: `item-${'b'.repeat(64)}`, subjectFingerprint: 'c'.repeat(64), kind: 'input_assignment', label: 'parameter: mode',
    confirmed: false, blocking: true, editable: true, warnings: [], controls: [{
      name: 'value_expression', controlKind: 'c_expression', requiredForConfirmation: true, value: 'TBD_VALUE',
      suggestions: [{ value: 'MODE_AUTO', label: 'MODE_AUTO', source: 'boundary_candidate', confidence: 'high' }], enumValues: [],
    }],
  }] }],
};

describe('test input editor renderer', () => {
  it('renders a nonce-protected escaped form with explicit save', () => {
    const html = renderTestInputEditor(createDraftState(form), 'nonce123');
    assert.match(html, /default-src 'none'/);
    assert.match(html, /nonce="nonce123"/);
    assert.match(html, /保存して反映/);
    assert.match(html, /確認済み/);
    assert.match(html, /MODE_AUTO/);
    assert.match(html, /値（C式）/);
    assert.doesNotMatch(html, /<script>alert\(1\)<\/script>/);
    assert.doesNotMatch(html, /onclick=/);
  });

  it('shows draft progress before the explicit save', () => {
    const itemId = form.cases![0].items[0].itemId;
    let state = createDraftState(form);
    state = editControl(state, itemId, 'value_expression', 'MODE_AUTO');
    state = setItemConfirmed(state, itemId, true);

    const html = renderTestInputEditor(state, 'nonce123');
    assert.match(html, /要確認 0/);
    assert.match(html, /未入力 0/);
    assert.match(html, /未確認 0/);
    assert.match(html, /実行阻害 0/);
  });

});

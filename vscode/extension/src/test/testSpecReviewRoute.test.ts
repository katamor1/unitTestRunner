import * as assert from 'assert';
import { describe, it } from 'node:test';

import { reportAvailabilityFromPaths, WORKFLOW_STEP_DEFINITIONS } from '../workflow/workflowState';

describe('ordinary TestSpec review route', () => {
  it('uses canonical TestSpec views and a review command rather than runtime authority', () => {
    const review = WORKFLOW_STEP_DEFINITIONS.find((step) => step.id === 'reviewTestSpec');
    assert.ok(review);
    assert.deepEqual(review.actions.map((action) => action.id), ['openTestInputEditor', 'openTestSpecMarkdown', 'openTestSpecJson']);
    assert.equal(review.actions[0].commandId, 'unitTestRunner.openTestInputEditor');
    assert.match(`${review.purpose}\n${review.requiredAction}`, /artifact review|TestSpec|approved/);
    assert.doesNotMatch(`${review.purpose}\n${review.requiredAction}`, /authority|IPC/);
  });

  it('does not confuse artifact existence with completed review', () => {
    const availability = reportAvailabilityFromPaths(
      { workspace: 'D:\\out', testSpecJson: 'D:\\out\\reports\\test_spec.json' },
      (value) => value.endsWith('test_spec.json'),
    );
    assert.equal(availability.testSpec, true);
    assert.equal(availability.reviewRecord, false);
  });
});

import * as assert from 'assert';
import { describe, it } from 'node:test';

import {
  reportAvailabilityFromPaths,
  WORKFLOW_STEP_DEFINITIONS,
} from '../workflow/workflowState';

describe('canonical TestSpec review route', () => {
  it('routes the test-design review step to test_spec artifacts', () => {
    const review = WORKFLOW_STEP_DEFINITIONS.find((step) => step.id === 'reviewTestDesign');
    assert.ok(review);

    assert.deepEqual(
      review.actions
        .filter((action) => action.kind === 'openReport')
        .map((action) => action.reportKey),
      ['testSpecCsv', 'testSpecMd', 'testSpecJson'],
    );
    assert.doesNotMatch(`${review.purpose}\n${review.requiredAction}`, /test_case_design\.json/);

    const testSpecCsv = 'D:\\unit-test-output\\Control_Update\\reports\\test_spec.csv';
    const availability = reportAvailabilityFromPaths(
      { workspace: 'D:\\unit-test-output\\Control_Update', testSpecCsv },
      (filePath) => filePath === testSpecCsv,
    );
    assert.equal(availability.testCaseDesign, true);
  });

  it('describes test_spec.json as the harness input', () => {
    const harness = WORKFLOW_STEP_DEFINITIONS.find((step) => step.id === 'generateHarnessSkeleton');
    assert.ok(harness);

    const copy = `${harness.purpose}\n${harness.requiredAction}`;
    assert.match(copy, /test_spec\.json/);
    assert.doesNotMatch(copy, /test_case_design\.json/);
  });
});

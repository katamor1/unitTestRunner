import * as assert from 'assert';
import { describe, it } from 'node:test';

import { parseCliEnvelopeValue } from '../cli/cliEnvelope';
import { parseCliResult, parseValidatedCliSuccess } from '../cli/cliResultParser';

function validEnvelope(outcome: 'planned' | 'passed' = 'passed'): Record<string, unknown> {
  return {
    command: 'run-tests',
    outcome,
    message: outcome === 'passed' ? 'Tests passed.' : 'Run planned.',
    artifacts: [{ kind: 'test_run_report', path: 'runs/run-001/test_run_report.json', sha256: 'a'.repeat(64) }],
    diagnostics: [],
  };
}

describe('v0.1 CLI envelope boundary', () => {
  it('accepts only the exact five-field public envelope', () => {
    const parsed = parseCliEnvelopeValue(validEnvelope());
    assert.equal(parsed.command, 'run-tests');
    assert.equal(parsed.outcome, 'passed');
    assert.deepEqual(parsed.producedArtifacts.map((item) => item.path), ['runs/run-001/test_run_report.json']);

    const extra = { ...validEnvelope(), schema_version: '1.0.0' };
    assert.throws(() => parseCliEnvelopeValue(extra), /Malformed v0\.1 CLI envelope/);
  });

  it('rejects malformed artifacts, outcomes, and diagnostics', () => {
    assert.throws(() => parseCliEnvelopeValue({ ...validEnvelope(), outcome: 'inconclusive' }));
    assert.throws(() => parseCliEnvelopeValue({ ...validEnvelope(), artifacts: [{ kind: 'test_run_report', path: '../escape.json', sha256: 'a'.repeat(64) }] }));
    assert.throws(() => parseCliEnvelopeValue({ ...validEnvelope(), diagnostics: [{ code: 'x', level: 'fatal', message: 'bad' }] }));
  });

  it('permits workflow advancement only for passed or explicitly allowed planned outcomes', () => {
    assert.equal(parseValidatedCliSuccess(JSON.stringify(validEnvelope()), '', 'C:\\out', false).status, 'passed');
    assert.throws(() => parseValidatedCliSuccess(JSON.stringify(validEnvelope('planned')), '', 'C:\\out', false), /planned/);
    assert.equal(parseValidatedCliSuccess(JSON.stringify(validEnvelope('planned')), '', 'C:\\out', true).status, 'planned');
  });

  it('rejects non-JSON and failed envelopes for workflow advancement', () => {
    assert.throws(() => parseValidatedCliSuccess('plain output', '', 'C:\\out', false), /JSON/);
    assert.throws(() => parseValidatedCliSuccess(JSON.stringify({ ...validEnvelope(), outcome: 'failed' }), '', 'C:\\out', false), /failed/);
  });

  it('rejects non-JSON display output instead of inventing artifacts', () => {
    assert.throws(
      () => parseCliResult('plain output', 'diagnostic', 'C:\\out'),
      /must be a JSON envelope/,
    );
  });
});

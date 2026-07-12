import * as assert from 'assert';
import { describe, it } from 'node:test';

import { parseCliEnvelopeValue } from '../cli/cliEnvelope';
import { formatCliFailureMessage, parseCliResult } from '../cli/cliResultParser';


function validV1Envelope(): Record<string, unknown> {
  return {
    artifact_kind: 'cli_result',
    schema_version: '1.0.0',
    producer: {
      name: 'unit-test-runner',
      version: '0.1.0',
      commit: '6c3aecac794f18bffd4307213481cbfaf270cdba',
    },
    subject: { invocation_id: 'inv-001' },
    data: {
      invocation_id: 'inv-001',
      command: 'run-tests',
      lifecycle: 'finished',
      outcome_kind: 'test_run',
      outcome: 'passed',
      green: true,
      exit_code: 0,
      message: 'Tests passed.',
      diagnostics: [],
      artifacts: [
        {
          artifact_kind: 'test_execution_report',
          path: 'runs/run-001/test_execution_report.json',
          exists: true,
          sha256: 'a'.repeat(64),
          schema_version: '1.0.0',
        },
      ],
      expected_artifacts: [
        {
          artifact_kind: 'test_spec',
          path: 'reports/test_spec.json',
        },
      ],
      errors: [],
      details: { run_id: 'run-001' },
    },
    extensions: {},
  };
}


describe('CLI envelope compatibility boundary', () => {
  it('accepts a fully shaped v1 envelope', () => {
    const parsed = parseCliEnvelopeValue(validV1Envelope());

    assert.equal(parsed.version, '1.0.0');
    assert.equal(parsed.outcome, 'passed');
    assert.equal(parsed.exitCode, 0);
    assert.deepEqual(parsed.warnings, []);
    assert.deepEqual(parsed.producedArtifacts.map((item) => item.path), [
      'runs/run-001/test_execution_report.json',
    ]);
    assert.deepEqual(parsed.expectedArtifacts.map((item) => item.path), [
      'reports/test_spec.json',
    ]);
  });

  it('rejects malformed v1 instead of falling back to legacy parsing', () => {
    const malformed = validV1Envelope();
    const data = malformed.data as Record<string, unknown>;
    data.artifacts = [{ artifact_kind: 'test_execution_report', path: 'report.json' }];

    assert.throws(() => parseCliEnvelopeValue(malformed), /Malformed v1 CLI envelope/);
  });

  it('rejects an unsupported v1-family version', () => {
    const unsupported = validV1Envelope();
    unsupported.schema_version = '2.0.0';

    assert.throws(() => parseCliEnvelopeValue(unsupported), /Unsupported CLI envelope version: 2\.0\.0/);
  });

  it('rejects versionless JSON instead of assuming legacy v0.1', () => {
    assert.throws(
      () => parseCliEnvelopeValue({
        status: 'ok',
        exit_code: 0,
        command: 'doctor',
        data: {},
        warnings: [],
        errors: [],
      }),
      /Unsupported CLI envelope version: <missing>/,
    );
  });

  it('reads a genuine v0.1 envelope with a migration warning and explicit paths only', () => {
    const legacy = parseCliEnvelopeValue({
      schema_version: '0.1',
      status: 'dossier_finalized',
      exit_code: 0,
      command: 'finalize-dossier',
      message: 'done',
      data: {
        reports: {
          function_dossier_md: 'reports/explicit_dossier.md',
        },
      },
      warnings: [],
      errors: [],
    });

    assert.equal(legacy.version, '0.1');
    assert.ok(legacy.warnings.some((warning) => warning.includes('v0.1')));
    assert.deepEqual(legacy.reportedPaths, {
      function_dossier_md: 'reports/explicit_dossier.md',
    });
  });

  it('does not fabricate produced reports from a legacy dossier path', () => {
    const legacy = parseCliEnvelopeValue({
      schema_version: '0.1',
      status: 'dossier_finalized',
      exit_code: 0,
      command: 'finalize-dossier',
      message: 'done',
      data: {
        dossier: 'reports/function_dossier.json',
      },
      warnings: [],
      errors: [],
    });

    assert.deepEqual(legacy.reportedPaths, {});
    assert.deepEqual(legacy.producedArtifacts, []);
  });

  it('uses only validated v1 produced artifacts in the adapter report view', () => {
    const envelope = validV1Envelope();
    const data = envelope.data as Record<string, unknown>;
    data.artifacts = [
      {
        artifact_kind: 'function_dossier',
        path: 'reports/explicit_dossier.md',
        exists: true,
        sha256: 'b'.repeat(64),
        schema_version: null,
      },
    ];

    const parsed = parseCliResult(
      JSON.stringify(envelope),
      '',
      'C:\\work\\out\\Control_Update',
    );

    assert.equal(parsed.status, 'passed');
    assert.match(parsed.reports.functionDossierMd ?? '', /explicit_dossier\.md$/);
    assert.deepEqual(parsed.warnings, []);
  });

  it('propagates malformed v1 as an adapter error', () => {
    const malformed = validV1Envelope();
    const data = malformed.data as Record<string, unknown>;
    data.expected_artifacts = [
      {
        artifact_kind: 'test_spec',
        path: 'reports/test_spec.json',
        exists: false,
      },
    ];

    assert.throws(
      () => parseCliResult(JSON.stringify(malformed), '', 'C:\\work\\out'),
      /Malformed v1 CLI envelope/,
    );
  });

  it('does not turn a legacy dossier path into conventional report paths', () => {
    const parsed = parseCliResult(
      JSON.stringify({
        schema_version: '0.1',
        status: 'dossier_finalized',
        exit_code: 0,
        command: 'finalize-dossier',
        message: 'done',
        data: { dossier: 'reports/function_dossier.json' },
        warnings: [],
        errors: [],
      }),
      '',
      'C:\\work\\out\\Control_Update',
    );

    assert.equal(parsed.reports.functionDossierMd, undefined);
    assert.ok(parsed.warnings.some((warning) => warning.includes('v0.1')));
  });

  it('does not infer report paths from non-JSON output', () => {
    const parsed = parseCliResult('plain output', '', 'C:\\work\\out\\Control_Update');

    assert.equal(parsed.reports.functionDossierMd, undefined);
    assert.ok(parsed.warnings.some((warning) => warning.includes('JSON envelope')));
  });

  it('formats validated v1 failures from nested machine fields', () => {
    const envelope = validV1Envelope();
    const data = envelope.data as Record<string, unknown>;
    data.command = 'suite-run';
    data.outcome_kind = 'suite_run';
    data.outcome = 'failed';
    data.green = false;
    data.exit_code = 32;
    data.message = 'Suite run completed.';
    data.diagnostics = [
      { code: 'suite_not_green', severity: 'error', message: 'One selected entry is not GREEN.' },
    ];
    data.errors = [
      { code: 'test_failure', message: 'Control_Update failed.' },
    ];
    data.details = {
      summary: { total: 2, green: 1, not_green: 1 },
    };

    const message = formatCliFailureMessage(JSON.stringify(envelope), '', 32);

    assert.match(message, /suite-run/);
    assert.match(message, /全件GREENではありません/);
    assert.match(message, /GREEN 1 \/ Not GREEN 1 \/ Total 2/);
    assert.match(message, /Control_Update failed\./);
    assert.match(message, /One selected entry is not GREEN\./);
  });
});

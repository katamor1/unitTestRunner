import * as assert from 'assert';
import { describe, it } from 'node:test';

import { ParsedCliEnvelope } from '../cli/cliEnvelope';
import { parseHandledBlockedRun } from '../testExecutionBlockers/contracts';

function blockedEnvelope(): ParsedCliEnvelope {
  return {
    version: '1.0.0',
    command: 'run-tests',
    outcome: 'blocked',
    exitCode: 35,
    details: {
      test_execution: { status: 'blocked', run_id: 'run-001' },
      blockers: {
        count: 2,
        primary_action: 'open_test_input_editor',
        primary_action_label: '未確定項目を入力',
        run_json: 'runs/run-001/test_execution_blockers.json',
        run_markdown: 'runs/run-001/test_execution_blockers.md',
        latest_json: 'reports/test_execution_blockers.json',
        latest_markdown: 'reports/test_execution_blockers.md',
      },
    },
    diagnostics: [],
    producedArtifacts: [],
    expectedArtifacts: [],
    reportedPaths: {},
    warnings: [],
    raw: {},
  };
}

describe('blocked test run contract', () => {
  it('recognizes only a structured run-tests --run exit-35 result', () => {
    const parsed = parseHandledBlockedRun(blockedEnvelope(), 35, ['run-tests', '--run']);

    assert.ok(parsed);
    assert.equal(parsed.runId, 'run-001');
    assert.equal(parsed.count, 2);
    assert.equal(parsed.primaryAction, 'open_test_input_editor');
    assert.equal(parsed.latestMarkdown, 'reports/test_execution_blockers.md');

    assert.equal(parseHandledBlockedRun(blockedEnvelope(), 35, ['run-tests', '--plan']), undefined);
    assert.equal(parseHandledBlockedRun(blockedEnvelope(), 34, ['run-tests', '--run']), undefined);
  });

  it('keeps a blocked result handled when report publication failed', () => {
    const envelope = blockedEnvelope();
    envelope.details = {
      test_execution: { status: 'blocked', run_id: 'run-002' },
    };
    envelope.diagnostics = [
      { code: 'blocker_report_write_failed', severity: 'warning', message: 'write failed' },
    ];

    const parsed = parseHandledBlockedRun(envelope, 35, ['run-tests', '--run']);

    assert.ok(parsed);
    assert.equal(parsed.count, 0);
    assert.equal(parsed.primaryAction, 'open_execution_report');
    assert.equal(parsed.publicationDiagnostics.length, 1);
  });

  it('rejects unsafe report paths', () => {
    const envelope = blockedEnvelope();
    const blockers = envelope.details.blockers as Record<string, unknown>;
    blockers.latest_markdown = '../outside.md';

    assert.throws(
      () => parseHandledBlockedRun(envelope, 35, ['run-tests', '--run']),
      /Invalid blocker path/,
    );
  });
});

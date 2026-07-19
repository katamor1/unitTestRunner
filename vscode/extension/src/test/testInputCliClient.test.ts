import * as assert from 'assert';
import { describe, it } from 'node:test';

import { buildApplyTestInputFormInvocation, buildGetTestInputFormInvocation } from '../cli/commandBuilder';
import { buildSettingsViewModel } from '../config/settingsViewModel';
import { readAdapterSettingsFromObject } from '../config/settings';
import { parseTestInputFormEnvelope } from '../testInputEditor/contracts';
import { TestInputCliClient, TestInputCliError } from '../testInputEditor/cliClient';

const settings = readAdapterSettingsFromObject({
  cliPath: 'unit-test-runner', sourceRoot: 'C:\\work', dswPath: 'C:\\work\\P.dsw', outputRoot: 'C:\\out',
  useJsonOutput: true, commandTimeoutSeconds: 30,
}, 'C:\\work');
void buildSettingsViewModel;

describe('test input CLI adapter', () => {
  it('builds query and apply commands', () => {
    const get = buildGetTestInputFormInvocation(settings, 'C:\\out\\Control', true);
    assert.deepEqual(get.args.slice(0, 4), ['--json', 'get-test-input-form', '--workspace', 'C:\\out\\Control']);
    assert.ok(get.args.includes('--summary-only'));
    const apply = buildApplyTestInputFormInvocation(settings, 'C:\\out\\Control', 'C:\\tmp\\x.json', 3);
    assert.deepEqual(apply.args.slice(-2), ['--expected-revision', '3']);
  });


  it('reports a timeout before attempting to parse an empty response', async () => {
    const client = new TestInputCliClient({
      settings: () => settings,
      storageRoot: 'C:\\tmp',
      run: async () => ({
        exitCode: null,
        stdout: '',
        stderr: '',
        timedOut: true,
        commandLine: 'unit-test-runner --json get-test-input-form',
      }),
    });

    await assert.rejects(
      client.load('C:\\out\\Control'),
      (error: unknown) => error instanceof TestInputCliError && error.code === 'timed_out',
    );
  });

  it('uses stderr for a non-JSON CLI failure', async () => {
    const client = new TestInputCliClient({
      settings: () => settings,
      storageRoot: 'C:\\tmp',
      run: async () => ({
        exitCode: 2,
        stdout: '',
        stderr: 'Canonical TestSpec was not found',
        timedOut: false,
        commandLine: 'unit-test-runner --json get-test-input-form',
      }),
    });

    await assert.rejects(
      client.load('C:\\out\\Control'),
      (error: unknown) => error instanceof TestInputCliError
        && error.code === 'cli_error'
        && /Canonical TestSpec/.test(error.message),
    );
  });

  it('parses a strict v1 form envelope', () => {
    const value = {
      artifact_kind: 'cli_result', schema_version: '1.0.0',
      producer: { name: 'unit-test-runner', version: '0.1.0', commit: 'a'.repeat(40) },
      subject: { invocation_id: 'inv-1' }, extensions: {},
      data: { invocation_id: 'inv-1', command: 'get-test-input-form', lifecycle: 'finished', outcome_kind: 'command', outcome: 'passed', green: null, exit_code: 0, message: '', diagnostics: [], artifacts: [], expected_artifacts: [], errors: [], details: {
        schema_version: '1.0', revision: 1, spec_sha256: 'b'.repeat(64), function: { name: 'Control_Update' },
        summary: { attention_count: 0, unresolved_count: 0, unconfirmed_count: 0, execution_blocking_count: 0, warning_count: 0 }, cases: [],
      } },
    };
    assert.equal(parseTestInputFormEnvelope(value).functionName, 'Control_Update');
  });
});

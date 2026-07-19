import * as assert from 'assert';
import { describe, it } from 'node:test';
import * as path from 'path';

import {
  buildGenerateHarnessSkeletonInvocation,
  buildReanalyzeFunctionInvocation,
} from '../cli/commandBuilder';
import { parseCliResult } from '../cli/cliResultParser';
import { readAdapterSettingsFromObject } from '../config/settings';
import { resolveReportPaths } from '../reports/reportPathResolver';

function settings() {
  return readAdapterSettingsFromObject(
    {
      cliPath: 'unit-test-runner',
      sourceRoot: 'C:\\work\\product',
      dswPath: 'C:\\work\\product\\Product.dsw',
      outputRoot: 'D:\\unit-test-output',
      defaultConfiguration: 'Win32 Debug',
      defaultProject: 'Control',
      useJsonOutput: true,
    },
    'C:\\work\\product',
  );
}

function validEnvelope() {
  return {
    artifact_kind: 'cli_result',
    schema_version: '1.0.0',
    producer: {
      name: 'unit-test-runner',
      version: '0.1.0',
      commit: '6c3aecac794f18bffd4307213481cbfaf270cdba',
    },
    subject: { invocation_id: 'inv-canonical-test-spec' },
    data: {
      invocation_id: 'inv-canonical-test-spec',
      command: 'get-test-spec',
      lifecycle: 'finished',
      outcome_kind: 'command',
      outcome: 'passed',
      green: null,
      exit_code: 0,
      message: 'loaded',
      diagnostics: [],
      artifacts: [
        {
          artifact_kind: 'test_spec',
          path: 'reports/test_spec.json',
          exists: true,
          sha256: 'a'.repeat(64),
          schema_version: '1.1.0',
        },
        {
          artifact_kind: 'test_spec_markdown',
          path: 'reports/test_spec.md',
          exists: true,
          sha256: 'b'.repeat(64),
          schema_version: null,
        },
        {
          artifact_kind: 'test_spec_csv',
          path: 'reports/test_spec.csv',
          exists: true,
          sha256: 'c'.repeat(64),
          schema_version: null,
        },
      ],
      expected_artifacts: [],
      errors: [],
      details: {},
    },
    extensions: {},
  };
}

describe('canonical TestSpec paths in the VS Code adapter', () => {
  it('passes canonical TestSpec to reanalysis and harness generation', () => {
    const adapterSettings = settings();
    const target = {
      sourcePath: 'C:\\work\\product\\src\\control.c',
      sourceRelativePath: 'src/control.c',
      functionName: 'Control_Update',
      project: 'Control',
      configuration: 'Win32 Debug',
      outputWorkspace: 'D:\\unit-test-output\\Control_Update',
    };

    const reanalyze = buildReanalyzeFunctionInvocation(adapterSettings, target);
    const harness = buildGenerateHarnessSkeletonInvocation(adapterSettings, target.outputWorkspace);
    const canonical = path.join(target.outputWorkspace, 'reports', 'test_spec.json');

    assert.deepEqual(
      reanalyze.args.slice(
        reanalyze.args.indexOf('--previous-test-spec'),
        reanalyze.args.indexOf('--previous-test-spec') + 2,
      ),
      ['--previous-test-spec', canonical],
    );
    assert.equal(reanalyze.args.includes('--previous-test-case-design'), false);
    assert.deepEqual(
      harness.args.slice(harness.args.indexOf('--test-spec'), harness.args.indexOf('--test-spec') + 2),
      ['--test-spec', canonical],
    );
    assert.equal(harness.args.includes('--test-case-design'), false);
  });

  it('resolves conventional and reported canonical TestSpec files', () => {
    const workspace = 'D:\\unit-test-output\\Control_Update';
    const conventional = resolveReportPaths(workspace);

    assert.equal(conventional.testSpecJson, path.join(workspace, 'reports', 'test_spec.json'));
    assert.equal(conventional.testSpecMd, path.join(workspace, 'reports', 'test_spec.md'));
    assert.equal(conventional.testSpecCsv, path.join(workspace, 'reports', 'test_spec.csv'));

    const parsed = parseCliResult(JSON.stringify(validEnvelope()), '', workspace);
    assert.equal(parsed.reports.testSpecJson, path.join(workspace, 'reports', 'test_spec.json'));
    assert.equal(parsed.reports.testSpecMd, path.join(workspace, 'reports', 'test_spec.md'));
    assert.equal(parsed.reports.testSpecCsv, path.join(workspace, 'reports', 'test_spec.csv'));
  });
});

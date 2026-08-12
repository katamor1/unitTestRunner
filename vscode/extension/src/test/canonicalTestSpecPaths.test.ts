import * as assert from 'assert';
import * as path from 'path';
import { describe, it } from 'node:test';

import { buildPrepareHarnessInvocation, buildReanalyzeFunctionInvocation } from '../cli/commandBuilder';
import { parseCliResult } from '../cli/cliResultParser';
import { readAdapterSettingsFromObject } from '../config/settings';
import { resolveReportPaths } from '../reports/reportPathResolver';

const settings = readAdapterSettingsFromObject({
  cliPath: 'unit-test-runner', sourceRoot: 'C:\\work\\product', dswPath: 'C:\\work\\product\\Product.dsw',
  outputRoot: 'D:\\out', defaultConfiguration: 'Control - Win32 Debug', defaultProject: 'Control',
}, 'C:\\work\\product');

const target = {
  sourcePath: 'C:\\work\\product\\src\\control.c', sourceRelativePath: 'src/control.c',
  functionName: 'Control_Update', project: 'Control', configuration: 'Control - Win32 Debug',
  outputWorkspace: 'D:\\out\\fn_Control_Update_123456789abc',
};

describe('canonical TestSpec route', () => {
  it('reanalyzes against canonical TestSpec and prepares harness through analyze-function', () => {
    const reanalyze = buildReanalyzeFunctionInvocation(settings, target);
    const harness = buildPrepareHarnessInvocation(settings, target);
    const canonical = path.win32.join(target.outputWorkspace, 'reports', 'test_spec.json');
    assert.deepEqual(reanalyze.args.slice(reanalyze.args.indexOf('--previous-test-spec'), reanalyze.args.indexOf('--previous-test-spec') + 2), ['--previous-test-spec', canonical]);
    assert.deepEqual(harness.args.slice(0, 2), ['--json', 'analyze-function']);
    assert.deepEqual(harness.args.slice(harness.args.indexOf('--phase'), harness.args.indexOf('--phase') + 2), ['--phase', 'harness']);
    assert.equal(harness.args.includes('generate-harness-skeleton'), false);
  });

  it('resolves TestSpec JSON/Markdown/CSV only from the public artifact', () => {
    const conventional = resolveReportPaths(target.outputWorkspace);
    assert.equal(conventional.testSpecJson, path.win32.join(target.outputWorkspace, 'reports', 'test_spec.json'));
    const parsed = parseCliResult(JSON.stringify({
      command: 'analyze-function', outcome: 'passed', message: 'done', diagnostics: [],
      artifacts: [{ kind: 'test_spec', path: 'reports/test_spec.json', sha256: 'a'.repeat(64) }],
    }), '', target.outputWorkspace);
    assert.equal(parsed.reports.testSpecJson, conventional.testSpecJson);
    assert.equal(parsed.reports.testSpecMd, conventional.testSpecMd);
    assert.equal(parsed.reports.testSpecCsv, conventional.testSpecCsv);
  });
});

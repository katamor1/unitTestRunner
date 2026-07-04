import * as assert from 'assert';
import { describe, it } from 'node:test';
import * as path from 'path';

import { buildAnalyzeFunctionInvocation, buildFinalizeDossierInvocation, buildRunTestsInvocation } from '../cli/commandBuilder';
import { parseCliResultReportPaths } from '../cli/cliResultParser';
import { readAdapterSettingsFromObject } from '../config/settings';
import { validateSettings } from '../config/validation';
import { resolveFunctionNameFromText } from '../functionTarget/regexFunctionResolver';
import { resolveReportPaths } from '../reports/reportPathResolver';
import { commandRequiresConfirmation } from '../safety/confirmation';

describe('UnitTestRunner VS Code thin adapter core', () => {
  it('reads settings and warns when outputRoot is inside sourceRoot', () => {
    const settings = readAdapterSettingsFromObject(
      {
        cliPath: '',
        sourceRoot: 'C:\\work\\product',
        dswPath: 'C:\\work\\product\\Product.dsw',
        outputRoot: 'C:\\work\\product\\generated',
        defaultConfiguration: 'Win32 Debug',
        defaultProject: 'Control',
      },
      'C:\\work\\product',
    );

    const validation = validateSettings(settings);

    assert.equal(settings.cliPath, '');
    assert.ok(validation.warnings.some((warning) => warning.code === 'missing_cli_path'));
    assert.ok(validation.warnings.some((warning) => warning.code === 'output_root_inside_source_root'));
  });

  it('resolves selected and cursor function names without parsing C in VS Code', () => {
    assert.equal(resolveFunctionNameFromText({ selectedText: 'Control_Update', documentText: '', cursorOffset: 0 }), 'Control_Update');

    const source = 'static int helper(void) { return 0; }\nint Control_Update(int mode)\n{\n    return mode;\n}\n';
    const offset = source.indexOf('return mode');

    assert.equal(resolveFunctionNameFromText({ selectedText: '', documentText: source, cursorOffset: offset }), 'Control_Update');
  });

  it('builds analyze/finalize/run invocations with Windows paths as argv items', () => {
    const settings = readAdapterSettingsFromObject(
      {
        cliPath: 'C:\\Program Files\\Unit Test Runner\\unit-test-runner.exe',
        sourceRoot: 'C:\\work\\product',
        dswPath: 'C:\\work\\product\\Product.dsw',
        outputRoot: 'C:\\unit test workspace',
        defaultConfiguration: 'Win32 Debug',
        defaultProject: 'Control',
        useJsonOutput: true,
      },
      'C:\\work\\product',
    );
    const target = {
      sourcePath: 'C:\\work\\product\\src\\control.c',
      sourceRelativePath: 'src/control.c',
      functionName: 'Control_Update',
      project: 'Control',
      configuration: 'Win32 Debug',
      outputWorkspace: 'C:\\unit test workspace\\Control_Update',
    };

    const analyze = buildAnalyzeFunctionInvocation(settings, target);
    const finalize = buildFinalizeDossierInvocation(settings, target.outputWorkspace);
    const runTests = buildRunTestsInvocation(settings, target.outputWorkspace, true);

    assert.equal(analyze.command, settings.cliPath);
    assert.ok(analyze.args.includes('--json'));
    assert.ok(analyze.args.includes('--finalize-dossier'));
    assert.deepEqual(analyze.args.slice(analyze.args.indexOf('--configuration'), analyze.args.indexOf('--configuration') + 2), ['--configuration', 'Win32 Debug']);
    assert.ok(analyze.displayCommand.includes('"C:\\unit test workspace\\Control_Update"'));
    assert.deepEqual(finalize.args.slice(0, 3), ['--json', 'finalize-dossier', '--workspace']);
    assert.equal(runTests.requiresConfirmation, true);
  });

  it('parses CLI JSON report paths and falls back to conventional report names', () => {
    const parsed = parseCliResultReportPaths(
      JSON.stringify({
        status: 'dossier_finalized',
        data: {
          review: {
            reports: {
              function_dossier_md: 'reports/function_dossier.md',
              review_checklist: 'reports/review_checklist.md',
              next_actions: 'reports/next_actions.md',
            },
          },
        },
      }),
      '',
      'C:\\work\\out\\Control_Update',
    );
    const fallback = parseCliResultReportPaths('plain output', '', 'C:\\work\\out\\Control_Update');
    const direct = resolveReportPaths('C:\\work\\out\\Control_Update');

    assert.equal(path.basename(parsed.functionDossierMd ?? ''), 'function_dossier.md');
    assert.equal(path.basename(parsed.reviewChecklistMd ?? ''), 'review_checklist.md');
    assert.equal(path.basename(fallback.nextActionsMd ?? ''), 'next_actions.md');
    assert.equal(path.basename(direct.unresolvedItemsMd ?? ''), 'unresolved_items.md');
  });

  it('requires confirmation only for explicit build and test execution commands', () => {
    assert.equal(commandRequiresConfirmation('build-probe', { run: false, dryRun: true }), false);
    assert.equal(commandRequiresConfirmation('build-probe', { run: true, dryRun: false }), true);
    assert.equal(commandRequiresConfirmation('run-tests', { run: true, dryRun: false }), true);
    assert.equal(commandRequiresConfirmation('finalize-dossier', {}), false);
  });
});

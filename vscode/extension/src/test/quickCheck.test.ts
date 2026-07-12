import * as assert from 'assert';
import { describe, it } from 'node:test';
import * as path from 'path';

import {
  buildFullGateAnalyzeInvocation,
  buildQuickCheckInvocation,
  buildQuickOutputWorkspace,
  normalizeQuickCheckProfile,
  quickCheckPhase,
} from '../cli/commandBuilder';
import { parseCliResult } from '../cli/cliResultParser';
import { readAdapterSettingsFromObject } from '../config/settings';
import { validateSettings } from '../config/validation';
import { resolveReportPaths } from '../reports/reportPathResolver';

describe('UnitTestRunner quick check adapter core', () => {
  it('reads quick check settings with safe defaults', () => {
    const settings = readAdapterSettingsFromObject(
      {
        cliPath: 'unit-test-runner',
        sourceRoot: 'C:\\work\\product',
        dswPath: 'C:\\work\\product\\Product.dsw',
        outputRoot: 'D:\\unit-test-output',
      },
      'C:\\work\\product',
    );

    assert.equal(settings.quickProfile, 'design');
    assert.equal(settings.quickOutputRoot, '');
    assert.equal(settings.quickReusePreviousWorkspace, true);
    assert.equal(settings.quickAutoOpenSummary, true);
    assert.equal(settings.quickAllowExecution, false);
  });

  it('warns when quickOutputRoot points inside sourceRoot', () => {
    const settings = readAdapterSettingsFromObject(
      {
        cliPath: 'unit-test-runner',
        sourceRoot: 'C:\\work\\product',
        dswPath: 'C:\\work\\product\\Product.dsw',
        outputRoot: 'D:\\unit-test-output',
        quickOutputRoot: 'C:\\work\\product\\_quick',
      },
      'C:\\work\\product',
    );

    const validation = validateSettings(settings);

    assert.equal(validation.ok, true);
    assert.ok(validation.warnings.some((warning) => warning.code === 'quick_output_root_inside_source_root'));
  });

  it('normalizes quick check profiles to generated-design CLI phases', () => {
    assert.equal(normalizeQuickCheckProfile('design'), 'design');
    assert.equal(normalizeQuickCheckProfile('harness'), 'harness');
    assert.equal(normalizeQuickCheckProfile('build-dry-run'), 'build-dry-run');
    assert.equal(normalizeQuickCheckProfile('analysis'), 'design');
    assert.equal(normalizeQuickCheckProfile('unexpected'), 'design');
    assert.equal(quickCheckPhase('build-dry-run'), 'build');
  });

  it('builds quick check analyze invocation without dossier finalization', () => {
    const settings = readAdapterSettingsFromObject(
      {
        cliPath: 'C:\\Program Files\\Unit Test Runner\\unit-test-runner.exe',
        sourceRoot: 'C:\\work\\product',
        dswPath: 'C:\\work\\product\\Product.dsw',
        outputRoot: 'D:\\unit-test-output',
        defaultConfiguration: 'Win32 Debug',
        defaultProject: 'Control',
        quickProfile: 'harness',
        useJsonOutput: true,
        finalizeDossierAfterAnalyze: true,
      },
      'C:\\work\\product',
    );
    const target = {
      sourcePath: 'C:\\work\\product\\src\\control.c',
      sourceRelativePath: 'src/control.c',
      functionName: 'Control_Update',
      project: 'Control',
      configuration: 'Win32 Debug',
      outputWorkspace: path.join(settings.outputRoot, 'Control_Update'),
    };

    const quickWorkspace = buildQuickOutputWorkspace(settings, target);
    const quick = buildQuickCheckInvocation(settings, target);
    const phaseIndex = quick.args.indexOf('--phase');

    assert.ok(quickWorkspace.includes('_quick'));
    assert.ok(quickWorkspace.includes('src_control_Control_Update'));
    assert.equal(quick.args.includes('--finalize-dossier'), false);
    assert.deepEqual(quick.args.slice(phaseIndex, phaseIndex + 2), ['--phase', 'harness']);
    assert.deepEqual(quick.args.slice(quick.args.indexOf('--out'), quick.args.indexOf('--out') + 2), ['--out', quickWorkspace]);
    assert.equal(quick.requiresConfirmation, false);
  });

  it('builds full gate analyze invocation with forced dossier finalization', () => {
    const settings = readAdapterSettingsFromObject(
      {
        cliPath: 'unit-test-runner',
        sourceRoot: 'C:\\work\\product',
        dswPath: 'C:\\work\\product\\Product.dsw',
        outputRoot: 'D:\\unit-test-output',
        defaultConfiguration: 'Win32 Debug',
        defaultProject: 'Control',
        finalizeDossierAfterAnalyze: false,
      },
      'C:\\work\\product',
    );
    const target = {
      sourcePath: 'C:\\work\\product\\src\\control.c',
      sourceRelativePath: 'src/control.c',
      functionName: 'Control_Update',
      project: 'Control',
      configuration: 'Win32 Debug',
      outputWorkspace: path.join(settings.outputRoot, 'Control_Update'),
    };

    const fullGate = buildFullGateAnalyzeInvocation(settings, target);

    assert.ok(fullGate.args.includes('--finalize-dossier'));
    assert.equal(fullGate.args.includes('--phase'), false);
    assert.deepEqual(fullGate.args.slice(fullGate.args.indexOf('--out'), fullGate.args.indexOf('--out') + 2), ['--out', target.outputWorkspace]);
  });

  it('resolves quick summary report paths from fallback and CLI JSON', () => {
    const workspace = 'D:\\unit-test-output\\_quick\\src_control_Control_Update_deadbeef';
    const fallback = resolveReportPaths(workspace);
    assert.equal(fallback.quickSummaryMd, path.win32.join(workspace, 'reports', 'quick_summary.md'));
    assert.equal(fallback.quickSummaryJson, path.win32.join(workspace, 'reports', 'quick_summary.json'));

    const parsed = parseCliResult(
      JSON.stringify({
        schema_version: '0.1',
        status: 'analysis_completed',
        exit_code: 0,
        command: 'analyze-function',
        data: {
          reports: {
            quick_summary_md: 'D:/quick/reports/quick_summary.md',
            quick_summary_json: 'D:/quick/reports/quick_summary.json',
            function_dossier_md: 'D:/quick/reports/function_dossier.md',
          },
        },
        warnings: [],
        errors: [],
      }),
      '',
      workspace,
    );

    assert.equal(parsed.reports.quickSummaryMd, 'D:/quick/reports/quick_summary.md');
    assert.equal(parsed.reports.quickSummaryJson, 'D:/quick/reports/quick_summary.json');
    assert.equal(parsed.reports.functionDossierMd, 'D:/quick/reports/function_dossier.md');
  });
});

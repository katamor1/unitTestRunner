import * as assert from 'assert';
import * as fs from 'fs';
import { describe, it } from 'node:test';
import * as path from 'path';

import { buildAnalyzeFunctionInvocation, buildFinalizeDossierInvocation, buildGenerateHarnessSkeletonInvocation, buildGenerateTestDesignInvocation, buildReanalyzeFunctionInvocation, buildRunTestsInvocation } from '../cli/commandBuilder';
import { runCliInvocation } from '../cli/cliRunner';
import { parseCliResult, parseCliResultReportPaths } from '../cli/cliResultParser';
import { DEFAULT_CLI_PATH, resolveCliPath } from '../config/bundledCli';
import { defaultSourceRootFromWorkspaceFolders, readAdapterSettingsFromObject } from '../config/settings';
import { buildSettingsViewModel } from '../config/settingsViewModel';
import { validateSettings } from '../config/validation';
import { resolveFunctionNameFromText } from '../functionTarget/regexFunctionResolver';
import { resolveReportPaths } from '../reports/reportPathResolver';
import { commandRequiresConfirmation } from '../safety/confirmation';
import { renderSettings } from '../workflow/settingsPanelRenderer';
import {
  completeAwaitingSaveIfMatches,
  createInitialWorkflowState,
  deriveCurrentWorkflowStepId,
  EMPTY_REPORT_AVAILABILITY,
  markStepAwaitingSave,
  markWorkflowCommandFailed,
  markWorkflowCommandSucceeded,
  WorkflowReportAvailability,
  WORKFLOW_STEP_DEFINITIONS,
  workflowLegacyProjection,
} from '../workflow/workflowState';

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

  it('uses the first VS Code workspace folder as the sourceRoot default', () => {
    const workspaceRoot = 'C:\\work\\product';
    const defaultSourceRoot = defaultSourceRootFromWorkspaceFolders([{ uri: { fsPath: workspaceRoot } }, { uri: { fsPath: 'D:\\other' } }]);
    const settings = readAdapterSettingsFromObject(
      {
        dswPath: 'C:\\work\\product\\Product.dsw',
        outputRoot: 'D:\\unit-test-output',
      },
      defaultSourceRoot,
    );

    assert.equal(defaultSourceRoot, workspaceRoot);
    assert.equal(settings.sourceRoot, workspaceRoot);

    const legacySettings = readAdapterSettingsFromObject(
      {
        sourceRoot: '',
        workspaceRoot: 'D:\\legacy\\product',
        defaultProject: '',
        projectName: 'LegacyControl',
      },
      workspaceRoot,
    );
    assert.equal(legacySettings.sourceRoot, 'D:\\legacy\\product');
    assert.equal(legacySettings.defaultProject, 'LegacyControl');
  });

  it('builds the settings panel model with defaults, missing fields, and warnings', () => {
    const model = buildSettingsViewModel(
      {
        sourceRoot: '',
        dswPath: '',
        outputRoot: 'C:\\work\\product\\generated',
        defaultConfiguration: '',
        defaultProject: 'Control',
      },
      'C:\\work\\product',
    );
    const fields = new Map(model.fields.map((field) => [field.id, field]));

    assert.equal(model.ready, false);
    assert.equal(fields.get('sourceRoot')?.state, 'default');
    assert.equal(fields.get('sourceRoot')?.effectiveValue, 'C:\\work\\product');
    assert.equal(fields.get('dswPath')?.state, 'missing');
    assert.equal(fields.get('outputRoot')?.state, 'warning');
    assert.ok(fields.get('outputRoot')?.messages.some((message) => message.includes('本番リポジトリへ生成物が混入')));
    assert.equal(fields.get('defaultConfiguration')?.state, 'default');
    assert.equal(fields.get('defaultProject')?.state, 'configured');
    assert.ok(fields.get('sourceRoot')?.actions.some((action) => action.kind === 'inputText'));
    assert.ok(fields.get('dswPath')?.actions.some((action) => action.kind === 'inputText'));
    assert.ok(fields.get('outputRoot')?.actions.some((action) => action.kind === 'inputText'));
    assert.ok(fields.get('cliPath')?.actions.some((action) => action.kind === 'inputText'));
    assert.ok(fields.get('cliPath')?.actions.some((action) => action.kind === 'reset'));
  });

  it('collapses the settings panel by default only when required workspace settings are ready', () => {
    const ready = buildSettingsViewModel(
      {
        cliPath: 'unit-test-runner',
        sourceRoot: 'C:\\work\\product',
        dswPath: 'C:\\work\\product\\Product.dsw',
        outputRoot: 'D:\\unit-test-output',
        defaultConfiguration: 'Win32 Debug',
      },
      'C:\\work\\product',
    );
    const missing = buildSettingsViewModel(
      {
        cliPath: 'unit-test-runner',
        sourceRoot: 'C:\\work\\product',
        dswPath: '',
        outputRoot: 'D:\\unit-test-output',
        defaultConfiguration: 'Win32 Debug',
      },
      'C:\\work\\product',
    );
    const warning = buildSettingsViewModel(
      {
        cliPath: 'unit-test-runner',
        sourceRoot: 'C:\\work\\product',
        dswPath: 'C:\\work\\product\\Product.dsw',
        outputRoot: 'C:\\work\\product\\generated',
        defaultConfiguration: 'Win32 Debug',
      },
      'C:\\work\\product',
    );

    assert.equal(ready.ready, true);
    assert.equal(missing.ready, false);
    assert.equal(warning.ready, true);
    assert.ok(warning.warnings.length > 0);

    const readyHtml = renderSettings(ready);
    const missingHtml = renderSettings(missing);
    const warningHtml = renderSettings(warning);

    assert.match(readyHtml, /<details class="settings">/);
    assert.doesNotMatch(readyHtml, /<details class="settings" open>/);
    assert.match(readyHtml, /<summary class="settings-summary">/);
    assert.match(readyHtml, /設定を表示/);
    assert.match(readyHtml, /data-setting-kind="pickFile"/);

    assert.match(missingHtml, /<details class="settings" open>/);
    assert.match(missingHtml, /未設定の必須項目があります。/);
    assert.match(warningHtml, /<details class="settings" open>/);
    assert.match(warningHtml, /本番リポジトリへ生成物が混入/);
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
    const reanalyze = buildReanalyzeFunctionInvocation(settings, target);
    const finalize = buildFinalizeDossierInvocation(settings, target.outputWorkspace);
    const runTests = buildRunTestsInvocation(settings, target.outputWorkspace, true);
    const testDesign = buildGenerateTestDesignInvocation(settings, path.join(target.outputWorkspace, 'reports', 'function_dossier.json'));
    const harness = buildGenerateHarnessSkeletonInvocation(settings, target.outputWorkspace);

    assert.equal(analyze.command, settings.cliPath);
    assert.ok(analyze.args.includes('--json'));
    assert.ok(analyze.args.includes('--finalize-dossier'));
    assert.ok(reanalyze.args.includes('reanalyze-function'));
    assert.ok(reanalyze.args.includes('--previous-dossier'));
    assert.equal(reanalyze.args.includes('--finalize-dossier'), false);
    assert.deepEqual(analyze.args.slice(analyze.args.indexOf('--configuration'), analyze.args.indexOf('--configuration') + 2), ['--configuration', 'Win32 Debug']);
    assert.ok(analyze.displayCommand.includes('"C:\\unit test workspace\\Control_Update"'));
    assert.deepEqual(finalize.args.slice(0, 3), ['--json', 'finalize-dossier', '--workspace']);
    assert.deepEqual(testDesign.args.slice(0, 3), ['--json', 'generate-test-design', '--dossier']);
    assert.deepEqual(harness.args.slice(0, 2), ['--json', 'generate-harness-skeleton']);
    assert.deepEqual(harness.args.slice(harness.args.indexOf('--test-case-design'), harness.args.indexOf('--test-case-design') + 2), ['--test-case-design', path.join(target.outputWorkspace, 'reports', 'test_case_design.json')]);
    assert.deepEqual(harness.args.slice(harness.args.indexOf('--out'), harness.args.indexOf('--out') + 2), ['--out', target.outputWorkspace]);
    assert.equal(runTests.requiresConfirmation, true);
  });

  it('prefers bundled CLI only when cliPath is default or empty', () => {
    const extensionRoot = 'C:\\Users\\me\\.vscode\\extensions\\unit-test-runner';
    const bundledPath = path.join(extensionRoot, 'bin', 'win32-x64', 'unit-test-runner.exe');
    const exists = (candidate: string) => candidate === bundledPath;

    assert.equal(resolveCliPath(DEFAULT_CLI_PATH, extensionRoot, exists, 'win32', 'x64'), bundledPath);
    assert.equal(resolveCliPath('', extensionRoot, exists, 'win32', 'x64'), bundledPath);
    assert.equal(resolveCliPath('D:\\tools\\unit-test-runner.exe', extensionRoot, exists, 'win32', 'x64'), 'D:\\tools\\unit-test-runner.exe');
    assert.equal(resolveCliPath(DEFAULT_CLI_PATH, extensionRoot, () => false, 'win32', 'x64'), DEFAULT_CLI_PATH);
    assert.equal(resolveCliPath(DEFAULT_CLI_PATH, extensionRoot, exists, 'linux', 'x64'), DEFAULT_CLI_PATH);
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
    const topLevel = parseCliResultReportPaths(
      JSON.stringify({
        status: 'dossier_finalized',
        reports: {
          function_dossier_md: 'C:\\work\\out\\Control_Update\\reports\\top_level_dossier.md',
          test_case_design_md: 'C:\\work\\out\\Control_Update\\reports\\top_level_design.md',
          test_case_design_json: 'C:\\work\\out\\Control_Update\\reports\\top_level_design.json',
          test_case_design_csv: 'C:\\work\\out\\Control_Update\\reports\\top_level_design.csv',
        },
      }),
      '',
      'C:\\work\\out\\Control_Update',
    );
    const fallback = parseCliResultReportPaths('plain output', '', 'C:\\work\\out\\Control_Update');
    const direct = resolveReportPaths('C:\\work\\out\\Control_Update');
    const directStep19 = parseCliResultReportPaths(
      JSON.stringify({
        status: 'reanalysis_completed',
        data: {
          reports: {
            change_impact_report_md: 'C:\\work\\out\\Control_Update\\reports\\custom_change.md',
            regression_selection_csv: 'C:\\work\\out\\Control_Update\\reports\\custom_regression.csv',
          },
        },
      }),
      '',
      'C:\\work\\out\\Control_Update',
    );

    assert.equal(path.basename(parsed.functionDossierMd ?? ''), 'function_dossier.md');
    assert.equal(path.basename(parsed.reviewChecklistMd ?? ''), 'review_checklist.md');
    assert.equal(path.basename(topLevel.functionDossierMd ?? ''), 'top_level_dossier.md');
    assert.equal(path.basename(topLevel.testCaseDesignMd ?? ''), 'top_level_design.md');
    assert.equal(path.basename(topLevel.testCaseDesignJson ?? ''), 'top_level_design.json');
    assert.equal(path.basename(topLevel.testCaseDesignCsv ?? ''), 'top_level_design.csv');
    assert.equal(path.basename(fallback.nextActionsMd ?? ''), 'next_actions.md');
    assert.equal(path.basename(direct.unresolvedItemsMd ?? ''), 'unresolved_items.md');
    assert.equal(path.basename(direct.testCaseDesignMd ?? ''), 'test_case_design.md');
    assert.equal(path.basename(direct.testCaseDesignJson ?? ''), 'test_case_design.json');
    assert.equal(path.basename(direct.changeImpactReportMd ?? ''), 'change_impact_report.md');
    assert.equal(path.basename(direct.regressionSelectionCsv ?? ''), 'regression_selection.csv');
    assert.equal(path.basename(directStep19.changeImpactReportMd ?? ''), 'custom_change.md');
    assert.equal(path.basename(directStep19.regressionSelectionCsv ?? ''), 'custom_regression.csv');
  });

  it('warns when CLI JSON omits report paths and uses conventional paths', () => {
    const parsed = parseCliResult(JSON.stringify({ status: 'ok', data: {} }), '', 'C:\\work\\out\\Control_Update');

    assert.ok(parsed.warnings.some((warning) => warning.includes('レポートパス')));
    assert.equal(path.basename(parsed.reports.functionDossierMd ?? ''), 'function_dossier.md');
  });

  it('requires confirmation only for explicit build and test execution commands', () => {
    assert.equal(commandRequiresConfirmation('build-probe', { run: false, dryRun: true }), false);
    assert.equal(commandRequiresConfirmation('build-probe', { run: true, dryRun: false }), true);
    assert.equal(commandRequiresConfirmation('run-tests', { run: true, dryRun: false }), true);
    assert.equal(commandRequiresConfirmation('finalize-dossier', {}), false);
  });

  it('returns a timedOut result when the CLI process exceeds the configured timeout', async () => {
    const result = await runCliInvocation({
      command: process.execPath,
      args: ['-e', 'setTimeout(() => {}, 1000)'],
      workingDirectory: process.cwd(),
      displayCommand: 'node timeout-fixture',
      timeoutSeconds: 0.01,
      requiresConfirmation: false,
    });

    assert.equal(result.timedOut, true);
    assert.equal(result.exitCode, null);
  });

  it('declares command palette activation and copy-last-command contribution', () => {
    const packageJson = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf-8'));
    const commands = new Set(packageJson.contributes.commands.map((item: { command: string }) => item.command));
    const commandTitles = new Map<string, string>(packageJson.contributes.commands.map((item: { command: string; title: string }) => [item.command, item.title]));
    const activationEvents = new Set(packageJson.activationEvents);

    for (const command of [
      'unitTestRunner.analyzeCurrentFunction',
      'unitTestRunner.analyzeSelectedFunction',
      'unitTestRunner.finalizeDossier',
      'unitTestRunner.generateTestDesign',
      'unitTestRunner.reanalyzeCurrentFunction',
      'unitTestRunner.openChangeImpactReport',
      'unitTestRunner.openRegressionSelection',
      'unitTestRunner.copyLastCommand',
      'unitTestRunner.openLastFunctionDossier',
      'unitTestRunner.generateHarnessSkeleton',
    ]) {
      assert.ok(commands.has(command), command);
      assert.ok(activationEvents.has(`onCommand:${command}`), command);
    }
    assert.equal(commandTitles.get('unitTestRunner.analyzeCurrentFunction'), 'UnitTestRunner: 現在関数を解析');
    assert.equal(commandTitles.get('unitTestRunner.openLastFunctionDossier'), 'UnitTestRunner: 最後の関数dossierを開く');
    assert.equal([...commandTitles.values()].some((title) => title.includes('Analyze Current Function')), false);
    assert.equal([...commandTitles.values()].some((title) => title.includes('Open Last Function Dossier')), false);
  });

  it('declares editor context menu and workflow view contributions', () => {
    const packageJson = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'package.json'), 'utf-8'));
    const activationEvents = new Set(packageJson.activationEvents);
    const contextMenus = packageJson.contributes.menus['editor/context'] as Array<{ command: string; when: string }>;
    const activityContainers = packageJson.contributes.viewsContainers.activitybar as Array<{ id: string; icon: string }>;
    const workflowViews = packageJson.contributes.views.unitTestRunner as Array<{ id: string; name: string; type?: string }>;

    assert.ok(activationEvents.has('onView:unitTestRunner.workflow'));
    assert.ok(activationEvents.has('onStartupFinished'));
    assert.ok(contextMenus.some((item) => item.command === 'unitTestRunner.analyzeCurrentFunction' && item.when.includes('editorLangId == c')));
    assert.ok(contextMenus.some((item) => item.command === 'unitTestRunner.analyzeSelectedFunction' && item.when.includes('editorHasSelection')));
    assert.ok(activityContainers.some((item) => item.id === 'unitTestRunner' && item.icon === 'media/unit-test-runner.svg'));
    assert.ok(workflowViews.some((item) => item.id === 'unitTestRunner.workflow' && item.name === 'ワークフロー' && item.type === 'webview'));
  });

  it('packages a VS Code extension README for the details view', () => {
    const readmePath = path.join(process.cwd(), 'README.md');
    const vscodeIgnore = fs.readFileSync(path.join(process.cwd(), '.vscodeignore'), 'utf-8');

    assert.equal(fs.existsSync(readmePath), true);
    assert.match(fs.readFileSync(readmePath, 'utf-8'), /# Unit Test Runner/);
    assert.equal(vscodeIgnore.split(/\r?\n/).some((line) => line.trim().toLowerCase() === 'readme.md'), false);
  });

  it('derives the current workflow step from generated artifacts', () => {
    const base = createInitialWorkflowState(true);

    assert.equal(deriveCurrentWorkflowStepId(base, availability()), 'analyze');
    assert.equal(deriveCurrentWorkflowStepId(base, availability({ functionDossier: true })), 'reviewDossier');
    assert.equal(deriveCurrentWorkflowStepId(base, availability({ functionDossier: true, testCaseDesign: true })), 'reviewTestDesign');
    assert.equal(deriveCurrentWorkflowStepId(
      { ...base, completedStepIds: ['settings', 'reviewTestDesign'] },
      availability({ functionDossier: true, testCaseDesign: true }),
    ), 'generateHarnessSkeleton');
    assert.equal(deriveCurrentWorkflowStepId(base, availability({ functionDossier: true, testCaseDesign: true, harnessSkeletonReport: true })), 'buildProbeDryRun');
    assert.equal(deriveCurrentWorkflowStepId(base, availability({ functionDossier: true, testCaseDesign: true, harnessSkeletonReport: true, buildProbeReport: true })), 'reviewBuildProbe');
    assert.equal(deriveCurrentWorkflowStepId(base, availability({ functionDossier: true, testCaseDesign: true, buildProbeReport: true, testExecutionReport: true, evidencePackage: true })), 'reviewEvidence');
  });

  it('shows harness generation as the required bridge from reviewed design to build probe', () => {
    const reviewIndex = WORKFLOW_STEP_DEFINITIONS.findIndex((step) => step.id === 'reviewTestDesign');
    const harnessIndex = WORKFLOW_STEP_DEFINITIONS.findIndex((step) => step.id === 'generateHarnessSkeleton');
    const probeIndex = WORKFLOW_STEP_DEFINITIONS.findIndex((step) => step.id === 'buildProbeDryRun');
    const harnessStep = WORKFLOW_STEP_DEFINITIONS[harnessIndex];

    assert.ok(reviewIndex >= 0);
    assert.ok(harnessIndex > reviewIndex);
    assert.ok(probeIndex > harnessIndex);
    assert.match(harnessStep.purpose, /Build Probe/);
    assert.match(harnessStep.requiredAction, /test_case_design\.json/);
    assert.equal(harnessStep.actions[0].commandId, 'unitTestRunner.generateHarnessSkeleton');
  });

  it('exposes markdown and json reports from the test design review step', () => {
    const reviewStep = WORKFLOW_STEP_DEFINITIONS.find((step) => step.id === 'reviewTestDesign');
    assert.ok(reviewStep);
    const actions = new Map(reviewStep.actions.map((action) => [action.label, action]));

    assert.equal(actions.get('CSVを開く')?.reportKey, 'testCaseDesignCsv');
    assert.equal(actions.get('Markdownを開く')?.reportKey, 'testCaseDesignMd');
    assert.equal(actions.get('JSONを開く')?.reportKey, 'testCaseDesignJson');
  });

  it('completes an awaiting-save workflow step only for the matching file', () => {
    const waiting = markStepAwaitingSave(
      createInitialWorkflowState(true),
      'reviewDossier',
      'C:\\out\\Control_Update\\reports\\function_dossier.md',
      'functionDossierMd',
    );
    const mismatch = completeAwaitingSaveIfMatches(waiting, 'C:\\out\\Control_Update\\reports\\review_checklist.md');
    const match = completeAwaitingSaveIfMatches(waiting, 'C:\\out\\Control_Update\\reports\\function_dossier.md');

    assert.equal(mismatch.matched, false);
    assert.equal(mismatch.state.completedStepIds.includes('reviewDossier'), false);
    assert.equal(match.matched, true);
    assert.equal(match.state.completedStepIds.includes('reviewDossier'), true);
    assert.equal(match.state.awaitingSave, undefined);
  });

  it('does not advance workflow recommendation after a CLI failure', () => {
    const outputWorkspace = 'C:\\out\\Control_Update';
    const analyzed = markWorkflowCommandSucceeded(createInitialWorkflowState(true), {
      kind: 'analyze',
      outputWorkspace,
      functionName: 'Control_Update',
      reports: {
        workspace: outputWorkspace,
        functionDossierMd: path.join(outputWorkspace, 'reports', 'function_dossier.md'),
      },
    });
    const failed = markWorkflowCommandFailed(analyzed, 'unit-test-runner exited with code 1.');

    assert.equal(failed.lastError, 'unit-test-runner exited with code 1.');
    assert.equal(deriveCurrentWorkflowStepId(failed, availability({ functionDossier: true })), 'reviewDossier');
  });

  it('projects workflow state to legacy global state keys', () => {
    const outputWorkspace = 'C:\\out\\Control_Update';
    const state = markWorkflowCommandSucceeded(createInitialWorkflowState(true), {
      kind: 'analyze',
      outputWorkspace,
      functionName: 'Control_Update',
      reports: {
        workspace: outputWorkspace,
        functionDossierMd: path.join(outputWorkspace, 'reports', 'function_dossier.md'),
      },
    });
    const legacy = workflowLegacyProjection(state);

    assert.equal(legacy.lastWorkspace, outputWorkspace);
    assert.equal(legacy.lastDossier, path.join(outputWorkspace, 'reports', 'function_dossier.md'));
  });

  it('opens markdown reports with preview but plain files without markdown preview', () => {
    const opener = fs.readFileSync(path.join(process.cwd(), 'src', 'reports', 'reportOpener.ts'), 'utf-8');

    assert.ok(opener.includes('openReport(reportPath: string)'));
    assert.ok(opener.includes("path.extname(reportPath).toLowerCase() === '.md'"));
    assert.ok(opener.includes("vscode.commands.executeCommand('vscode.open', uri)"));
  });
});

function availability(overrides: Partial<WorkflowReportAvailability> = {}): WorkflowReportAvailability {
  return { ...EMPTY_REPORT_AVAILABILITY, ...overrides };
}

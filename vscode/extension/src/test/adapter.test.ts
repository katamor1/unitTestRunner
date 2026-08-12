import * as assert from 'assert';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { describe, it } from 'node:test';

import {
  buildAnalyzeFunctionInvocation,
  buildBuildProbeInvocation,
  buildPrepareHarnessInvocation,
  buildReviewSetInvocation,
  buildRunTestsInvocation,
  buildSuiteRegisterInvocation,
  buildSuiteRunInvocation,
  buildSuiteUpdateInvocation,
} from '../cli/commandBuilder';
import { parseCliResult, parseValidatedCliSuccess } from '../cli/cliResultParser';
import { DEFAULT_CLI_PATH, resolveCliPath } from '../config/bundledCli';
import { defaultSourceRootFromWorkspaceFolder, readAdapterSettingsFromObject } from '../config/settings';
import { preflightInvocation, validateSettings } from '../config/validation';
import { resolveFunctionNameFromText } from '../functionTarget/regexFunctionResolver';
import { resolveReportPaths } from '../reports/reportPathResolver';
import {
  createInitialWorkflowState,
  deriveCurrentWorkflowStepId,
  EMPTY_REPORT_AVAILABILITY,
  markWorkflowCommandFailed,
  markWorkflowCommandSucceeded,
  WorkflowState,
} from '../workflow/workflowState';

function settings(overrides: Record<string, unknown> = {}) {
  return readAdapterSettingsFromObject({
    cliPath: 'unit-test-runner',
    sourceRoot: 'C:\\work\\product',
    dswPath: 'C:\\work\\product\\Product.dsw',
    outputRoot: 'D:\\unit-test-output',
    defaultConfiguration: 'Control - Win32 Debug',
    defaultProject: 'Control',
    commandTimeoutSeconds: 30,
    ...overrides,
  }, 'C:\\work\\product');
}

function target() {
  return {
    sourcePath: 'C:\\work\\product\\src\\control.c',
    sourceRelativePath: 'src/control.c',
    functionName: 'Control_Update',
    project: 'Control',
    configuration: 'Control - Win32 Debug',
    outputWorkspace: 'D:\\unit-test-output\\fn_Control_Update_deadbeef0000',
  };
}

function envelope(outcome = 'passed') {
  return {
    command: 'analyze-function',
    outcome,
    message: 'done',
    artifacts: [
      { kind: 'function_dossier', path: 'reports/function_dossier.json', sha256: 'a'.repeat(64) },
      { kind: 'test_spec', path: 'reports/test_spec.json', sha256: 'b'.repeat(64) },
    ],
    diagnostics: [{ code: 'representative', level: 'warning', message: 'review this' }],
  };
}

describe('UnitTestRunner v0.1 VS Code adapter', () => {
  it('uses only resource-scoped settings and no legacy aliases', () => {
    const root = defaultSourceRootFromWorkspaceFolder({ uri: { fsPath: 'D:\\active' } });
    const value = readAdapterSettingsFromObject({ workspaceRoot: 'D:\\legacy', projectName: 'Legacy' }, root);
    assert.equal(value.sourceRoot, root);
    assert.equal(value.defaultProject, '');
    assert.equal(value.cliPath, DEFAULT_CLI_PATH);
    assert.deepEqual(Object.keys(value).sort(), [
      'autoOpenDossier', 'cliPath', 'commandTimeoutSeconds', 'defaultConfiguration', 'defaultProject',
      'dswPath', 'outputRoot', 'runBuildProbeRequiresConfirmation', 'runTestsRequiresConfirmation',
      'sourceRoot', 'suiteManifestPath', 'vcvarsPath',
    ]);
  });

  it('preflights executable, DSW, source containment, output boundary, and timeout', () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'utr-v01-preflight-'));
    try {
      const sourceRoot = path.join(root, 'source');
      const outputRoot = path.join(root, 'output');
      fs.mkdirSync(sourceRoot);
      fs.mkdirSync(outputRoot);
      const source = path.join(sourceRoot, 'control.c');
      const dsw = path.join(sourceRoot, 'Product.dsw');
      const cli = path.join(root, process.platform === 'win32' ? 'utr.exe' : 'utr');
      fs.writeFileSync(source, 'int f(void){return 0;}');
      fs.writeFileSync(dsw, 'Microsoft Developer Studio Workspace File');
      fs.writeFileSync(cli, 'placeholder');
      const valid = readAdapterSettingsFromObject({ cliPath: cli, sourceRoot, dswPath: dsw, outputRoot, commandTimeoutSeconds: 10 }, sourceRoot);
      assert.equal(preflightInvocation(valid, source).ok, true);
      assert.equal(validateSettings({ ...valid, outputRoot: path.join(sourceRoot, 'generated') }).ok, true);
      assert.ok(validateSettings({ ...valid, outputRoot: path.join(sourceRoot, 'generated') }).warnings.some((item) => item.code === 'output_root_inside_source_root'));
      assert.ok(preflightInvocation({ ...valid, commandTimeoutSeconds: 0 }, source).warnings.some((item) => item.code === 'invalid_timeout'));
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  });

  it('builds only formal v0.1 CLI commands with explicit execution selectors', () => {
    const analyze = buildAnalyzeFunctionInvocation(settings(), target());
    const harness = buildPrepareHarnessInvocation(settings(), target());
    const review = buildReviewSetInvocation(settings(), target().outputWorkspace, 'test_spec', 'c'.repeat(64), 'approved', 'reviewer', 'ok');
    const dryBuild = buildBuildProbeInvocation(settings(), target().outputWorkspace, false);
    const run = buildRunTestsInvocation(settings(), target().outputWorkspace, true, { all: true });
    assert.deepEqual(analyze.args.slice(0, 2), ['--json', 'analyze-function']);
    assert.deepEqual(analyze.args.slice(analyze.args.indexOf('--phase'), analyze.args.indexOf('--phase') + 2), ['--phase', 'design']);
    assert.equal(analyze.args.includes('--finalize-dossier'), false);
    assert.deepEqual(harness.args.slice(harness.args.indexOf('--phase'), harness.args.indexOf('--phase') + 2), ['--phase', 'harness']);
    assert.equal(review.args.includes('review-set'), true);
    assert.equal(dryBuild.args.includes('--dry-run'), true);
    assert.equal(dryBuild.requiresConfirmation, false);
    assert.equal(run.args.includes('--all'), true);
    assert.equal(run.args.includes('--run'), true);
    assert.equal(run.requiresConfirmation, true);
  });

  it('builds revision-guarded suite mutations and explicit selected runs', () => {
    const register = buildSuiteRegisterInvocation(settings(), target(), ['smoke'], 0);
    const update = buildSuiteUpdateInvocation(settings(), 'entry-1', false, 2);
    const run = buildSuiteRunInvocation(settings(), { entryIds: ['entry-1', 'entry-2'], run: true });
    assert.deepEqual(register.args.slice(-4), ['--expected-revision', '0', '--tags', 'smoke']);
    assert.deepEqual(update.args.slice(-4), ['--enabled', 'false', '--expected-revision', '2']);
    assert.deepEqual(run.args.filter((value) => value === '--entry-id'), ['--entry-id', '--entry-id']);
    assert.equal(run.args.includes('--all'), false);
  });

  it('strictly parses the five-key CLI envelope and derives public report paths', () => {
    const workspace = 'D:\\unit-test-output\\fn_Control_Update_deadbeef0000';
    const parsed = parseCliResult(JSON.stringify(envelope()), '', workspace);
    assert.equal(parsed.status, 'passed');
    assert.deepEqual(parsed.warnings, ['review this']);
    assert.equal(parsed.reports.functionDossierJson, path.win32.join(workspace, 'reports', 'function_dossier.json'));
    assert.equal(parsed.reports.testSpecJson, path.win32.join(workspace, 'reports', 'test_spec.json'));
    assert.throws(() => parseCliResult(JSON.stringify({ ...envelope(), data: {} }), '', workspace), /Malformed/);
    assert.throws(() => parseValidatedCliSuccess(JSON.stringify(envelope('failed')), '', workspace, false), /cannot advance/);
  });

  it('does not advance workflow from file existence and invalidates downstream state', () => {
    const initial = createInitialWorkflowState(true);
    assert.equal(deriveCurrentWorkflowStepId(initial, { ...EMPTY_REPORT_AVAILABILITY, functionDossier: true, testSpec: true }), 'analyze');
    const analyzed = markWorkflowCommandSucceeded(initial, { kind: 'analyze', outputWorkspace: 'D:\\out', sourcePath: 'C:\\src\\x.c', functionName: 'f' });
    assert.equal(deriveCurrentWorkflowStepId(analyzed, EMPTY_REPORT_AVAILABILITY), 'finalizeDossier');
    const built = markWorkflowCommandSucceeded({ ...analyzed, completedStepIds: ['settings', 'analyze', 'finalizeDossier', 'reviewTestSpec', 'prepareHarness', 'buildProbeDryRun', 'buildProbeRun'] }, { kind: 'review', reviewDecision: 'approved' });
    assert.equal(built.completedStepIds.includes('buildProbeRun'), false);
    assert.equal(built.completedStepIds.includes('reviewTestSpec'), true);
    assert.equal(markWorkflowCommandFailed(built, 'failed').completedStepIds.includes('reviewTestSpec'), true);
  });

  it('keeps a changes-requested review current while retaining its record', () => {
    const analyzed = markWorkflowCommandSucceeded(createInitialWorkflowState(true), {
      kind: 'analyze', outputWorkspace: 'D:\\out', sourcePath: 'C:\\src\\x.c', functionName: 'f',
    });
    const previouslyAdvanced: WorkflowState = {
      ...analyzed,
      completedStepIds: ['settings', 'analyze', 'finalizeDossier', 'reviewTestSpec', 'prepareHarness', 'buildProbeDryRun', 'buildProbeRun', 'runTests', 'complete'],
    };

    const reviewed = markWorkflowCommandSucceeded(previouslyAdvanced, {
      kind: 'review',
      reviewDecision: 'changes_requested',
      reports: { workspace: 'D:\\out', reviewRecordJson: 'D:\\out\\reports\\review_record.json' },
    });

    assert.equal(reviewed.completedStepIds.includes('reviewTestSpec'), false);
    assert.equal(reviewed.completedStepIds.includes('prepareHarness'), false);
    assert.equal(reviewed.completedStepIds.includes('buildProbeRun'), false);
    assert.equal(reviewed.completedStepIds.includes('runTests'), false);
    assert.equal(reviewed.completedStepIds.includes('complete'), false);
    assert.equal(deriveCurrentWorkflowStepId(reviewed, EMPTY_REPORT_AVAILABILITY), 'reviewTestSpec');
    assert.equal(reviewed.reports?.reviewRecordJson, 'D:\\out\\reports\\review_record.json');
  });

  it('resolves canonical public artifact views and bundled CLI preference', () => {
    const reports = resolveReportPaths('C:\\out\\f');
    assert.equal(reports.testRunReportJson, undefined);
    assert.equal(reports.testRunReportMd, undefined);
    assert.equal(reports.reanalysisReportJson, path.win32.join('C:\\out\\f', 'reports', 'reanalysis_report.json'));
    assert.equal(resolveCliPath(DEFAULT_CLI_PATH, 'C:\\extension', (candidate) => candidate.endsWith('unit-test-runner.exe'), 'win32', 'x64'), path.win32.join('C:\\extension', 'bin', 'win32-x64', 'unit-test-runner.exe'));
  });

  it('resolves a C function from selection or cursor without an internal parser copy', () => {
    const text = 'static int Control_Update(int value) {\n  return value;\n}\n';
    assert.equal(resolveFunctionNameFromText({ selectedText: 'Control_Update', documentText: text, cursorOffset: 0 }), 'Control_Update');
    assert.equal(resolveFunctionNameFromText({ selectedText: '', documentText: text, cursorOffset: text.indexOf('return') }), 'Control_Update');
  });
});

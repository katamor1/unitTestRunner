import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

import { activate as activateBase, deactivate as deactivateBase } from './extension';
import {
  buildFullGateAnalyzeInvocation,
  buildQuickCheckInvocation,
  buildQuickOutputWorkspace,
  CliInvocation,
  FunctionTarget,
  normalizeQuickCheckProfile,
  relativeSourcePath,
} from './cli/commandBuilder';
import { CliResult, runCliInvocation } from './cli/cliRunner';
import { formatCliFailureMessage, parseCliResult } from './cli/cliResultParser';
import { DEFAULT_CLI_PATH, resolveCliPath } from './config/bundledCli';
import { AdapterSettings, defaultSourceRootFromWorkspaceFolders, RawSettings, readAdapterSettingsFromObject } from './config/settings';
import { validateSettings } from './config/validation';
import { resolveFunctionNameFromText } from './functionTarget/regexFunctionResolver';
import { openMarkdown, openReport } from './reports/reportOpener';
import { ReportPaths, resolveReportPaths } from './reports/reportPathResolver';

const LAST_DOSSIER_KEY = 'unitTestRunner.lastFunctionDossierMarkdown';
const LAST_WORKSPACE_KEY = 'unitTestRunner.lastOutputWorkspace';
const LAST_COMMAND_KEY = 'unitTestRunner.lastCliCommand';
const LAST_QUICK_SUMMARY_KEY = 'unitTestRunner.lastQuickSummaryMarkdown';

interface QuickSummaryDetails {
  globalsRead: number;
  globalsWritten: number;
  externalCalls: number;
  branches: number;
  branchCoverageItems: number;
  conditionCoverageItems: number;
  stubCandidates: number;
  diagnostics: number;
  testCaseDesignStatus?: string;
  harnessStatus?: string;
  buildProbeStatus?: string;
}

interface QuickSummary {
  schema_version: string;
  mode: 'quick_check';
  profile: string;
  function: string;
  source: string;
  workspace: string;
  note: string;
  details?: QuickSummaryDetails;
  reports: Record<string, string | undefined>;
}

export function activate(context: vscode.ExtensionContext): void {
  activateBase(context);
  const output = vscode.window.createOutputChannel('Unit Test Runner Quick');
  context.subscriptions.push(output);
  context.subscriptions.push(
    vscode.commands.registerCommand('unitTestRunner.quickCheckCurrentFunction', async () => quickCheckActiveFunction(context, output)),
    vscode.commands.registerCommand('unitTestRunner.quickCheckSelectedFunction', async () => quickCheckActiveFunction(context, output)),
    vscode.commands.registerCommand('unitTestRunner.openQuickSummary', async () => openQuickSummary(context)),
    vscode.commands.registerCommand('unitTestRunner.runFullGateForCurrentFunction', async () => runFullGateForActiveFunction(context, output)),
  );
}

export function deactivate(): void {
  deactivateBase();
}

async function quickCheckActiveFunction(context: vscode.ExtensionContext, output: vscode.OutputChannel): Promise<void> {
  const settings = readConfig(context);
  showValidation(settings);
  const target = await activeFunctionTarget(settings);
  const quickWorkspace = buildQuickOutputWorkspace(settings, target);
  const invocation = buildQuickCheckInvocation(settings, target);
  const reports = await executeInvocation(context, output, settings, invocation, quickWorkspace);
  const summaryReports = writeQuickSummary(settings, target, reports);
  await recordReports(context, summaryReports);
  if (settings.quickAutoOpenSummary && summaryReports.quickSummaryMd) {
    await openMarkdown(summaryReports.quickSummaryMd);
  }
  void vscode.window.showInformationMessage(`UnitTestRunner: Quick Check completed for ${target.functionName}.`);
}

async function runFullGateForActiveFunction(context: vscode.ExtensionContext, output: vscode.OutputChannel): Promise<void> {
  const settings = readConfig(context);
  showValidation(settings);
  const target = await activeFunctionTarget(settings);
  const fullGateTarget = {
    ...target,
    outputWorkspace: path.join(settings.outputRoot, target.functionName),
  };
  const invocation = buildFullGateAnalyzeInvocation(settings, fullGateTarget);
  const reports = await executeInvocation(context, output, settings, invocation, fullGateTarget.outputWorkspace);
  await recordReports(context, reports);
  if (reports.functionDossierMd) {
    await openMarkdown(reports.functionDossierMd);
  }
  void vscode.window.showInformationMessage(`UnitTestRunner: Full Gate dossier finalized for ${target.functionName}.`);
}

async function activeFunctionTarget(settings: AdapterSettings): Promise<FunctionTarget> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    throw new Error('UnitTestRunnerを実行する前にCソースファイルを開いてください。');
  }
  const functionName = await resolveFunctionName(editor);
  const sourceRelativePath = relativeSourcePath(editor.document.uri.fsPath, settings.sourceRoot);
  return {
    sourcePath: editor.document.uri.fsPath,
    sourceRelativePath,
    functionName,
    project: settings.defaultProject,
    configuration: settings.defaultConfiguration,
    outputWorkspace: path.join(settings.outputRoot, functionName),
  };
}

async function executeInvocation(context: vscode.ExtensionContext, output: vscode.OutputChannel, settings: AdapterSettings, invocation: CliInvocation, outputWorkspace: string): Promise<ReportPaths> {
  await context.globalState.update(LAST_COMMAND_KEY, invocation.displayCommand);
  if (settings.showOutputChannel) {
    output.show(true);
  }
  output.appendLine(`> ${invocation.displayCommand}`);
  let result: CliResult;
  try {
    result = await runCliInvocation(invocation);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`unit-test-runnerを起動できませんでした。${message}`);
  }
  output.append(result.stdout);
  output.append(result.stderr);
  if (result.timedOut) {
    throw new Error('unit-test-runnerがタイムアウトしました。');
  }
  if (result.exitCode !== 0) {
    throw new Error(formatCliFailureMessage(result.stdout, result.stderr, result.exitCode));
  }
  const parsed = parseCliResult(result.stdout, result.stderr, outputWorkspace);
  return parsed.reports;
}

function writeQuickSummary(settings: AdapterSettings, target: FunctionTarget, reports: ReportPaths): ReportPaths {
  const resolved = {
    ...resolveReportPaths(reports.workspace),
    ...reports,
  };
  const quickSummaryMd = resolved.quickSummaryMd ?? path.join(reports.workspace, 'reports', 'quick_summary.md');
  const quickSummaryJson = resolved.quickSummaryJson ?? path.join(reports.workspace, 'reports', 'quick_summary.json');
  fs.mkdirSync(path.dirname(quickSummaryMd), { recursive: true });
  const profile = normalizeQuickCheckProfile(settings.quickProfile);
  const summary: QuickSummary = {
    schema_version: '0.1',
    mode: 'quick_check',
    profile,
    function: target.functionName,
    source: target.sourceRelativePath ?? target.sourcePath,
    workspace: reports.workspace,
    note: 'Quick Check is an iterative design aid. Use Full Gate before review.',
    details: readQuickSummaryDetails(reports.workspace),
    reports: {
      function_dossier_md: resolved.functionDossierMd,
      test_case_design_md: resolved.testCaseDesignMd,
      test_case_design_csv: resolved.testCaseDesignCsv,
      harness_skeleton_report_md: resolved.harnessSkeletonReportMd,
      build_probe_report_md: resolved.buildProbeReportMd,
      quick_summary_md: quickSummaryMd,
      quick_summary_json: quickSummaryJson,
    },
  };
  fs.writeFileSync(quickSummaryJson, JSON.stringify(summary, null, 2) + '\n', 'utf-8');
  fs.writeFileSync(quickSummaryMd, renderQuickSummary(summary), 'utf-8');
  return {
    ...resolved,
    quickSummaryMd,
    quickSummaryJson,
  };
}

function readQuickSummaryDetails(workspace: string): QuickSummaryDetails | undefined {
  const dossierPath = path.join(workspace, 'reports', 'function_dossier.json');
  const dossier = readJsonObject(dossierPath);
  if (!dossier) {
    return undefined;
  }
  const functionPayload = objectValue(dossier.function);
  const testDesignPayload = objectValue(dossier.test_design);
  const testCaseDesignPayload = objectValue(dossier.test_case_design);
  const harnessPayload = objectValue(dossier.harness_skeleton);
  const buildProbePayload = objectValue(dossier.build_probe);
  return {
    globalsRead: arrayLength(functionPayload.globals_read),
    globalsWritten: arrayLength(functionPayload.globals_written),
    externalCalls: arrayLength(functionPayload.external_calls),
    branches: arrayLength(functionPayload.branches),
    branchCoverageItems: arrayLength(testDesignPayload.branch_coverage_items),
    conditionCoverageItems: arrayLength(testDesignPayload.condition_coverage_items),
    stubCandidates: arrayLength(testDesignPayload.stub_candidates),
    diagnostics: arrayLength(dossier.diagnostics),
    testCaseDesignStatus: stringValue(testCaseDesignPayload.status),
    harnessStatus: stringValue(harnessPayload.status),
    buildProbeStatus: stringValue(buildProbePayload.status),
  };
}

function renderQuickSummary(summary: QuickSummary): string {
  return [
    `# Quick Check: ${summary.function}`,
    '',
    'このレポートは機能設計中の反復確認用です。レビュー前の正式確認には Full Gate を実行してください。',
    '',
    '## 対象',
    `- 関数: \`${summary.function}\``,
    `- ソース: \`${summary.source}\``,
    `- profile: \`${summary.profile}\``,
    `- workspace: \`${summary.workspace}\``,
    '',
    '## 動作確認サマリ',
    renderDetails(summary.details),
    '',
    '## 主要レポート',
    quickReportLine('function_dossier.md', summary.reports.function_dossier_md),
    quickReportLine('test_case_design.md', summary.reports.test_case_design_md),
    quickReportLine('test_case_design.csv', summary.reports.test_case_design_csv),
    quickReportLine('harness_skeleton_report.md', summary.reports.harness_skeleton_report_md),
    quickReportLine('build_probe_report.md', summary.reports.build_probe_report_md),
    '',
    '## 次の使い分け',
    '- 開発中の確認を続ける場合: Quick Check を再実行します。',
    '- レビューに進める場合: `UnitTestRunner: Full Gate for Current Function` を実行します。',
    '',
  ].join('\n');
}

function renderDetails(details: QuickSummaryDetails | undefined): string {
  if (!details) {
    return '- function_dossier.json がまだ読めないため、主要レポートを直接確認してください。';
  }
  return [
    `- グローバル参照: read ${details.globalsRead} / write ${details.globalsWritten}`,
    `- 外部呼び出し候補: ${details.externalCalls}`,
    `- 分岐候補: ${details.branches}`,
    `- カバレッジ観点: branch ${details.branchCoverageItems} / condition ${details.conditionCoverageItems}`,
    `- スタブ候補: ${details.stubCandidates}`,
    `- diagnostics: ${details.diagnostics}`,
    `- test_case_design: ${details.testCaseDesignStatus ?? '未生成'}`,
    `- harness: ${details.harnessStatus ?? '未生成'}`,
    `- build probe: ${details.buildProbeStatus ?? '未生成'}`,
  ].join('\n');
}

function quickReportLine(label: string, filePath: string | undefined): string {
  return filePath ? `- ${label}: \`${filePath}\`` : `- ${label}: 未生成`;
}

async function recordReports(context: vscode.ExtensionContext, reports: ReportPaths): Promise<void> {
  await context.globalState.update(LAST_WORKSPACE_KEY, reports.workspace);
  if (reports.functionDossierMd) {
    await context.globalState.update(LAST_DOSSIER_KEY, reports.functionDossierMd);
  }
  if (reports.quickSummaryMd) {
    await context.globalState.update(LAST_QUICK_SUMMARY_KEY, reports.quickSummaryMd);
  }
}

async function openQuickSummary(context: vscode.ExtensionContext): Promise<void> {
  const remembered = context.globalState.get<string>(LAST_QUICK_SUMMARY_KEY);
  const workspace = context.globalState.get<string>(LAST_WORKSPACE_KEY);
  const reportPath = remembered || (workspace ? resolveReportPaths(workspace).quickSummaryMd : undefined);
  if (!reportPath) {
    throw new Error('記録済みのQuick Check summaryがありません。');
  }
  await openReport(reportPath);
}

function readRawConfig(): RawSettings {
  const config = vscode.workspace.getConfiguration('unitTestRunner');
  return {
    cliPath: config.get('cliPath'),
    sourceRoot: config.get('sourceRoot'),
    workspaceRoot: config.get('workspaceRoot'),
    dswPath: config.get('dswPath'),
    outputRoot: config.get('outputRoot'),
    suiteManifestPath: config.get('suiteManifestPath'),
    defaultConfiguration: config.get('defaultConfiguration'),
    defaultProject: config.get('defaultProject'),
    projectName: config.get('projectName'),
    vcvarsPath: config.get('vcvarsPath'),
    autoOpenDossier: config.get('autoOpenDossier'),
    finalizeDossierAfterAnalyze: config.get('finalizeDossierAfterAnalyze'),
    useJsonOutput: config.get('useJsonOutput'),
    showOutputChannel: config.get('showOutputChannel'),
    runBuildProbeRequiresConfirmation: config.get('runBuildProbeRequiresConfirmation'),
    runTestsRequiresConfirmation: config.get('runTestsRequiresConfirmation'),
    commandTimeoutSeconds: config.get('commandTimeoutSeconds'),
    quickProfile: config.get('quickProfile'),
    quickOutputRoot: config.get('quickOutputRoot'),
    quickReusePreviousWorkspace: config.get('quickReusePreviousWorkspace'),
    quickAutoOpenSummary: config.get('quickAutoOpenSummary'),
    quickAllowExecution: config.get('quickAllowExecution'),
  };
}

function readConfig(context: vscode.ExtensionContext): AdapterSettings {
  const settings = readAdapterSettingsFromObject(readRawConfig(), defaultSourceRoot());
  return { ...settings, cliPath: resolveCliPath(settings.cliPath, context.extensionPath) };
}

function defaultSourceRoot(): string {
  return defaultSourceRootFromWorkspaceFolders(vscode.workspace.workspaceFolders);
}

function showValidation(settings: AdapterSettings): void {
  const validation = validateSettings(settings);
  for (const warning of validation.warnings) {
    if (!warning.code.startsWith('missing_')) {
      void vscode.window.showWarningMessage(`UnitTestRunner: ${warning.message}`);
    }
  }
  if (!validation.ok) {
    throw new Error(`UnitTestRunnerの設定が不足しています: ${validation.warnings.map((warning) => warning.message).join(' ')}`);
  }
}

async function resolveFunctionName(editor: vscode.TextEditor): Promise<string> {
  const resolved = resolveFunctionNameFromText({
    selectedText: editor.document.getText(editor.selection),
    documentText: editor.document.getText(),
    cursorOffset: editor.document.offsetAt(editor.selection.active),
  });
  if (resolved) {
    return resolved;
  }
  const prompt = await vscode.window.showInputBox({
    prompt: '解析する関数名を入力してください。',
    validateInput: (value) => (/^[A-Za-z_]\w*$/.test(value) ? undefined : 'Cの関数識別子を入力してください。'),
  });
  if (!prompt) {
    throw new Error('関数解析をキャンセルしました。');
  }
  return prompt;
}

function readJsonObject(filePath: string): Record<string, unknown> | undefined {
  try {
    if (!fs.existsSync(filePath)) {
      return undefined;
    }
    const parsed = JSON.parse(fs.readFileSync(filePath, 'utf-8')) as unknown;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : undefined;
  } catch {
    return undefined;
  }
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function arrayLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

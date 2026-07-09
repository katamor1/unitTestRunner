import * as path from 'path';
import * as vscode from 'vscode';

import { activate as activateCore, deactivate as deactivateCore } from './extension';
import {
  buildFullGateAnalyzeInvocation,
  buildQuickCheckInvocation,
  buildQuickOutputWorkspace,
  CliInvocation,
  FunctionTarget,
  relativeSourcePath,
} from './cli/commandBuilder';
import { CliResult, runCliInvocation } from './cli/cliRunner';
import { formatCliFailureMessage, parseCliResult } from './cli/cliResultParser';
import { resolveCliPath } from './config/bundledCli';
import { AdapterSettings, defaultSourceRootFromWorkspaceFolders, RawSettings, readAdapterSettingsFromObject } from './config/settings';
import { validateSettings } from './config/validation';
import { resolveFunctionNameFromText } from './functionTarget/regexFunctionResolver';
import { ReportPaths, resolveReportPaths } from './reports/reportPathResolver';
import { openMarkdown, openReport } from './reports/reportOpener';
import {
  createInitialWorkflowState,
  markWorkflowCommandFailed,
  markWorkflowCommandSucceeded,
  WorkflowState,
  workflowLegacyProjection,
  WORKFLOW_STATE_KEY,
} from './workflow/workflowState';

const LAST_DOSSIER_KEY = 'unitTestRunner.lastFunctionDossierMarkdown';
const LAST_WORKSPACE_KEY = 'unitTestRunner.lastOutputWorkspace';
const LAST_COMMAND_KEY = 'unitTestRunner.lastCliCommand';

export function activate(context: vscode.ExtensionContext): void {
  activateCore(context);

  const output = vscode.window.createOutputChannel('Unit Test Runner Quick');
  context.subscriptions.push(output);
  context.subscriptions.push(
    vscode.commands.registerCommand('unitTestRunner.quickCheckCurrentFunction', () => runQuickCommand(() => quickCheckActiveFunction(context, output))),
    vscode.commands.registerCommand('unitTestRunner.quickCheckSelectedFunction', () => runQuickCommand(() => quickCheckActiveFunction(context, output))),
    vscode.commands.registerCommand('unitTestRunner.openQuickSummary', () => runQuickCommand(() => openQuickSummary(context))),
    vscode.commands.registerCommand('unitTestRunner.runFullGateForCurrentFunction', () => runQuickCommand(() => runFullGateForCurrentFunction(context, output))),
  );
}

export function deactivate(): void {
  deactivateCore();
}

async function runQuickCommand(action: () => Promise<void>): Promise<void> {
  try {
    await action();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    void vscode.window.showErrorMessage(`UnitTestRunner: ${message}`);
  }
}

async function quickCheckActiveFunction(context: vscode.ExtensionContext, output: vscode.OutputChannel): Promise<void> {
  const settings = readConfig(context);
  showValidation(settings);
  const targetBase = await activeFunctionTarget(settings);
  const outputWorkspace = buildQuickOutputWorkspace(settings, targetBase);
  const target = { ...targetBase, outputWorkspace };
  const invocation = buildQuickCheckInvocation(settings, target);
  const reports = await executeInvocation(context, output, invocation, outputWorkspace);
  await recordWorkflowSuccess(context, {
    kind: 'analyze',
    outputWorkspace,
    functionName: target.functionName,
    reports,
  });
  if (settings.quickAutoOpenSummary && reports.quickSummaryMd) {
    await openMarkdown(reports.quickSummaryMd);
  }
}

async function runFullGateForCurrentFunction(context: vscode.ExtensionContext, output: vscode.OutputChannel): Promise<void> {
  const settings = readConfig(context);
  showValidation(settings);
  const target = await activeFunctionTarget(settings);
  const invocation = buildFullGateAnalyzeInvocation(settings, target);
  const reports = await executeInvocation(context, output, invocation, target.outputWorkspace);
  await recordWorkflowSuccess(context, {
    kind: 'analyze',
    outputWorkspace: target.outputWorkspace,
    functionName: target.functionName,
    reports,
  });
  if (settings.autoOpenDossier && reports.functionDossierMd) {
    await openMarkdown(reports.functionDossierMd);
  }
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

async function executeInvocation(context: vscode.ExtensionContext, output: vscode.OutputChannel, invocation: CliInvocation, outputWorkspace: string): Promise<ReportPaths> {
  await context.globalState.update(LAST_COMMAND_KEY, invocation.displayCommand);
  output.show(true);
  output.appendLine(`> ${invocation.displayCommand}`);
  let result: CliResult;
  try {
    result = await runCliInvocation(invocation);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await recordWorkflowError(context, message);
    throw error;
  }
  output.append(result.stdout);
  output.append(result.stderr);
  if (result.timedOut) {
    const message = 'unit-test-runnerがタイムアウトしました。';
    await recordWorkflowError(context, message);
    throw new Error(message);
  }
  if (result.exitCode !== 0) {
    const message = formatCliFailureMessage(result.stdout, result.stderr, result.exitCode);
    await recordWorkflowError(context, message);
    throw new Error(message);
  }
  const parsed = parseCliResult(result.stdout, result.stderr, outputWorkspace);
  await context.globalState.update(LAST_WORKSPACE_KEY, parsed.reports.workspace);
  return parsed.reports;
}

async function openQuickSummary(context: vscode.ExtensionContext): Promise<void> {
  const workspace = context.globalState.get<string>(LAST_WORKSPACE_KEY);
  if (!workspace) {
    throw new Error('記録済みのQuick Check出力workspaceがありません。');
  }
  await openReport(resolveReportPaths(workspace).quickSummaryMd ?? path.join(workspace, 'reports', 'quick_summary.md'));
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
    quickProfile: config.get('quickProfile'),
    quickOutputRoot: config.get('quickOutputRoot'),
    quickReusePreviousWorkspace: config.get('quickReusePreviousWorkspace'),
    quickAutoOpenSummary: config.get('quickAutoOpenSummary'),
    quickAllowExecution: config.get('quickAllowExecution'),
    useJsonOutput: config.get('useJsonOutput'),
    showOutputChannel: config.get('showOutputChannel'),
    runBuildProbeRequiresConfirmation: config.get('runBuildProbeRequiresConfirmation'),
    runTestsRequiresConfirmation: config.get('runTestsRequiresConfirmation'),
    commandTimeoutSeconds: config.get('commandTimeoutSeconds'),
  };
}

function readConfig(context: vscode.ExtensionContext): AdapterSettings {
  const settings = readAdapterSettingsFromObject(
    readRawConfig(),
    defaultSourceRootFromWorkspaceFolders(vscode.workspace.workspaceFolders),
  );
  return { ...settings, cliPath: resolveCliPath(settings.cliPath, context.extensionPath) };
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

async function recordWorkflowSuccess(context: vscode.ExtensionContext, event: Parameters<typeof markWorkflowCommandSucceeded>[1]): Promise<void> {
  const state = readWorkflowState(context);
  const next = markWorkflowCommandSucceeded(state, event);
  await context.workspaceState.update(WORKFLOW_STATE_KEY, next);
  const legacy = workflowLegacyProjection(next);
  if (legacy.lastWorkspace) {
    await context.globalState.update(LAST_WORKSPACE_KEY, legacy.lastWorkspace);
  }
  if (legacy.lastDossier) {
    await context.globalState.update(LAST_DOSSIER_KEY, legacy.lastDossier);
  }
}

async function recordWorkflowError(context: vscode.ExtensionContext, message: string): Promise<void> {
  await context.workspaceState.update(WORKFLOW_STATE_KEY, markWorkflowCommandFailed(readWorkflowState(context), message));
}

function readWorkflowState(context: vscode.ExtensionContext): WorkflowState {
  return context.workspaceState.get<WorkflowState>(WORKFLOW_STATE_KEY) ?? createInitialWorkflowState(validateSettings(readConfig(context)).ok);
}

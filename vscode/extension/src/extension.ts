import * as path from 'path';
import * as vscode from 'vscode';

import {
  buildAnalyzeFunctionInvocation,
  buildBuildProbeInvocation,
  buildFinalizeDossierInvocation,
  buildGenerateTestDesignInvocation,
  buildPrepareEvidenceInvocation,
  buildReanalyzeFunctionInvocation,
  buildRunTestsInvocation,
  CliInvocation,
  FunctionTarget,
  relativeSourcePath,
} from './cli/commandBuilder';
import { CliResult, runCliInvocation } from './cli/cliRunner';
import { parseCliResult } from './cli/cliResultParser';
import { resolveCliPath } from './config/bundledCli';
import { AdapterSettings, readAdapterSettingsFromObject } from './config/settings';
import { validateSettings } from './config/validation';
import { resolveFunctionNameFromText } from './functionTarget/regexFunctionResolver';
import { ReportPaths, resolveReportPaths } from './reports/reportPathResolver';
import { openMarkdown, openReport } from './reports/reportOpener';
import { WorkflowPanelProvider } from './workflow/workflowPanel';
import {
  completeAwaitingSaveIfMatches,
  createInitialWorkflowState,
  markWorkflowCommandFailed,
  markWorkflowCommandSucceeded,
  WorkflowCommandKind,
  WorkflowState,
  workflowLegacyProjection,
  WORKFLOW_STATE_KEY,
} from './workflow/workflowState';

const LAST_DOSSIER_KEY = 'unitTestRunner.lastFunctionDossierMarkdown';
const LAST_WORKSPACE_KEY = 'unitTestRunner.lastOutputWorkspace';
const LAST_COMMAND_KEY = 'unitTestRunner.lastCliCommand';

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel('Unit Test Runner');
  context.subscriptions.push(output);
  const workflowPanel = new WorkflowPanelProvider(context, () => workflowSettingsReady(context));
  context.subscriptions.push(vscode.window.registerWebviewViewProvider(WorkflowPanelProvider.viewType, workflowPanel));
  context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(async (document) => {
    const state = readWorkflowState(context);
    const result = completeAwaitingSaveIfMatches(state, document.uri.fsPath);
    if (result.matched) {
      await context.workspaceState.update(WORKFLOW_STATE_KEY, result.state);
      workflowPanel.refresh();
      void vscode.window.showInformationMessage('UnitTestRunner: 保存を検知し、次の工程へ進めました。');
    }
  }));

  context.subscriptions.push(
    vscode.commands.registerCommand('unitTestRunner.analyzeCurrentFunction', async () => analyzeActiveFunction(context, output, workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.analyzeSelectedFunction', async () => analyzeActiveFunction(context, output, workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.reanalyzeCurrentFunction', async () => reanalyzeActiveFunction(context, output, workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.finalizeDossier', async () => runWorkspaceCommand(context, output, 'finalize', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.openFunctionDossier', async () => openLastReport(context, 'functionDossierMd')),
    vscode.commands.registerCommand('unitTestRunner.openReviewChecklist', async () => openLastReport(context, 'reviewChecklistMd')),
    vscode.commands.registerCommand('unitTestRunner.openNextActions', async () => openLastReport(context, 'nextActionsMd')),
    vscode.commands.registerCommand('unitTestRunner.openChangeImpactReport', async () => openLastReport(context, 'changeImpactReportMd')),
    vscode.commands.registerCommand('unitTestRunner.openRegressionSelection', async () => openLastReport(context, 'regressionSelectionCsv')),
    vscode.commands.registerCommand('unitTestRunner.generateTestDesign', async () => runWorkspaceCommand(context, output, 'testDesign', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.buildProbeDryRun', async () => runWorkspaceCommand(context, output, 'buildProbeDryRun', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.runBuildProbe', async () => runWorkspaceCommand(context, output, 'buildProbeRun', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.runTests', async () => runWorkspaceCommand(context, output, 'runTests', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.prepareEvidence', async () => runWorkspaceCommand(context, output, 'evidence', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.openOutputWorkspace', async () => openOutputWorkspace(context)),
    vscode.commands.registerCommand('unitTestRunner.copyLastCommand', async () => copyLastCommand(context)),
    vscode.commands.registerCommand('unitTestRunner.openLastFunctionDossier', async () => openLastReport(context, 'functionDossierMd')),
  );
}

export function deactivate(): void {
  // No long-lived process is kept by this thin adapter.
}

async function analyzeActiveFunction(context: vscode.ExtensionContext, output: vscode.OutputChannel, workflowPanel: WorkflowPanelProvider): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    throw new Error('Open a C source file before running UnitTestRunner.');
  }
  const settings = readConfig(context);
  showValidation(settings);
  const functionName = await resolveFunctionName(editor);
  const sourceRelativePath = relativeSourcePath(editor.document.uri.fsPath, settings.sourceRoot);
  const outputWorkspace = path.join(settings.outputRoot, functionName);
  const target: FunctionTarget = {
    sourcePath: editor.document.uri.fsPath,
    sourceRelativePath,
    functionName,
    project: settings.defaultProject,
    configuration: settings.defaultConfiguration,
    outputWorkspace,
  };
  const invocation = buildAnalyzeFunctionInvocation(settings, target);
  const reports = await executeInvocation(context, output, invocation, outputWorkspace, workflowPanel);
  await recordWorkflowSuccess(context, workflowPanel, {
    kind: 'analyze',
    outputWorkspace,
    functionName,
    reports,
  });
  if (settings.autoOpenDossier && reports.functionDossierMd) {
    await openMarkdown(reports.functionDossierMd);
  }
}

async function reanalyzeActiveFunction(context: vscode.ExtensionContext, output: vscode.OutputChannel, workflowPanel: WorkflowPanelProvider): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    throw new Error('Open a C source file before running UnitTestRunner.');
  }
  const settings = readConfig(context);
  showValidation(settings);
  const functionName = await resolveFunctionName(editor);
  const sourceRelativePath = relativeSourcePath(editor.document.uri.fsPath, settings.sourceRoot);
  const outputWorkspace = path.join(settings.outputRoot, functionName);
  const target: FunctionTarget = {
    sourcePath: editor.document.uri.fsPath,
    sourceRelativePath,
    functionName,
    project: settings.defaultProject,
    configuration: settings.defaultConfiguration,
    outputWorkspace,
  };
  const invocation = buildReanalyzeFunctionInvocation(settings, target);
  const reports = await executeInvocation(context, output, invocation, outputWorkspace, workflowPanel);
  await recordWorkflowSuccess(context, workflowPanel, {
    kind: 'reanalyze',
    outputWorkspace,
    functionName,
    reports,
  });
  if (reports.changeImpactReportMd) {
    await openMarkdown(reports.changeImpactReportMd);
  }
}

function readConfig(context: vscode.ExtensionContext): AdapterSettings {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
  const config = vscode.workspace.getConfiguration('unitTestRunner');
  const settings = readAdapterSettingsFromObject(
    {
      cliPath: config.get('cliPath'),
      sourceRoot: config.get('sourceRoot') || config.get('workspaceRoot'),
      dswPath: config.get('dswPath'),
      outputRoot: config.get('outputRoot'),
      defaultConfiguration: config.get('defaultConfiguration'),
      defaultProject: config.get('defaultProject') || config.get('projectName'),
      autoOpenDossier: config.get('autoOpenDossier'),
      finalizeDossierAfterAnalyze: config.get('finalizeDossierAfterAnalyze'),
      useJsonOutput: config.get('useJsonOutput'),
      showOutputChannel: config.get('showOutputChannel'),
      runBuildProbeRequiresConfirmation: config.get('runBuildProbeRequiresConfirmation'),
      runTestsRequiresConfirmation: config.get('runTestsRequiresConfirmation'),
      commandTimeoutSeconds: config.get('commandTimeoutSeconds'),
    },
    workspaceFolder,
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
    throw new Error(`Invalid UnitTestRunner settings: ${validation.warnings.map((warning) => warning.message).join(' ')}`);
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
    prompt: 'Function name to analyze',
    validateInput: (value) => (/^[A-Za-z_]\w*$/.test(value) ? undefined : 'Enter a C function identifier.'),
  });
  if (!prompt) {
    throw new Error('Function analysis cancelled.');
  }
  return prompt;
}

async function runWorkspaceCommand(context: vscode.ExtensionContext, output: vscode.OutputChannel, kind: 'finalize' | 'testDesign' | 'buildProbeDryRun' | 'buildProbeRun' | 'runTests' | 'evidence', workflowPanel: WorkflowPanelProvider): Promise<void> {
  const settings = readConfig(context);
  showValidation(settings);
  const workspace = await lastWorkspace(context);
  let invocation: CliInvocation;
  if (kind === 'finalize') {
    invocation = buildFinalizeDossierInvocation(settings, workspace);
  } else if (kind === 'testDesign') {
    invocation = buildGenerateTestDesignInvocation(settings, path.join(workspace, 'reports', 'function_dossier.json'));
  } else if (kind === 'buildProbeDryRun') {
    invocation = buildBuildProbeInvocation(settings, workspace, false);
  } else if (kind === 'buildProbeRun') {
    invocation = buildBuildProbeInvocation(settings, workspace, true);
  } else if (kind === 'runTests') {
    invocation = buildRunTestsInvocation(settings, workspace, true);
  } else {
    invocation = buildPrepareEvidenceInvocation(settings, workspace);
  }
  const parsedReports = await executeInvocation(context, output, invocation, workspace, workflowPanel);
  await recordWorkflowSuccess(context, workflowPanel, {
    kind: workflowCommandKind(kind),
    outputWorkspace: workspace,
    reports: parsedReports,
  });
}

async function executeInvocation(context: vscode.ExtensionContext, output: vscode.OutputChannel, invocation: CliInvocation, outputWorkspace: string, workflowPanel: WorkflowPanelProvider): Promise<ReportPaths> {
  if (invocation.requiresConfirmation) {
    const selected = await vscode.window.showWarningMessage('This command may execute generated tools or tests. Continue?', { modal: true }, 'Continue');
    if (selected !== 'Continue') {
      throw new Error('UnitTestRunner command cancelled.');
    }
  }
  await context.globalState.update(LAST_COMMAND_KEY, invocation.displayCommand);
  output.show(true);
  output.appendLine(`> ${invocation.displayCommand}`);
  let result: CliResult;
  try {
    result = await runCliInvocation(invocation);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await recordWorkflowError(context, workflowPanel, message);
    throw error;
  }
  output.append(result.stdout);
  output.append(result.stderr);
  if (result.timedOut) {
    await recordWorkflowError(context, workflowPanel, 'unit-test-runner timed out.');
    throw new Error('unit-test-runner timed out.');
  }
  if (result.exitCode !== 0) {
    await recordWorkflowError(context, workflowPanel, `unit-test-runner exited with code ${result.exitCode ?? 'unknown'}.`);
    throw new Error(`unit-test-runner exited with code ${result.exitCode ?? 'unknown'}.`);
  }
  const parsed = parseCliResult(result.stdout, result.stderr, outputWorkspace);
  await context.globalState.update(LAST_WORKSPACE_KEY, parsed.reports.workspace);
  return parsed.reports;
}

function workflowCommandKind(kind: 'finalize' | 'testDesign' | 'buildProbeDryRun' | 'buildProbeRun' | 'runTests' | 'evidence'): WorkflowCommandKind {
  return kind;
}

function workflowSettingsReady(context: vscode.ExtensionContext): boolean {
  return validateSettings(readConfig(context)).ok;
}

function readWorkflowState(context: vscode.ExtensionContext): WorkflowState {
  return context.workspaceState.get<WorkflowState>(WORKFLOW_STATE_KEY) ?? createInitialWorkflowState(workflowSettingsReady(context));
}

async function recordWorkflowSuccess(context: vscode.ExtensionContext, workflowPanel: WorkflowPanelProvider, event: { kind: WorkflowCommandKind; outputWorkspace?: string; functionName?: string; reports?: ReportPaths }): Promise<void> {
  const state = markWorkflowCommandSucceeded(readWorkflowState(context), event);
  await context.workspaceState.update(WORKFLOW_STATE_KEY, state);
  const legacy = workflowLegacyProjection(state);
  if (legacy.lastWorkspace) {
    await context.globalState.update(LAST_WORKSPACE_KEY, legacy.lastWorkspace);
  }
  if (legacy.lastDossier) {
    await context.globalState.update(LAST_DOSSIER_KEY, legacy.lastDossier);
  }
  workflowPanel.refresh();
}

async function recordWorkflowError(context: vscode.ExtensionContext, workflowPanel: WorkflowPanelProvider, message: string): Promise<void> {
  await context.workspaceState.update(WORKFLOW_STATE_KEY, markWorkflowCommandFailed(readWorkflowState(context), message));
  workflowPanel.refresh();
}

async function lastWorkspace(context: vscode.ExtensionContext): Promise<string> {
  const workspace = context.globalState.get<string>(LAST_WORKSPACE_KEY);
  if (workspace) {
    return workspace;
  }
  const selected = await vscode.window.showInputBox({ prompt: 'Output workspace path' });
  if (!selected) {
    throw new Error('Output workspace is required.');
  }
  await context.globalState.update(LAST_WORKSPACE_KEY, selected);
  return selected;
}

async function openLastReport(context: vscode.ExtensionContext, key: keyof ReportPaths): Promise<void> {
  const workspace = context.globalState.get<string>(LAST_WORKSPACE_KEY);
  const remembered = key === 'functionDossierMd' ? context.globalState.get<string>(LAST_DOSSIER_KEY) : undefined;
  const reportPath = remembered || (workspace ? resolveReportPaths(workspace)[key] : undefined);
  if (!reportPath) {
    throw new Error('No output workspace is recorded.');
  }
  await openReport(reportPath);
}

async function openOutputWorkspace(context: vscode.ExtensionContext): Promise<void> {
  const workspace = await lastWorkspace(context);
  await vscode.commands.executeCommand('revealFileInOS', vscode.Uri.file(workspace));
}

async function copyLastCommand(context: vscode.ExtensionContext): Promise<void> {
  const command = context.globalState.get<string>(LAST_COMMAND_KEY);
  if (!command) {
    throw new Error('No UnitTestRunner command is recorded.');
  }
  await vscode.env.clipboard.writeText(command);
}

import * as path from 'path';
import * as vscode from 'vscode';

import {
  buildAnalyzeFunctionInvocation,
  buildBuildProbeInvocation,
  buildFinalizeDossierInvocation,
  buildGenerateTestDraftInvocation,
  buildPrepareEvidenceInvocation,
  buildRunTestsInvocation,
  CliInvocation,
  FunctionTarget,
  relativeSourcePath,
} from './cli/commandBuilder';
import { runCliInvocation } from './cli/cliRunner';
import { parseCliResult } from './cli/cliResultParser';
import { AdapterSettings, readAdapterSettingsFromObject } from './config/settings';
import { validateSettings } from './config/validation';
import { resolveFunctionNameFromText } from './functionTarget/regexFunctionResolver';
import { ReportPaths, resolveReportPaths } from './reports/reportPathResolver';

const LAST_DOSSIER_KEY = 'unitTestRunner.lastFunctionDossierMarkdown';
const LAST_WORKSPACE_KEY = 'unitTestRunner.lastOutputWorkspace';
const LAST_COMMAND_KEY = 'unitTestRunner.lastCliCommand';

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel('Unit Test Runner');
  context.subscriptions.push(output);

  context.subscriptions.push(
    vscode.commands.registerCommand('unitTestRunner.analyzeCurrentFunction', async () => analyzeActiveFunction(context, output)),
    vscode.commands.registerCommand('unitTestRunner.analyzeSelectedFunction', async () => analyzeActiveFunction(context, output)),
    vscode.commands.registerCommand('unitTestRunner.finalizeDossier', async () => runWorkspaceCommand(context, output, 'finalize')),
    vscode.commands.registerCommand('unitTestRunner.openFunctionDossier', async () => openLastReport(context, 'functionDossierMd')),
    vscode.commands.registerCommand('unitTestRunner.openReviewChecklist', async () => openLastReport(context, 'reviewChecklistMd')),
    vscode.commands.registerCommand('unitTestRunner.openNextActions', async () => openLastReport(context, 'nextActionsMd')),
    vscode.commands.registerCommand('unitTestRunner.generateTestDraft', async () => runWorkspaceCommand(context, output, 'draft')),
    vscode.commands.registerCommand('unitTestRunner.buildProbeDryRun', async () => runWorkspaceCommand(context, output, 'buildProbeDryRun')),
    vscode.commands.registerCommand('unitTestRunner.runBuildProbe', async () => runWorkspaceCommand(context, output, 'buildProbeRun')),
    vscode.commands.registerCommand('unitTestRunner.runTests', async () => runWorkspaceCommand(context, output, 'runTests')),
    vscode.commands.registerCommand('unitTestRunner.prepareEvidence', async () => runWorkspaceCommand(context, output, 'evidence')),
    vscode.commands.registerCommand('unitTestRunner.openOutputWorkspace', async () => openOutputWorkspace(context)),
    vscode.commands.registerCommand('unitTestRunner.copyLastCommand', async () => copyLastCommand(context)),
    vscode.commands.registerCommand('unitTestRunner.openLastFunctionDossier', async () => openLastReport(context, 'functionDossierMd')),
  );
}

export function deactivate(): void {
  // No long-lived process is kept by this thin adapter.
}

async function analyzeActiveFunction(context: vscode.ExtensionContext, output: vscode.OutputChannel): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    throw new Error('Open a C source file before running UnitTestRunner.');
  }
  const settings = readConfig();
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
  const reports = await executeInvocation(context, output, invocation, outputWorkspace);
  await context.globalState.update(LAST_WORKSPACE_KEY, outputWorkspace);
  await context.globalState.update(LAST_DOSSIER_KEY, reports.functionDossierMd);
  if (settings.autoOpenDossier && reports.functionDossierMd) {
    await openMarkdown(reports.functionDossierMd);
  }
}

function readConfig(): AdapterSettings {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
  const config = vscode.workspace.getConfiguration('unitTestRunner');
  return readAdapterSettingsFromObject(
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

async function runWorkspaceCommand(context: vscode.ExtensionContext, output: vscode.OutputChannel, kind: 'finalize' | 'draft' | 'buildProbeDryRun' | 'buildProbeRun' | 'runTests' | 'evidence'): Promise<void> {
  const settings = readConfig();
  showValidation(settings);
  const workspace = await lastWorkspace(context);
  const reports = resolveReportPaths(workspace);
  let invocation: CliInvocation;
  if (kind === 'finalize') {
    invocation = buildFinalizeDossierInvocation(settings, workspace);
  } else if (kind === 'draft') {
    invocation = buildGenerateTestDraftInvocation(settings, path.join(workspace, 'reports', 'function_dossier.json'));
  } else if (kind === 'buildProbeDryRun') {
    invocation = buildBuildProbeInvocation(settings, workspace, false);
  } else if (kind === 'buildProbeRun') {
    invocation = buildBuildProbeInvocation(settings, workspace, true);
  } else if (kind === 'runTests') {
    invocation = buildRunTestsInvocation(settings, workspace, true);
  } else {
    invocation = buildPrepareEvidenceInvocation(settings, workspace);
  }
  await executeInvocation(context, output, invocation, workspace);
  if (kind === 'finalize' && reports.functionDossierMd) {
    await context.globalState.update(LAST_DOSSIER_KEY, reports.functionDossierMd);
  }
}

async function executeInvocation(context: vscode.ExtensionContext, output: vscode.OutputChannel, invocation: CliInvocation, outputWorkspace: string): Promise<ReportPaths> {
  if (invocation.requiresConfirmation) {
    const selected = await vscode.window.showWarningMessage('This command may execute generated tools or tests. Continue?', { modal: true }, 'Continue');
    if (selected !== 'Continue') {
      throw new Error('UnitTestRunner command cancelled.');
    }
  }
  await context.globalState.update(LAST_COMMAND_KEY, invocation.displayCommand);
  output.show(true);
  output.appendLine(`> ${invocation.displayCommand}`);
  const result = await runCliInvocation(invocation);
  output.append(result.stdout);
  output.append(result.stderr);
  if (result.timedOut) {
    throw new Error('unit-test-runner timed out.');
  }
  if (result.exitCode !== 0) {
    throw new Error(`unit-test-runner exited with code ${result.exitCode ?? 'unknown'}.`);
  }
  const parsed = parseCliResult(result.stdout, result.stderr, outputWorkspace);
  await context.globalState.update(LAST_WORKSPACE_KEY, parsed.reports.workspace);
  return parsed.reports;
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
  await openMarkdown(reportPath);
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

async function openMarkdown(markdownPath: string): Promise<void> {
  const uri = vscode.Uri.file(markdownPath);
  await vscode.commands.executeCommand('vscode.open', uri);
  await vscode.commands.executeCommand('markdown.showPreview', uri);
}

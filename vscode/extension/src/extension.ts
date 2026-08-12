import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

import {
  buildAnalyzeFunctionInvocation,
  buildBuildProbeInvocation,
  buildFinalizeDossierInvocation,
  buildPrepareHarnessInvocation,
  buildReanalyzeFunctionInvocation,
  buildReviewSetInvocation,
  buildRunTestsInvocation,
  buildSuiteManifestPath,
  buildSuiteRegisterInvocation,
  buildSuiteRunInvocation,
  buildSuiteUpdateInvocation,
  CliInvocation,
  FunctionTarget,
  relativeSourcePath,
} from './cli/commandBuilder';
import { CliResult, runCliInvocation } from './cli/cliRunner';
import { formatCliFailureMessage, ParsedCliResult, parseValidatedCliSuccess } from './cli/cliResultParser';
import { registerUnitTestRunnerCommands, UnitTestRunnerCommandHandlers } from './commands/commandRegistry';
import { DEFAULT_CLI_PATH, resolveCliPath } from './config/bundledCli';
import { AdapterSettings, defaultSourceRootFromWorkspaceFolder, RawSettings, readAdapterSettingsFromObject } from './config/settings';
import { buildSettingsViewModel, SettingsActionKind, SettingsFieldId, SettingsViewModel } from './config/settingsViewModel';
import { preflightInvocation, validateSettings } from './config/validation';
import { resolveFunctionNameFromText } from './functionTarget/regexFunctionResolver';
import { isPathInside, resolveReportedPath } from './platform/pathDialect';
import { ReportPaths, resolveReportPaths } from './reports/reportPathResolver';
import { openMarkdown, openReport } from './reports/reportOpener';
import { readSelectedSuiteEntryIds, SuitePanelProvider } from './suite/suitePanel';
import { readSuiteManifestRevision, suiteRunReportMarkdownPath } from './suite/suiteViewModel';
import { WorkflowPanelProvider } from './workflow/workflowPanel';
import {
  createInitialWorkflowState,
  markWorkflowCommandFailed,
  markWorkflowCommandSucceeded,
  WorkflowCommandKind,
  WorkflowState,
  WORKFLOW_STATE_KEY,
} from './workflow/workflowState';

const LAST_COMMAND_KEY = 'unitTestRunner.lastCliCommand';
const LAST_SUITE_ERROR_KEY = 'unitTestRunner.lastSuiteError';

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel('Unit Test Runner');
  context.subscriptions.push(output);

  let workflowPanel: WorkflowPanelProvider;
  workflowPanel = new WorkflowPanelProvider(
    context,
    () => workflowSettingsReady(context),
    () => readSettingsViewModel(settingsResource()),
    async (fieldId, kind) => {
      await handleSettingsAction(fieldId, kind);
      workflowPanel.refresh();
    },
  );
  let suitePanel: SuitePanelProvider;
  suitePanel = new SuitePanelProvider(
    context,
    () => buildSuiteManifestPath(readConfig(context, settingsResource())),
    () => context.workspaceState.get<string>(LAST_SUITE_ERROR_KEY),
    async (entryId, enabled) => updateSuiteEntry(context, output, suitePanel, entryId, enabled),
  );
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(WorkflowPanelProvider.viewType, workflowPanel),
    vscode.window.registerWebviewViewProvider(SuitePanelProvider.viewType, suitePanel),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration('unitTestRunner')) {
        workflowPanel.refresh();
        suitePanel.refresh();
      }
    }),
  );

  const guarded = (operation: () => Promise<void>) => async (): Promise<void> => {
    try {
      await operation();
    } catch (error) {
      void vscode.window.showErrorMessage(`UnitTestRunner: ${errorMessage(error)}`);
    }
  };
  const handlers: UnitTestRunnerCommandHandlers = {
    'unitTestRunner.analyzeCurrentFunction': guarded(() => analyzeActiveFunction(context, output, workflowPanel)),
    'unitTestRunner.analyzeSelectedFunction': guarded(() => analyzeActiveFunction(context, output, workflowPanel)),
    'unitTestRunner.reanalyzeCurrentFunction': guarded(() => reanalyzeActiveFunction(context, output, workflowPanel)),
    'unitTestRunner.finalizeDossier': guarded(() => runWorkspaceCommand(context, output, workflowPanel, 'finalize')),
    'unitTestRunner.openFunctionDossier': guarded(() => openCurrentReport(context, 'functionDossierMd')),
    'unitTestRunner.openReviewChecklist': guarded(() => openCurrentReport(context, 'reviewChecklistMd')),
    'unitTestRunner.openTestInputEditor': guarded(() => reviewCurrentTestSpec(context, output, workflowPanel)),
    'unitTestRunner.prepareHarness': guarded(() => runWorkspaceCommand(context, output, workflowPanel, 'harness')),
    'unitTestRunner.buildProbeDryRun': guarded(() => runWorkspaceCommand(context, output, workflowPanel, 'buildProbeDryRun')),
    'unitTestRunner.runBuildProbe': guarded(() => runWorkspaceCommand(context, output, workflowPanel, 'buildProbeRun')),
    'unitTestRunner.runTests': guarded(() => runWorkspaceCommand(context, output, workflowPanel, 'runTests')),
    'unitTestRunner.registerCurrentFunctionInSuite': guarded(() => registerCurrentFunction(context, output, workflowPanel, suitePanel)),
    'unitTestRunner.runSelectedSuiteTests': guarded(() => runSelectedSuiteTests(context, output, suitePanel)),
    'unitTestRunner.openSuiteRunReport': guarded(() => openSuiteRunReport(context)),
    'unitTestRunner.openOutputWorkspace': guarded(() => openOutputWorkspace(context)),
    'unitTestRunner.copyLastCommand': guarded(() => copyLastCommand(context)),
  };
  context.subscriptions.push(...registerUnitTestRunnerCommands(context, {
    registry: { registerCommand: (command, handler) => vscode.commands.registerCommand(command, (...args: unknown[]) => handler(...args)) },
    handlers,
  }));
}

export function deactivate(): void {
  // The adapter owns no long-lived child process.
}

async function analyzeActiveFunction(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  panel: WorkflowPanelProvider,
): Promise<void> {
  const active = await activeFunctionContext(context);
  const parsed = await executeInvocation(context, output, buildAnalyzeFunctionInvocation(active.settings, active.target), active.target.outputWorkspace, panel);
  await recordWorkflowSuccess(context, panel, {
    kind: 'analyze',
    workspaceFolderUri: active.folder.uri.toString(),
    outputWorkspace: active.target.outputWorkspace,
    sourcePath: active.target.sourcePath,
    functionName: active.target.functionName,
    reports: parsed.reports,
  });
}

async function reanalyzeActiveFunction(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  panel: WorkflowPanelProvider,
): Promise<void> {
  const active = await currentFunctionContext(context);
  const parsed = await executeInvocation(context, output, buildReanalyzeFunctionInvocation(active.settings, active.target), active.target.outputWorkspace, panel);
  await recordWorkflowSuccess(context, panel, {
    kind: 'reanalyze',
    workspaceFolderUri: active.folder.uri.toString(),
    outputWorkspace: active.target.outputWorkspace,
    sourcePath: active.target.sourcePath,
    functionName: active.target.functionName,
    reports: parsed.reports,
  });
  if (parsed.reports.reanalysisReportMd && fs.existsSync(parsed.reports.reanalysisReportMd)) {
    await openMarkdown(parsed.reports.reanalysisReportMd);
  }
}

async function runWorkspaceCommand(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  panel: WorkflowPanelProvider,
  kind: 'finalize' | 'harness' | 'buildProbeDryRun' | 'buildProbeRun' | 'runTests',
): Promise<void> {
  const active = await currentFunctionContext(context);
  const workspace = active.target.outputWorkspace;
  let invocation: CliInvocation;
  let workflowKind: WorkflowCommandKind;
  if (kind === 'finalize') {
    invocation = buildFinalizeDossierInvocation(active.settings, workspace);
    workflowKind = 'finalize';
  } else if (kind === 'harness') {
    invocation = buildPrepareHarnessInvocation(active.settings, active.target);
    workflowKind = 'harness';
  } else if (kind === 'buildProbeDryRun') {
    invocation = buildBuildProbeInvocation(active.settings, workspace, false);
    workflowKind = 'buildProbeDryRun';
  } else if (kind === 'buildProbeRun') {
    invocation = buildBuildProbeInvocation(active.settings, workspace, true);
    workflowKind = 'buildProbeRun';
  } else {
    invocation = buildRunTestsInvocation(active.settings, workspace, true, { all: true });
    workflowKind = 'runTests';
  }
  const parsed = await executeInvocation(context, output, invocation, workspace, panel);
  await recordWorkflowSuccess(context, panel, {
    kind: workflowKind,
    workspaceFolderUri: active.folder.uri.toString(),
    outputWorkspace: workspace,
    sourcePath: active.target.sourcePath,
    functionName: active.target.functionName,
    reports: parsed.reports,
  });
  if (kind === 'finalize' && active.settings.autoOpenDossier) {
    const dossier = parsed.reports.functionDossierMd ?? resolveReportPaths(workspace).functionDossierMd;
    if (dossier && fs.existsSync(dossier)) await openMarkdown(dossier);
  }
}

async function reviewCurrentTestSpec(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  panel: WorkflowPanelProvider,
): Promise<void> {
  const active = await currentFunctionContext(context);
  const reports = resolveReportPaths(active.target.outputWorkspace);
  const specPath = reports.testSpecJson!;
  const spec = readPublicArtifact(specPath, 'test_spec');
  const specSha256 = sha256File(specPath);
  const reviewView = reports.testSpecMd && fs.existsSync(reports.testSpecMd) ? reports.testSpecMd : specPath;
  await openReport(reviewView);
  const decision = await vscode.window.showQuickPick(
    [
      { label: '承認する', value: 'approved' as const },
      { label: '変更を依頼する', value: 'changes_requested' as const },
    ],
    { placeHolder: 'TestSpecのレビュー結果を選択してください。' },
  );
  if (!decision) return;
  const reviewer = await vscode.window.showInputBox({
    prompt: 'レビュアー名を入力してください。',
    value: process.env.USERNAME || process.env.USER || '',
    validateInput: (value) => value.trim() ? undefined : 'レビュアー名は必須です。',
  });
  if (!reviewer) return;
  const comment = await vscode.window.showInputBox({ prompt: 'レビューコメント（任意）を入力してください。', value: '' });
  if (comment === undefined) return;
  const parsed = await executeInvocation(
    context,
    output,
    buildReviewSetInvocation(active.settings, active.target.outputWorkspace, String(spec.artifact_kind), specSha256, decision.value, reviewer.trim(), comment),
    active.target.outputWorkspace,
    panel,
  );
  await recordWorkflowSuccess(context, panel, {
    kind: 'review',
    reviewDecision: decision.value,
    workspaceFolderUri: active.folder.uri.toString(),
    outputWorkspace: active.target.outputWorkspace,
    sourcePath: active.target.sourcePath,
    functionName: active.target.functionName,
    reports: parsed.reports,
  });
}

async function registerCurrentFunction(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  workflowPanel: WorkflowPanelProvider,
  suitePanel: SuitePanelProvider,
): Promise<void> {
  const active = await currentFunctionContext(context);
  const suitePath = buildSuiteManifestPath(active.settings);
  const tagsText = await vscode.window.showInputBox({ prompt: 'タグをカンマ区切りで入力してください（任意）。', value: '' });
  if (tagsText === undefined) return;
  const tags = tagsText.split(',').map((item) => item.trim()).filter(Boolean);
  const revision = readSuiteManifestRevision(suitePath);
  await executeSuiteInvocation(
    context,
    output,
    buildSuiteRegisterInvocation(active.settings, active.target, tags, revision),
    path.dirname(suitePath),
    suitePanel,
  );
  workflowPanel.refresh();
  void vscode.window.showInformationMessage('UnitTestRunner: 現在の関数をスイートに登録しました。');
}

async function updateSuiteEntry(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  suitePanel: SuitePanelProvider,
  entryId: string,
  enabled: boolean,
): Promise<void> {
  const resource = activeWorkspaceResource();
  const settings = readConfig(context, resource);
  showPreflight(settings);
  const suitePath = buildSuiteManifestPath(settings);
  await executeSuiteInvocation(
    context,
    output,
    buildSuiteUpdateInvocation(settings, entryId, enabled, readSuiteManifestRevision(suitePath)),
    path.dirname(suitePath),
    suitePanel,
  );
}

async function runSelectedSuiteTests(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  suitePanel: SuitePanelProvider,
): Promise<void> {
  const resource = activeWorkspaceResource();
  const settings = readConfig(context, resource);
  showPreflight(settings);
  const entryIds = readSelectedSuiteEntryIds(context);
  if (entryIds.length === 0) throw new Error('実行するスイート項目を明示選択してください。');
  const suitePath = buildSuiteManifestPath(settings);
  await executeSuiteInvocation(
    context,
    output,
    buildSuiteRunInvocation(settings, { entryIds, run: true }),
    path.dirname(suitePath),
    suitePanel,
  );
}

async function executeInvocation(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  invocation: CliInvocation,
  artifactRoot: string,
  panel: WorkflowPanelProvider,
): Promise<ParsedCliResult> {
  await confirmExecution(invocation);
  await context.globalState.update(LAST_COMMAND_KEY, invocation.displayCommand);
  output.show(true);
  output.appendLine(`> ${invocation.displayCommand}`);
  let result: CliResult;
  try {
    result = await runCliInvocation(invocation);
  } catch (error) {
    await recordWorkflowError(context, panel, errorMessage(error));
    throw error;
  }
  output.append(result.stdout);
  output.append(result.stderr);
  if (result.timedOut) {
    const message = 'UnitTestRunner CLIの処理がタイムアウトし、process treeを終了しました。';
    await recordWorkflowError(context, panel, message);
    throw new Error(message);
  }
  if (result.exitCode !== 0) {
    const message = formatCliFailureMessage(result.stdout, result.stderr, result.exitCode);
    await recordWorkflowError(context, panel, message);
    throw new Error(message);
  }
  const allowPlanned = invocation.args.includes('--dry-run') || invocation.args.includes('--plan');
  const parsed = parseValidatedCliSuccess(result.stdout, result.stderr, artifactRoot, allowPlanned);
  verifyProducedArtifacts(parsed, artifactRoot);
  return parsed;
}

async function executeSuiteInvocation(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  invocation: CliInvocation,
  artifactRoot: string,
  panel: SuitePanelProvider,
): Promise<ParsedCliResult> {
  try {
    const parsed = await executeInvocationWithoutWorkflow(context, output, invocation, artifactRoot);
    await context.workspaceState.update(LAST_SUITE_ERROR_KEY, undefined);
    panel.refresh();
    return parsed;
  } catch (error) {
    await context.workspaceState.update(LAST_SUITE_ERROR_KEY, errorMessage(error));
    panel.refresh();
    throw error;
  }
}

async function executeInvocationWithoutWorkflow(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  invocation: CliInvocation,
  artifactRoot: string,
): Promise<ParsedCliResult> {
  await confirmExecution(invocation);
  await context.globalState.update(LAST_COMMAND_KEY, invocation.displayCommand);
  output.show(true);
  output.appendLine(`> ${invocation.displayCommand}`);
  const result = await runCliInvocation(invocation);
  output.append(result.stdout);
  output.append(result.stderr);
  if (result.timedOut) throw new Error('UnitTestRunner CLIの処理がタイムアウトし、process treeを終了しました。');
  if (result.exitCode !== 0) throw new Error(formatCliFailureMessage(result.stdout, result.stderr, result.exitCode));
  const parsed = parseValidatedCliSuccess(result.stdout, result.stderr, artifactRoot, invocation.args.includes('--plan'));
  verifyProducedArtifacts(parsed, artifactRoot);
  return parsed;
}

async function confirmExecution(invocation: CliInvocation): Promise<void> {
  if (!invocation.requiresConfirmation) return;
  const build = invocation.args.includes('build-probe');
  const action = build ? 'ビルドを実行' : 'テストを実行';
  const selected = await vscode.window.showWarningMessage(
    build ? '生成したハーネスをビルドします。実行しますか？' : '承認済みTestSpecのテストを実行します。実行しますか？',
    { modal: true },
    action,
  );
  if (selected !== action) throw new Error('ユーザーが実行をキャンセルしました。');
}

function verifyProducedArtifacts(parsed: ParsedCliResult, root: string): void {
  for (const artifact of parsed.artifacts) {
    const resolved = resolveReportedPath(artifact.path, root);
    if (!isPathInside(resolved, root) || !fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
      throw new Error(`CLIが報告したartifactを安全に再読できません: ${artifact.path}`);
    }
    if (sha256File(resolved) !== artifact.sha256) {
      throw new Error(`CLI artifact SHA-256が再読結果と一致しません: ${artifact.path}`);
    }
  }
}

async function activeFunctionContext(context: vscode.ExtensionContext): Promise<{
  settings: AdapterSettings; target: FunctionTarget; resource: vscode.Uri; folder: vscode.WorkspaceFolder;
}> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) throw new Error('workspace内のC sourceを開いてください。');
  const resource = activeWorkspaceResource();
  const folder = vscode.workspace.getWorkspaceFolder(resource)!;
  const settings = readConfig(context, resource);
  showPreflight(settings, editor.document.uri.fsPath);
  const functionName = await resolveFunctionName(editor);
  const relative = relativeSourcePath(editor.document.uri.fsPath, settings.sourceRoot);
  const suffix = crypto.createHash('sha256').update(`${relative}\0${functionName}`, 'utf8').digest('hex').slice(0, 12);
  const slug = functionName.replace(/[^A-Za-z0-9_]+/g, '_') || 'function';
  return {
    settings,
    resource,
    folder,
    target: {
      sourcePath: editor.document.uri.fsPath,
      sourceRelativePath: relative,
      functionName,
      project: settings.defaultProject,
      configuration: settings.defaultConfiguration,
      outputWorkspace: path.join(settings.outputRoot, `fn_${slug}_${suffix}`),
    },
  };
}

async function currentFunctionContext(context: vscode.ExtensionContext): Promise<{
  settings: AdapterSettings; target: FunctionTarget; resource: vscode.Uri; folder: vscode.WorkspaceFolder;
}> {
  const state = readWorkflowState(context);
  const editor = vscode.window.activeTextEditor;
  if (!editor || !state.outputWorkspace || !state.functionName || !state.sourcePath) {
    throw new Error('先にactive documentの関数を解析してください。');
  }
  const resource = activeWorkspaceResource();
  const folder = vscode.workspace.getWorkspaceFolder(resource)!;
  if (state.workspaceFolderUri && state.workspaceFolderUri !== folder.uri.toString()) {
    throw new Error('active documentのworkspace folderが現在のworkflowと一致しません。');
  }
  if (path.resolve(state.sourcePath) !== path.resolve(editor.document.uri.fsPath)) {
    throw new Error('active documentが現在のworkflow対象sourceと一致しません。');
  }
  const settings = readConfig(context, resource);
  showPreflight(settings, editor.document.uri.fsPath);
  if (!isPathInside(state.outputWorkspace, settings.outputRoot)) {
    throw new Error('現在のoutput workspaceがresource-scoped outputRoot外です。');
  }
  return {
    settings,
    resource,
    folder,
    target: {
      sourcePath: state.sourcePath,
      sourceRelativePath: relativeSourcePath(state.sourcePath, settings.sourceRoot),
      functionName: state.functionName,
      project: settings.defaultProject,
      configuration: settings.defaultConfiguration,
      outputWorkspace: state.outputWorkspace,
    },
  };
}

function readRawConfig(resource?: vscode.Uri): RawSettings {
  const config = vscode.workspace.getConfiguration('unitTestRunner', resource);
  return {
    cliPath: config.get('cliPath'),
    sourceRoot: config.get('sourceRoot'),
    dswPath: config.get('dswPath'),
    outputRoot: config.get('outputRoot'),
    suiteManifestPath: config.get('suiteManifestPath'),
    defaultConfiguration: config.get('defaultConfiguration'),
    defaultProject: config.get('defaultProject'),
    vcvarsPath: config.get('vcvarsPath'),
    autoOpenDossier: config.get('autoOpenDossier'),
    runBuildProbeRequiresConfirmation: config.get('runBuildProbeRequiresConfirmation'),
    runTestsRequiresConfirmation: config.get('runTestsRequiresConfirmation'),
    commandTimeoutSeconds: config.get('commandTimeoutSeconds'),
  };
}

function settingsResource(): vscode.Uri | undefined {
  const active = vscode.window.activeTextEditor?.document.uri;
  if (active && vscode.workspace.getWorkspaceFolder(active)) return active;
  return vscode.workspace.workspaceFolders?.length === 1 ? vscode.workspace.workspaceFolders[0].uri : undefined;
}

function activeWorkspaceResource(): vscode.Uri {
  const resource = vscode.window.activeTextEditor?.document.uri;
  if (!resource || !vscode.workspace.getWorkspaceFolder(resource)) {
    throw new Error('workspace folder内のactive documentを選択してください。');
  }
  return resource;
}

function defaultSourceRoot(resource?: vscode.Uri): string {
  return defaultSourceRootFromWorkspaceFolder(resource ? vscode.workspace.getWorkspaceFolder(resource) : undefined);
}

function readConfig(context: vscode.ExtensionContext, resource?: vscode.Uri): AdapterSettings {
  const settings = readAdapterSettingsFromObject(readRawConfig(resource), defaultSourceRoot(resource));
  return { ...settings, cliPath: resolveCliPath(settings.cliPath, context.extensionPath) };
}

function readSettingsViewModel(resource?: vscode.Uri): SettingsViewModel {
  return buildSettingsViewModel(readRawConfig(resource), defaultSourceRoot(resource));
}

function workflowSettingsReady(context: vscode.ExtensionContext): boolean {
  return validateSettings(readConfig(context, settingsResource())).ok;
}

function showPreflight(settings: AdapterSettings, sourcePath?: string): void {
  const result = preflightInvocation(settings, sourcePath);
  if (!result.ok) throw new Error(`実行前確認に失敗しました。${result.warnings.map((item) => ` ${item.message}`).join('')}`);
}

async function resolveFunctionName(editor: vscode.TextEditor): Promise<string> {
  const inferred = resolveFunctionNameFromText({
    selectedText: editor.document.getText(editor.selection),
    documentText: editor.document.getText(),
    cursorOffset: editor.document.offsetAt(editor.selection.active),
  });
  if (inferred) return inferred;
  const input = await vscode.window.showInputBox({
    prompt: '解析する関数名を入力してください。',
    validateInput: (value) => /^[A-Za-z_]\w*$/.test(value) ? undefined : 'C identifierを入力してください。',
  });
  if (!input) throw new Error('関数名が入力されませんでした。');
  return input;
}

async function handleSettingsAction(fieldId: SettingsFieldId, kind: SettingsActionKind): Promise<void> {
  const resource = settingsResource();
  if (!resource) throw new Error('設定対象のworkspace folderを選択してください。');
  const field = readSettingsViewModel(resource).fields.find((item) => item.id === fieldId);
  if (!field) throw new Error(`不明な設定項目です: ${fieldId}`);
  if (kind === 'reset') {
    const value = fieldId === 'cliPath' ? DEFAULT_CLI_PATH : fieldId === 'defaultConfiguration' ? '' : undefined;
    await updateSetting(resource, fieldId, value);
    return;
  }
  if (kind === 'pickFolder' || kind === 'pickFile') {
    const selected = await vscode.window.showOpenDialog({
      canSelectFiles: kind === 'pickFile',
      canSelectFolders: kind === 'pickFolder',
      canSelectMany: false,
      openLabel: '選択',
      title: `${field.label}を選択`,
    });
    if (selected?.[0]) await updateSetting(resource, fieldId, selected[0].fsPath);
    return;
  }
  const value = await vscode.window.showInputBox({ prompt: field.description, value: field.configuredValue || field.effectiveValue });
  if (value !== undefined) await updateSetting(resource, fieldId, value.trim());
}

async function updateSetting(resource: vscode.Uri, fieldId: SettingsFieldId, value: string | undefined): Promise<void> {
  await vscode.workspace.getConfiguration('unitTestRunner', resource).update(fieldId, value, vscode.ConfigurationTarget.WorkspaceFolder);
}

function readWorkflowState(context: vscode.ExtensionContext): WorkflowState {
  return context.workspaceState.get<WorkflowState>(WORKFLOW_STATE_KEY) ?? createInitialWorkflowState(workflowSettingsReady(context));
}

async function recordWorkflowSuccess(
  context: vscode.ExtensionContext,
  panel: WorkflowPanelProvider,
  event: Parameters<typeof markWorkflowCommandSucceeded>[1],
): Promise<void> {
  await context.workspaceState.update(WORKFLOW_STATE_KEY, markWorkflowCommandSucceeded(readWorkflowState(context), event));
  panel.refresh();
}

async function recordWorkflowError(context: vscode.ExtensionContext, panel: WorkflowPanelProvider, message: string): Promise<void> {
  await context.workspaceState.update(WORKFLOW_STATE_KEY, markWorkflowCommandFailed(readWorkflowState(context), message));
  panel.refresh();
}

async function openCurrentReport(context: vscode.ExtensionContext, key: keyof ReportPaths): Promise<void> {
  const state = readWorkflowState(context);
  if (!state.outputWorkspace) throw new Error('出力workspaceがありません。');
  const value = state.reports?.[key] ?? resolveReportPaths(state.outputWorkspace)[key];
  if (typeof value !== 'string' || !fs.existsSync(value)) throw new Error('対象レポートがまだ生成されていません。');
  await openReport(value);
}

async function openSuiteRunReport(context: vscode.ExtensionContext): Promise<void> {
  const settings = readConfig(context, settingsResource());
  const report = suiteRunReportMarkdownPath(buildSuiteManifestPath(settings));
  if (!fs.existsSync(report)) throw new Error('スイート実行レポートがまだありません。');
  await openReport(report);
}

async function openOutputWorkspace(context: vscode.ExtensionContext): Promise<void> {
  const workspace = readWorkflowState(context).outputWorkspace;
  if (!workspace) throw new Error('出力workspaceがありません。');
  await vscode.commands.executeCommand('revealFileInOS', vscode.Uri.file(workspace));
}

async function copyLastCommand(context: vscode.ExtensionContext): Promise<void> {
  const command = context.globalState.get<string>(LAST_COMMAND_KEY);
  if (!command) throw new Error('実行済みCLIコマンドがありません。');
  await vscode.env.clipboard.writeText(command);
}

function readPublicArtifact(filePath: string, kind: string): Record<string, unknown> {
  if (!fs.existsSync(filePath)) throw new Error(`${kind}が見つかりません。`);
  const value = JSON.parse(fs.readFileSync(filePath, 'utf8')) as unknown;
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${kind}がJSON objectではありません。`);
  const payload = value as Record<string, unknown>;
  if (payload.schema_version !== '1.0.0' || payload.artifact_kind !== kind) {
    throw new Error(`${kind}はv0.1 workspaceとして再生成してください。`);
  }
  return payload;
}

function sha256File(filePath: string): string {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

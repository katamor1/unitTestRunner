import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

import {
  buildAnalyzeFunctionInvocation,
  buildBuildProbeInvocation,
  buildFinalizeDossierInvocation,
  buildGenerateHarnessSkeletonInvocation,
  buildGenerateTestDesignInvocation,
  buildPrepareEvidenceInvocation,
  buildReanalyzeFunctionInvocation,
  buildRunTestsInvocation,
  buildSuiteManifestPath,
  buildSuiteRegisterInvocation,
  buildSuiteRunInvocation,
  CliInvocation,
  FunctionTarget,
  relativeSourcePath,
} from './cli/commandBuilder';
import { CliResult, runCliInvocation } from './cli/cliRunner';
import { formatCliFailureMessage, parseCliResult } from './cli/cliResultParser';
import { DEFAULT_CLI_PATH, resolveCliPath } from './config/bundledCli';
import { AdapterSettings, defaultSourceRootFromWorkspaceFolders, RawSettings, readAdapterSettingsFromObject } from './config/settings';
import { buildSettingsViewModel, SettingsActionKind, SettingsFieldId, SettingsViewModel } from './config/settingsViewModel';
import { validateSettings } from './config/validation';
import { resolveFunctionNameFromText } from './functionTarget/regexFunctionResolver';
import { ReportPaths, resolveReportPaths } from './reports/reportPathResolver';
import { openMarkdown, openReport } from './reports/reportOpener';
import { readSelectedSuiteEntryIds, SuitePanelProvider } from './suite/suitePanel';
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
  let workflowPanel: WorkflowPanelProvider;
  workflowPanel = new WorkflowPanelProvider(
    context,
    () => workflowSettingsReady(context),
    () => readSettingsViewModel(),
    async (fieldId, kind) => {
      await handleSettingsAction(fieldId, kind);
      workflowPanel.refresh();
    },
  );
  let suitePanel: SuitePanelProvider;
  suitePanel = new SuitePanelProvider(context, () => buildSuiteManifestPath(readConfig(context)));
  context.subscriptions.push(vscode.window.registerWebviewViewProvider(WorkflowPanelProvider.viewType, workflowPanel));
  context.subscriptions.push(vscode.window.registerWebviewViewProvider(SuitePanelProvider.viewType, suitePanel));
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((event) => {
    if (event.affectsConfiguration('unitTestRunner')) {
      workflowPanel.refresh();
      suitePanel.refresh();
    }
  }));
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
    vscode.commands.registerCommand('unitTestRunner.generateHarnessSkeleton', async () => runWorkspaceCommand(context, output, 'harness', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.buildProbeDryRun', async () => runWorkspaceCommand(context, output, 'buildProbeDryRun', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.runBuildProbe', async () => runWorkspaceCommand(context, output, 'buildProbeRun', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.runTests', async () => runWorkspaceCommand(context, output, 'runTests', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.prepareEvidence', async () => runWorkspaceCommand(context, output, 'evidence', workflowPanel)),
    vscode.commands.registerCommand('unitTestRunner.registerCurrentFunctionInSuite', async () => registerActiveFunctionInSuite(context, output, workflowPanel, suitePanel)),
    vscode.commands.registerCommand('unitTestRunner.openSuite', async () => openSuiteManifest(context)),
    vscode.commands.registerCommand('unitTestRunner.runSelectedSuiteTests', async () => runSuiteCommand(context, output, { selected: true, run: true }, suitePanel)),
    vscode.commands.registerCommand('unitTestRunner.runSuiteByTag', async () => runSuiteByTag(context, output, suitePanel)),
    vscode.commands.registerCommand('unitTestRunner.runAllSuiteTestsRequireGreen', async () => runSuiteCommand(context, output, { all: true, run: true, requireGreen: true }, suitePanel)),
    vscode.commands.registerCommand('unitTestRunner.openSuiteRunReport', async () => openSuiteRunReport(context)),
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
    throw new Error('UnitTestRunnerを実行する前にCソースファイルを開いてください。');
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
    throw new Error('UnitTestRunnerを実行する前にCソースファイルを開いてください。');
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

async function registerActiveFunctionInSuite(context: vscode.ExtensionContext, output: vscode.OutputChannel, workflowPanel: WorkflowPanelProvider, suitePanel: SuitePanelProvider): Promise<void> {
  const target = await activeFunctionTarget(context);
  const settings = readConfig(context);
  const invocation = buildSuiteRegisterInvocation(settings, target, ['selected', 'regression']);
  await executeSuiteInvocation(context, output, invocation, suitePanel);
  await context.globalState.update(LAST_WORKSPACE_KEY, target.outputWorkspace);
  workflowPanel.refresh();
  void vscode.window.showInformationMessage('UnitTestRunner: 現在関数をスイートに登録しました。');
}

async function activeFunctionTarget(context: vscode.ExtensionContext): Promise<FunctionTarget> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    throw new Error('UnitTestRunnerを実行する前にCソースファイルを開いてください。');
  }
  const settings = readConfig(context);
  showValidation(settings);
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

interface SuiteCommandOptions {
  selected?: boolean;
  tag?: string;
  all?: boolean;
  run: boolean;
  requireGreen?: boolean;
}

async function runSuiteByTag(context: vscode.ExtensionContext, output: vscode.OutputChannel, suitePanel: SuitePanelProvider): Promise<void> {
  const tag = await vscode.window.showInputBox({
    prompt: '実行するスイートタグを入力してください。',
    value: 'selected',
  });
  if (!tag) {
    throw new Error('スイートタグの指定が必要です。');
  }
  await runSuiteCommand(context, output, { tag: tag.trim(), run: true }, suitePanel);
}

async function runSuiteCommand(context: vscode.ExtensionContext, output: vscode.OutputChannel, options: SuiteCommandOptions, suitePanel: SuitePanelProvider): Promise<void> {
  const settings = readConfig(context);
  showValidation(settings);
  const entryIds = options.selected ? readSelectedSuiteEntryIds(context) : undefined;
  if (options.selected && (!entryIds || entryIds.length === 0)) {
    throw new Error('スイートで実行する関数を選択してください。');
  }
  const invocation = buildSuiteRunInvocation(settings, {
    entryIds,
    tag: options.tag,
    all: options.all,
    run: options.run,
    requireGreen: options.requireGreen,
  });
  await executeSuiteInvocation(context, output, invocation, suitePanel);
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
  };
}

function defaultSourceRoot(): string {
  return defaultSourceRootFromWorkspaceFolders(vscode.workspace.workspaceFolders);
}

function readSettingsViewModel(): SettingsViewModel {
  return buildSettingsViewModel(readRawConfig(), defaultSourceRoot());
}

function readConfig(context: vscode.ExtensionContext): AdapterSettings {
  const settings = readAdapterSettingsFromObject(
    readRawConfig(),
    defaultSourceRoot(),
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

async function handleSettingsAction(fieldId: SettingsFieldId, kind: SettingsActionKind): Promise<void> {
  ensureWorkspaceSettingsTarget();
  const model = readSettingsViewModel();
  const field = model.fields.find((item) => item.id === fieldId);
  if (!field) {
    throw new Error(`Unknown settings field: ${fieldId}`);
  }
  if (kind === 'reset') {
    await resetSetting(fieldId);
    return;
  }
  if (kind === 'pickFolder') {
    const selected = await vscode.window.showOpenDialog({
      canSelectFiles: false,
      canSelectFolders: true,
      canSelectMany: false,
      defaultUri: defaultUriForField(field.effectiveValue, false),
      openLabel: '選択',
      title: `${field.label}を選択`,
    });
    if (!selected?.[0]) {
      return;
    }
    await updateSetting(fieldId, selected[0].fsPath);
    return;
  }
  if (kind === 'pickFile') {
    const selected = await vscode.window.showOpenDialog({
      canSelectFiles: true,
      canSelectFolders: false,
      canSelectMany: false,
      defaultUri: defaultUriForField(field.configuredValue || field.effectiveValue, true),
      filters: filePickerFilters(fieldId),
      openLabel: '選択',
      title: `${field.label}を選択`,
    });
    if (!selected?.[0]) {
      return;
    }
    await updateSetting(fieldId, selected[0].fsPath);
    return;
  }
  if (kind === 'inputText') {
    const selected = await vscode.window.showInputBox({
      prompt: inputPrompt(fieldId),
      value: field.configuredValue || field.effectiveValue,
    });
    if (selected === undefined) {
      return;
    }
    await updateSetting(fieldId, selected.trim());
  }
}

function ensureWorkspaceSettingsTarget(): void {
  if (!vscode.workspace.workspaceFolders?.length && !vscode.workspace.workspaceFile) {
    throw new Error('UnitTestRunnerの設定を保存するには、フォルダまたはworkspaceを開いてください。');
  }
}

async function updateSetting(fieldId: SettingsFieldId, value: string): Promise<void> {
  const settingKey = settingKeyForField(fieldId);
  await vscode.workspace.getConfiguration('unitTestRunner').update(settingKey, value, vscode.ConfigurationTarget.Workspace);
}

async function resetSetting(fieldId: SettingsFieldId): Promise<void> {
  const config = vscode.workspace.getConfiguration('unitTestRunner');
  if (fieldId === 'sourceRoot') {
    await config.update('sourceRoot', '', vscode.ConfigurationTarget.Workspace);
    await config.update('workspaceRoot', '', vscode.ConfigurationTarget.Workspace);
    return;
  }
  if (fieldId === 'defaultConfiguration') {
    await config.update('defaultConfiguration', '', vscode.ConfigurationTarget.Workspace);
    return;
  }
  if (fieldId === 'defaultProject') {
    await config.update('defaultProject', '', vscode.ConfigurationTarget.Workspace);
    await config.update('projectName', '', vscode.ConfigurationTarget.Workspace);
    return;
  }
  if (fieldId === 'cliPath') {
    await config.update('cliPath', DEFAULT_CLI_PATH, vscode.ConfigurationTarget.Workspace);
    return;
  }
  if (fieldId === 'suiteManifestPath') {
    await config.update('suiteManifestPath', '', vscode.ConfigurationTarget.Workspace);
    return;
  }
  await config.update(settingKeyForField(fieldId), undefined, vscode.ConfigurationTarget.Workspace);
  for (const alias of legacySettingKeysForField(fieldId)) {
    await config.update(alias, undefined, vscode.ConfigurationTarget.Workspace);
  }
}

function settingKeyForField(fieldId: SettingsFieldId): string {
  const keys: Record<SettingsFieldId, string> = {
    sourceRoot: 'sourceRoot',
    dswPath: 'dswPath',
    outputRoot: 'outputRoot',
    suiteManifestPath: 'suiteManifestPath',
    defaultConfiguration: 'defaultConfiguration',
    defaultProject: 'defaultProject',
    vcvarsPath: 'vcvarsPath',
    cliPath: 'cliPath',
  };
  return keys[fieldId];
}

function legacySettingKeysForField(fieldId: SettingsFieldId): string[] {
  if (fieldId === 'sourceRoot') {
    return ['workspaceRoot'];
  }
  if (fieldId === 'defaultProject') {
    return ['projectName'];
  }
  return [];
}

function defaultUriForField(value: string, fileSelection: boolean): vscode.Uri | undefined {
  if (!value || !path.isAbsolute(value)) {
    return undefined;
  }
  return vscode.Uri.file(fileSelection ? path.dirname(value) : value);
}

function filePickerFilters(fieldId: SettingsFieldId): Record<string, string[]> {
  if (fieldId === 'dswPath') {
    return { 'Visual C++ workspace': ['dsw'], 'すべてのファイル': ['*'] };
  }
  if (fieldId === 'cliPath') {
    return { '実行ファイル': ['exe'], 'すべてのファイル': ['*'] };
  }
  if (fieldId === 'suiteManifestPath') {
    return { 'JSON': ['json'], 'すべてのファイル': ['*'] };
  }
  if (fieldId === 'vcvarsPath') {
    return { 'Batch files': ['bat', 'cmd'], 'すべてのファイル': ['*'] };
  }
  return { 'すべてのファイル': ['*'] };
}

function inputPrompt(fieldId: SettingsFieldId): string {
  if (fieldId === 'sourceRoot') {
    return 'プロジェクトルートのフォルダパスを入力してください。空にするとVS Codeで開いたTOPフォルダを使います。';
  }
  if (fieldId === 'dswPath') {
    return 'VC6 .dsw ファイルの絶対パスを入力してください。';
  }
  if (fieldId === 'outputRoot') {
    return '生成物の出力ルートフォルダを入力してください。関数名フォルダはこの下に自動作成されます。';
  }
  if (fieldId === 'suiteManifestPath') {
    return '複数関数回帰スイートmanifestのパスを入力してください。空にすると outputRoot\\suites\\default\\suite_manifest.json を使います。';
  }
  if (fieldId === 'defaultConfiguration') {
    return 'VC6構成名を入力してください。';
  }
  if (fieldId === 'defaultProject') {
    return '既定プロジェクト名を入力してください。空にすると指定なしになります。';
  }
  if (fieldId === 'vcvarsPath') {
    return 'VC6環境設定バッチの絶対パスを入力してください。例: C:\\Program Files\\Microsoft Visual Studio\\VC98\\Bin\\VCVARS32.BAT';
  }
  if (fieldId === 'cliPath') {
    return '外部CLI exeの絶対パスを入力してください。同梱CLIを使う場合は unit-test-runner または空にします。';
  }
  return '値を入力してください。';
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

async function runWorkspaceCommand(context: vscode.ExtensionContext, output: vscode.OutputChannel, kind: 'finalize' | 'testDesign' | 'harness' | 'buildProbeDryRun' | 'buildProbeRun' | 'runTests' | 'evidence', workflowPanel: WorkflowPanelProvider): Promise<void> {
  const settings = readConfig(context);
  showValidation(settings);
  const workspace = await lastWorkspace(context);
  let invocation: CliInvocation;
  if (kind === 'finalize') {
    invocation = buildFinalizeDossierInvocation(settings, workspace);
  } else if (kind === 'testDesign') {
    invocation = buildGenerateTestDesignInvocation(settings, path.join(workspace, 'reports', 'function_dossier.json'));
  } else if (kind === 'harness') {
    invocation = buildGenerateHarnessSkeletonInvocation(settings, workspace);
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
    const selected = await vscode.window.showWarningMessage('このコマンドは生成されたツールまたはテストを実行する可能性があります。続行しますか？', { modal: true }, '続行');
    if (selected !== '続行') {
      throw new Error('UnitTestRunnerコマンドをキャンセルしました。');
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
    await recordWorkflowError(context, workflowPanel, 'unit-test-runnerがタイムアウトしました。');
    throw new Error('unit-test-runnerがタイムアウトしました。');
  }
  if (result.exitCode !== 0) {
    const message = formatCliFailureMessage(result.stdout, result.stderr, result.exitCode);
    await recordWorkflowError(context, workflowPanel, message);
    throw new Error(message);
  }
  const parsed = parseCliResult(result.stdout, result.stderr, outputWorkspace);
  await context.globalState.update(LAST_WORKSPACE_KEY, parsed.reports.workspace);
  return parsed.reports;
}

async function executeSuiteInvocation(context: vscode.ExtensionContext, output: vscode.OutputChannel, invocation: CliInvocation, suitePanel: SuitePanelProvider): Promise<void> {
  if (invocation.requiresConfirmation) {
    const selected = await vscode.window.showWarningMessage('このコマンドは登録済みスイートのテストを実行する可能性があります。続行しますか？', { modal: true }, '続行');
    if (selected !== '続行') {
      throw new Error('UnitTestRunnerスイートコマンドをキャンセルしました。');
    }
  }
  await context.globalState.update(LAST_COMMAND_KEY, invocation.displayCommand);
  output.show(true);
  output.appendLine(`> ${invocation.displayCommand}`);
  const result = await runCliInvocation(invocation);
  output.append(result.stdout);
  output.append(result.stderr);
  suitePanel.refresh();
  if (result.timedOut) {
    throw new Error('unit-test-runnerがタイムアウトしました。');
  }
  if (result.exitCode !== 0) {
    throw new Error(formatCliFailureMessage(result.stdout, result.stderr, result.exitCode));
  }
}

function workflowCommandKind(kind: 'finalize' | 'testDesign' | 'harness' | 'buildProbeDryRun' | 'buildProbeRun' | 'runTests' | 'evidence'): WorkflowCommandKind {
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
  const selected = await vscode.window.showInputBox({ prompt: '出力workspaceのパスを入力してください。' });
  if (!selected) {
    throw new Error('出力workspaceの指定が必要です。');
  }
  await context.globalState.update(LAST_WORKSPACE_KEY, selected);
  return selected;
}

async function openLastReport(context: vscode.ExtensionContext, key: keyof ReportPaths): Promise<void> {
  const workspace = context.globalState.get<string>(LAST_WORKSPACE_KEY);
  const remembered = key === 'functionDossierMd' ? context.globalState.get<string>(LAST_DOSSIER_KEY) : undefined;
  const reportPath = remembered || (workspace ? resolveReportPaths(workspace)[key] : undefined);
  if (!reportPath) {
    throw new Error('記録済みの出力workspaceがありません。');
  }
  await openReport(reportPath);
}

async function openSuiteManifest(context: vscode.ExtensionContext): Promise<void> {
  const suitePath = buildSuiteManifestPath(readConfig(context));
  if (!fs.existsSync(suitePath)) {
    throw new Error(`スイートmanifestがまだありません: ${suitePath}`);
  }
  await openReport(suitePath);
}

async function openSuiteRunReport(context: vscode.ExtensionContext): Promise<void> {
  const suitePath = buildSuiteManifestPath(readConfig(context));
  const reportPath = path.join(path.dirname(suitePath), 'reports', 'suite_run_report.md');
  if (!fs.existsSync(reportPath)) {
    throw new Error(`スイート実行レポートがまだありません: ${reportPath}`);
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
    throw new Error('記録済みのUnitTestRunnerコマンドがありません。');
  }
  await vscode.env.clipboard.writeText(command);
}

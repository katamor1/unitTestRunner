import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

import {
  buildAnalyzeFunctionInvocation,
  buildBuildProbeInvocation,
  buildFinalizeDossierInvocation,
  buildFullGateAnalyzeInvocation,
  buildGenerateHarnessSkeletonInvocation,
  buildGenerateTestDesignInvocation,
  buildPrepareEvidenceInvocation,
  buildQuickCheckInvocation,
  buildQuickOutputWorkspace,
  buildReanalyzeFunctionInvocation,
  buildRunTestsInvocation,
  buildSuiteManifestPath,
  buildSuiteRegisterInvocation,
  buildSuiteRunInvocation,
  CliInvocation,
  FunctionTarget,
  normalizeQuickCheckProfile,
  QuickCheckProfile,
  relativeSourcePath,
} from './cli/commandBuilder';
import {
  registerUnitTestRunnerCommands,
  UnitTestRunnerCommandHandlers,
} from './commands/commandRegistry';
import { createQuickCommandHandlers } from './commands/quickCommands';
import { CliResult, runCliInvocation } from './cli/cliRunner';
import { formatCliFailureMessage, parseCliResult } from './cli/cliResultParser';
import { DEFAULT_CLI_PATH, resolveCliPath } from './config/bundledCli';
import { AdapterSettings, defaultSourceRootFromWorkspaceFolders, RawSettings, readAdapterSettingsFromObject } from './config/settings';
import { buildSettingsViewModel, SettingsActionKind, SettingsFieldId, SettingsViewModel } from './config/settingsViewModel';
import { validateSettings } from './config/validation';
import { resolveFunctionNameFromText } from './functionTarget/regexFunctionResolver';
import { ReportPaths, resolveReportPaths } from './reports/reportPathResolver';
import { openMarkdown, openReport } from './reports/reportOpener';
import { SuiteDashboardPanel } from './suite/suiteDashboard';
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
const LAST_SUITE_ERROR_KEY = 'unitTestRunner.lastSuiteError';

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
  let suiteDashboard: SuiteDashboardPanel;
  const suiteManifestPath = () => buildSuiteManifestPath(readConfig(context));
  const lastSuiteError = () => context.workspaceState.get<string>(LAST_SUITE_ERROR_KEY);
  suiteDashboard = new SuiteDashboardPanel(context, suiteManifestPath, lastSuiteError);
  suitePanel = new SuitePanelProvider(context, suiteManifestPath, lastSuiteError);
  context.subscriptions.push(vscode.window.registerWebviewViewProvider(WorkflowPanelProvider.viewType, workflowPanel));
  context.subscriptions.push(vscode.window.registerWebviewViewProvider(SuitePanelProvider.viewType, suitePanel));
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((event) => {
    if (event.affectsConfiguration('unitTestRunner')) {
      workflowPanel.refresh();
      suitePanel.refresh();
      suiteDashboard.refresh();
    }
  }));
  context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(async (document) => {
    const state = readWorkflowState(context);
    const result = completeAwaitingSaveIfMatches(state, document.uri.fsPath);
    if (result.matched) {
      await context.workspaceState.update(WORKFLOW_STATE_KEY, result.state);
      workflowPanel.refresh();
      void vscode.window.showInformationMessage('UnitTestRunner: ファイルの保存を確認しました。次のステップへ進めます。');
    }
  }));

  const quickHandlers = createQuickCommandHandlers({
    getQuickProfile: () => normalizeQuickCheckProfile(readConfig(context).quickProfile),
    runQuickCheck: (profile) => quickCheckActiveFunction(context, output, workflowPanel, profile),
    openGeneratedTestSource: () => openGeneratedTestSource(context),
    openQuickSummary: () => openQuickSummary(context),
    runFullGate: () => runFullGateForCurrentFunction(context, output, workflowPanel),
    showError: (message) => {
      void vscode.window.showErrorMessage(message);
    },
  });
  const handlers: UnitTestRunnerCommandHandlers = {
    ...quickHandlers,
    'unitTestRunner.analyzeCurrentFunction': async () => analyzeActiveFunction(context, output, workflowPanel),
    'unitTestRunner.analyzeSelectedFunction': async () => analyzeActiveFunction(context, output, workflowPanel),
    'unitTestRunner.reanalyzeCurrentFunction': async () => reanalyzeActiveFunction(context, output, workflowPanel),
    'unitTestRunner.finalizeDossier': async () => runWorkspaceCommand(context, output, 'finalize', workflowPanel),
    'unitTestRunner.openFunctionDossier': async () => openLastReport(context, 'functionDossierMd'),
    'unitTestRunner.openReviewChecklist': async () => openLastReport(context, 'reviewChecklistMd'),
    'unitTestRunner.openNextActions': async () => openLastReport(context, 'nextActionsMd'),
    'unitTestRunner.openChangeImpactReport': async () => openLastReport(context, 'changeImpactReportMd'),
    'unitTestRunner.openRegressionSelection': async () => openLastReport(context, 'regressionSelectionCsv'),
    'unitTestRunner.generateTestDesign': async () => runWorkspaceCommand(context, output, 'testDesign', workflowPanel),
    'unitTestRunner.generateHarnessSkeleton': async () => runWorkspaceCommand(context, output, 'harness', workflowPanel),
    'unitTestRunner.buildProbeDryRun': async () => runWorkspaceCommand(context, output, 'buildProbeDryRun', workflowPanel),
    'unitTestRunner.runBuildProbe': async () => runWorkspaceCommand(context, output, 'buildProbeRun', workflowPanel),
    'unitTestRunner.runTests': async () => runWorkspaceCommand(context, output, 'runTests', workflowPanel),
    'unitTestRunner.prepareEvidence': async () => runWorkspaceCommand(context, output, 'evidence', workflowPanel),
    'unitTestRunner.registerCurrentFunctionInSuite': async () => registerActiveFunctionInSuite(context, output, workflowPanel, suitePanel, suiteDashboard),
    'unitTestRunner.openSuite': async () => suiteDashboard.open(),
    'unitTestRunner.openSuiteDashboard': async () => suiteDashboard.open(),
    'unitTestRunner.openSuiteManifest': async () => openSuiteManifest(context),
    'unitTestRunner.runSelectedSuiteTests': async () => runSuiteCommand(context, output, { selected: true, run: true }, suitePanel, suiteDashboard),
    'unitTestRunner.runSuiteByTag': async () => runSuiteByTag(context, output, suitePanel, suiteDashboard),
    'unitTestRunner.runAllSuiteTestsRequireGreen': async () => runSuiteCommand(context, output, { all: true, run: true, requireGreen: true }, suitePanel, suiteDashboard),
    'unitTestRunner.openSuiteRunReport': async () => openSuiteRunReport(context),
    'unitTestRunner.openOutputWorkspace': async () => openOutputWorkspace(context),
    'unitTestRunner.copyLastCommand': async () => copyLastCommand(context),
    'unitTestRunner.openLastFunctionDossier': async () => openLastReport(context, 'functionDossierMd'),
  };
  const commandRegistry = {
    registerCommand: (command: string, handler: (...args: unknown[]) => unknown) =>
      vscode.commands.registerCommand(command, (...args: unknown[]) => handler(...args)),
  };
  context.subscriptions.push(
    ...registerUnitTestRunnerCommands(context, { registry: commandRegistry, handlers }),
  );
}

export function deactivate(): void {
  // No long-lived process is kept by this thin adapter.
}

async function quickCheckActiveFunction(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  workflowPanel: WorkflowPanelProvider,
  profile: QuickCheckProfile,
): Promise<void> {
  const settings: AdapterSettings = { ...readConfig(context), quickProfile: profile };
  showValidation(settings);
  const targetBase = await activeFunctionTarget(context);
  const outputWorkspace = buildQuickOutputWorkspace(settings, targetBase);
  const target = { ...targetBase, outputWorkspace };
  const invocation = buildQuickCheckInvocation(settings, target);
  const reports = await executeInvocation(
    context,
    output,
    invocation,
    outputWorkspace,
    workflowPanel,
  );
  const kind: WorkflowCommandKind = profile === 'design'
    ? 'analyze'
    : profile === 'harness'
      ? 'harness'
      : 'buildProbeDryRun';
  await recordWorkflowSuccess(context, workflowPanel, {
    kind,
    outputWorkspace,
    functionName: target.functionName,
    reports,
  });
  if (settings.quickAutoOpenSummary && reports.quickSummaryMd) {
    await openMarkdown(reports.quickSummaryMd);
  }
}

async function runFullGateForCurrentFunction(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel,
  workflowPanel: WorkflowPanelProvider,
): Promise<void> {
  const settings = readConfig(context);
  showValidation(settings);
  const target = await activeFunctionTarget(context);
  const invocation = buildFullGateAnalyzeInvocation(settings, target);
  const reports = await executeInvocation(
    context,
    output,
    invocation,
    target.outputWorkspace,
    workflowPanel,
  );
  await recordWorkflowSuccess(context, workflowPanel, {
    kind: 'analyze',
    outputWorkspace: target.outputWorkspace,
    functionName: target.functionName,
    reports,
  });
  if (settings.autoOpenDossier && reports.functionDossierMd) {
    await openMarkdown(reports.functionDossierMd);
  }
}

async function openGeneratedTestSource(context: vscode.ExtensionContext): Promise<void> {
  const workspace = await lastWorkspace(context);
  const functionName = await lastFunctionName(context);
  const candidates = generatedTestSourceCandidates(workspace, functionName);
  const existing = candidates.find((candidate) => fs.existsSync(candidate));
  if (existing) {
    await openReport(existing);
    return;
  }
  const generatedTests = path.join(workspace, 'generated', 'tests');
  if (fs.existsSync(generatedTests)) {
    const matches = fs.readdirSync(generatedTests)
      .filter((name) => /^test_.*\.c$/i.test(name))
      .map((name) => path.join(generatedTests, name));
    if (matches.length === 1) {
      await openReport(matches[0]);
      return;
    }
    if (matches.length > 1) {
      const selected = await vscode.window.showQuickPick(matches, {
        placeHolder: '開くテストソースを選んでください。',
      });
      if (selected) {
        await openReport(selected);
        return;
      }
    }
  }
  throw new Error(`生成したテストソースが見つかりません。確認先: ${candidates[0]}`);
}

async function openQuickSummary(context: vscode.ExtensionContext): Promise<void> {
  const workspace = await lastWorkspace(context);
  const report = resolveReportPaths(workspace).quickSummaryMd
    ?? path.join(workspace, 'reports', 'quick_summary.md');
  await openReport(report);
}

async function lastFunctionName(context: vscode.ExtensionContext): Promise<string> {
  const state = readWorkflowState(context);
  if (state.functionName) {
    return state.functionName;
  }
  const prompt = await vscode.window.showInputBox({
    prompt: 'テストソースを開く対象の関数名を入力してください。',
    validateInput: (value) => (/^[A-Za-z_]\w*$/.test(value) ? undefined : 'C言語の関数名として有効な識別子を入力してください。'),
  });
  if (!prompt) {
    throw new Error('関数名を入力してください。');
  }
  return prompt;
}

function generatedTestSourceCandidates(workspace: string, functionName: string): string[] {
  const safe = sanitizeIdentifier(functionName);
  return [
    path.join(workspace, 'generated', 'tests', `test_${safe}.c`),
    path.join(workspace, 'generated', 'tests', `test_${functionName}.c`),
  ];
}

function sanitizeIdentifier(value: string): string {
  const sanitized = value.replace(/\W+/g, '_').replace(/^_+|_+$/g, '');
  if (!sanitized) {
    return 'item';
  }
  return /^\d/.test(sanitized) ? `_${sanitized}` : sanitized;
}

async function analyzeActiveFunction(context: vscode.ExtensionContext, output: vscode.OutputChannel, workflowPanel: WorkflowPanelProvider): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    throw new Error('Cソースファイルを開き、対象の関数内にカーソルを置いてから実行してください。');
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
    throw new Error('Cソースファイルを開き、対象の関数内にカーソルを置いてから実行してください。');
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

async function registerActiveFunctionInSuite(context: vscode.ExtensionContext, output: vscode.OutputChannel, workflowPanel: WorkflowPanelProvider, suitePanel: SuitePanelProvider, suiteDashboard: SuiteDashboardPanel): Promise<void> {
  const target = await activeFunctionTarget(context);
  const settings = readConfig(context);
  const invocation = buildSuiteRegisterInvocation(settings, target, ['selected', 'regression']);
  const completed = await executeSuiteInvocation(context, output, invocation, suitePanel, suiteDashboard);
  if (!completed) {
    return;
  }
  await context.globalState.update(LAST_WORKSPACE_KEY, target.outputWorkspace);
  workflowPanel.refresh();
  suiteDashboard.refresh();
  void vscode.window.showInformationMessage('UnitTestRunner: 現在の関数をテストスイートに登録しました。');
}

async function activeFunctionTarget(context: vscode.ExtensionContext): Promise<FunctionTarget> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    throw new Error('Cソースファイルを開き、対象の関数内にカーソルを置いてから実行してください。');
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

async function runSuiteByTag(context: vscode.ExtensionContext, output: vscode.OutputChannel, suitePanel: SuitePanelProvider, suiteDashboard: SuiteDashboardPanel): Promise<void> {
  const tag = await vscode.window.showInputBox({
    prompt: '実行するテストに付けられたタグを入力してください。',
    value: 'selected',
  });
  if (!tag) {
    throw new Error('実行するタグを入力してください。');
  }
  await runSuiteCommand(context, output, { tag: tag.trim(), run: true }, suitePanel, suiteDashboard);
}

async function runSuiteCommand(context: vscode.ExtensionContext, output: vscode.OutputChannel, options: SuiteCommandOptions, suitePanel: SuitePanelProvider, suiteDashboard: SuiteDashboardPanel): Promise<void> {
  const settings = readConfig(context);
  showValidation(settings);
  const entryIds = options.selected ? readSelectedSuiteEntryIds(context) : undefined;
  if (options.selected && (!entryIds || entryIds.length === 0)) {
    throw new Error('テストスイートで実行する関数を選択してください。');
  }
  const invocation = buildSuiteRunInvocation(settings, {
    entryIds,
    tag: options.tag,
    all: options.all,
    run: options.run,
    requireGreen: options.requireGreen,
  });
  await executeSuiteInvocation(context, output, invocation, suitePanel, suiteDashboard);
  if (options.all && options.requireGreen) {
    suiteDashboard.open();
  }
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
    throw new Error(`UnitTestRunnerの必須設定が不足しています。ワークフローパネルの［設定］を確認してください。${validation.warnings.map((warning) => ` ${warning.message}`).join('')}`);
  }
}

async function handleSettingsAction(fieldId: SettingsFieldId, kind: SettingsActionKind): Promise<void> {
  ensureWorkspaceSettingsTarget();
  const model = readSettingsViewModel();
  const field = model.fields.find((item) => item.id === fieldId);
  if (!field) {
    throw new Error(`設定項目を認識できません: ${fieldId}`);
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
      openLabel: 'このフォルダーを選択',
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
      openLabel: 'このファイルを選択',
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
    throw new Error('設定を保存するには、VS Codeでフォルダーまたはワークスペースを開いてください。');
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
    return { 'Visual C++ワークスペース': ['dsw'], 'すべてのファイル': ['*'] };
  }
  if (fieldId === 'cliPath') {
    return { '実行ファイル': ['exe'], 'すべてのファイル': ['*'] };
  }
  if (fieldId === 'suiteManifestPath') {
    return { 'JSON': ['json'], 'すべてのファイル': ['*'] };
  }
  if (fieldId === 'vcvarsPath') {
    return { 'バッチファイル': ['bat', 'cmd'], 'すべてのファイル': ['*'] };
  }
  return { 'すべてのファイル': ['*'] };
}

function inputPrompt(fieldId: SettingsFieldId): string {
  if (fieldId === 'sourceRoot') {
    return 'ソースのルートフォルダーのパスを入力してください。空欄の場合は、VS Codeで最初に開いたフォルダーを使用します。';
  }
  if (fieldId === 'dswPath') {
    return 'VC6ワークスペースファイル（.dsw）の絶対パスを入力してください。';
  }
  if (fieldId === 'outputRoot') {
    return '生成物を保存する出力先フォルダーを入力してください。関数ごとのフォルダーは、この中に自動で作成されます。';
  }
  if (fieldId === 'suiteManifestPath') {
    return 'テストスイートの定義ファイルのパスを入力してください。空欄の場合は、出力先フォルダー配下のsuites\\default\\suite_manifest.jsonを使用します。';
  }
  if (fieldId === 'defaultConfiguration') {
    return 'Visual C++ 6.0のビルド構成名を入力してください。';
  }
  if (fieldId === 'defaultProject') {
    return '既定として使用するVisual C++ 6.0のプロジェクト名を入力してください。空欄の場合は指定しません。';
  }
  if (fieldId === 'vcvarsPath') {
    return 'Visual C++ 6.0の環境設定バッチファイルの絶対パスを入力してください。例: C:\\Program Files\\Microsoft Visual Studio\\VC98\\Bin\\VCVARS32.BAT';
  }
  if (fieldId === 'cliPath') {
    return '外部のUnitTestRunner実行ファイルの絶対パスを入力してください。同梱のCLIを使用する場合は、unit-test-runnerまたは空欄にします。';
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
    validateInput: (value) => (/^[A-Za-z_]\w*$/.test(value) ? undefined : 'C言語の関数名として有効な識別子を入力してください。'),
  });
  if (!prompt) {
    throw new Error('関数名が入力されなかったため、解析を中止しました。');
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

interface ExecutionConfirmation {
  operation: string;
  message: string;
  action: string;
}

function executionConfirmation(invocation: CliInvocation): ExecutionConfirmation {
  if (invocation.args.includes('build-probe')) {
    return {
      operation: 'ビルド',
      message: '生成したテストをビルドします。ビルドを実行してもよろしいですか？',
      action: 'ビルドを実行',
    };
  }
  if (invocation.args.includes('run-tests')) {
    return {
      operation: 'テスト実行',
      message: '生成したテストを実行します。テストを実行してもよろしいですか？',
      action: 'テストを実行',
    };
  }
  return {
    operation: '処理',
    message: '生成したツールまたはテストを実行します。実行してもよろしいですか？',
    action: '実行する',
  };
}

async function executeInvocation(context: vscode.ExtensionContext, output: vscode.OutputChannel, invocation: CliInvocation, outputWorkspace: string, workflowPanel: WorkflowPanelProvider): Promise<ReportPaths> {
  if (invocation.requiresConfirmation) {
    const confirmation = executionConfirmation(invocation);
    const selected = await vscode.window.showWarningMessage(
      confirmation.message,
      { modal: true },
      confirmation.action,
    );
    if (selected !== confirmation.action) {
      throw new Error(`${confirmation.operation}を中止しました。`);
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
    await recordWorkflowError(context, workflowPanel, 'UnitTestRunner CLIの処理がタイムアウトしました。');
    throw new Error('UnitTestRunner CLIの処理がタイムアウトしました。');
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

async function executeSuiteInvocation(context: vscode.ExtensionContext, output: vscode.OutputChannel, invocation: CliInvocation, suitePanel: SuitePanelProvider, suiteDashboard: SuiteDashboardPanel): Promise<boolean> {
  if (invocation.requiresConfirmation) {
    const runAll = invocation.args.includes('--all');
    const action = runAll ? '全件テストを実行' : 'テストスイートを実行';
    const message = runAll
      ? '登録されているすべてのテストを実行し、合否を確認します。実行してもよろしいですか？'
      : '選択したテストスイートを実行します。実行してもよろしいですか？';
    const selected = await vscode.window.showWarningMessage(message, { modal: true }, action);
    if (selected !== action) {
      return false;
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
    await recordSuiteError(context, suitePanel, suiteDashboard, message);
    await showSuiteError(context, `UnitTestRunner CLIを起動できませんでした。 ${message}`);
    return false;
  }
  output.append(result.stdout);
  output.append(result.stderr);
  if (result.timedOut) {
    const message = 'UnitTestRunner CLIの処理がタイムアウトしました。';
    await recordSuiteError(context, suitePanel, suiteDashboard, message);
    await showSuiteError(context, message);
    return false;
  }
  if (result.exitCode !== 0) {
    const message = formatCliFailureMessage(result.stdout, result.stderr, result.exitCode);
    await recordSuiteError(context, suitePanel, suiteDashboard, message);
    await showSuiteError(context, message);
    return false;
  }
  await context.workspaceState.update(LAST_SUITE_ERROR_KEY, undefined);
  suitePanel.refresh();
  suiteDashboard.refresh();
  const summary = suiteSummaryFromStdout(result.stdout);
  if (summary) {
    void vscode.window.showInformationMessage(`UnitTestRunner: テストスイートの実行が完了しました。合計${summary.total}件のうち、${summary.green}件合格、${summary.notGreen}件不合格でした。`);
  }
  return true;
}

async function recordSuiteError(context: vscode.ExtensionContext, suitePanel: SuitePanelProvider, suiteDashboard: SuiteDashboardPanel, message: string): Promise<void> {
  await context.workspaceState.update(LAST_SUITE_ERROR_KEY, message);
  suitePanel.refresh();
  suiteDashboard.refresh();
}

async function showSuiteError(context: vscode.ExtensionContext, message: string): Promise<void> {
  const selected = await vscode.window.showErrorMessage(`UnitTestRunner: ${message}`, '実行レポートを開く');
  if (selected === '実行レポートを開く') {
    try {
      await openSuiteRunReport(context);
    } catch {
      // The command may have failed before a report was written.
    }
  }
}

function suiteSummaryFromStdout(stdout: string): { total: number; green: number; notGreen: number } | undefined {
  try {
    const parsed = JSON.parse(stdout) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return undefined;
    }
    const data = (parsed as { data?: unknown }).data;
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      return undefined;
    }
    const summary = (data as { summary?: unknown }).summary;
    if (!summary || typeof summary !== 'object' || Array.isArray(summary)) {
      return undefined;
    }
    return {
      total: numberFromUnknown((summary as { total?: unknown }).total),
      green: numberFromUnknown((summary as { green?: unknown }).green),
      notGreen: numberFromUnknown((summary as { not_green?: unknown }).not_green),
    };
  } catch {
    return undefined;
  }
}

function numberFromUnknown(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
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
  const selected = await vscode.window.showInputBox({ prompt: '出力ワークスペースのフォルダーパスを入力してください。' });
  if (!selected) {
    throw new Error('出力ワークスペースのフォルダーパスを入力してください。');
  }
  await context.globalState.update(LAST_WORKSPACE_KEY, selected);
  return selected;
}

async function openLastReport(context: vscode.ExtensionContext, key: keyof ReportPaths): Promise<void> {
  const workspace = context.globalState.get<string>(LAST_WORKSPACE_KEY);
  const remembered = key === 'functionDossierMd' ? context.globalState.get<string>(LAST_DOSSIER_KEY) : undefined;
  const reportPath = remembered || (workspace ? resolveReportPaths(workspace)[key] : undefined);
  if (!reportPath) {
    throw new Error('記録された出力ワークスペースがありません。先に関数解析またはクイックチェックを実行してください。');
  }
  await openReport(reportPath);
}

async function openSuiteManifest(context: vscode.ExtensionContext): Promise<void> {
  const suitePath = buildSuiteManifestPath(readConfig(context));
  if (!fs.existsSync(suitePath)) {
    throw new Error(`スイート定義ファイルが見つかりません。確認先: ${suitePath}`);
  }
  await openReport(suitePath);
}

async function openSuiteRunReport(context: vscode.ExtensionContext): Promise<void> {
  const suitePath = buildSuiteManifestPath(readConfig(context));
  const reportPath = path.join(path.dirname(suitePath), 'reports', 'suite_run_report.md');
  if (!fs.existsSync(reportPath)) {
    throw new Error(`テストスイートの実行レポートが見つかりません。先にテストスイートを実行してください。確認先: ${reportPath}`);
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
    throw new Error('記録されたCLIコマンドがありません。先にいずれかの処理を実行してください。');
  }
  await vscode.env.clipboard.writeText(command);
}

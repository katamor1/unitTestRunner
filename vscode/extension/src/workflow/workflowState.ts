import { ReportPaths } from '../reports/reportPathResolver';

export const WORKFLOW_STATE_KEY = 'unitTestRunner.workflowState';

export type WorkflowStepId =
  | 'settings'
  | 'analyze'
  | 'finalizeDossier'
  | 'reviewTestSpec'
  | 'prepareHarness'
  | 'buildProbeDryRun'
  | 'buildProbeRun'
  | 'runTests'
  | 'complete';

export type WorkflowStepStatus = 'done' | 'current' | 'pending';

export type WorkflowCommandKind =
  | 'analyze'
  | 'finalize'
  | 'review'
  | 'harness'
  | 'buildProbeDryRun'
  | 'buildProbeRun'
  | 'runTests'
  | 'reanalyze'
  | 'applyReanalysis';

export type WorkflowActionKind =
  | 'command'
  | 'openReport'
  | 'confirmStep'
  | 'openSettings'
  | 'openOutputWorkspace'
  | 'copyLastCommand';

export interface WorkflowState {
  settingsReady: boolean;
  workspaceFolderUri?: string;
  outputWorkspace?: string;
  sourcePath?: string;
  functionName?: string;
  reports?: Partial<ReportPaths>;
  completedStepIds: WorkflowStepId[];
  lastError?: string;
  updatedAt?: string;
}

export interface WorkflowReportAvailability {
  functionDossier: boolean;
  testSpec: boolean;
  reviewRecord: boolean;
  buildProbeReport: boolean;
  testRunReport: boolean;
  reanalysisReport: boolean;
}

export interface WorkflowAction {
  id: string;
  kind: WorkflowActionKind;
  label: string;
  repeatLabel?: string;
  commandId?: string;
  reportKey?: keyof ReportPaths;
  stepId?: WorkflowStepId;
  primary?: boolean;
  danger?: boolean;
}

export interface WorkflowStepDefinition {
  id: WorkflowStepId;
  title: string;
  purpose: string;
  requiredAction: string;
  actions: WorkflowAction[];
}

export interface WorkflowStepView extends WorkflowStepDefinition {
  status: WorkflowStepStatus;
}

export interface WorkflowCommandSuccess {
  kind: WorkflowCommandKind;
  reviewDecision?: 'approved' | 'changes_requested';
  workspaceFolderUri?: string;
  outputWorkspace?: string;
  sourcePath?: string;
  functionName?: string;
  reports?: ReportPaths;
}

export const EMPTY_REPORT_AVAILABILITY: WorkflowReportAvailability = {
  functionDossier: false,
  testSpec: false,
  reviewRecord: false,
  buildProbeReport: false,
  testRunReport: false,
  reanalysisReport: false,
};

export const WORKFLOW_STEP_DEFINITIONS: WorkflowStepDefinition[] = [
  {
    id: 'settings',
    title: '1. 設定確認',
    purpose: '対象source、VC6 workspace、外部output、CLIを確認します。',
    requiredAction: '不足しているresource-scoped設定を入力します。',
    actions: [{ id: 'openSettings', kind: 'openSettings', label: '設定を開く', primary: true }],
  },
  {
    id: 'analyze',
    title: '2. 関数を解析',
    purpose: '現在のC sourceからdossierとTestSpecを生成します。',
    requiredAction: '関数内へカーソルを置くか関数名を選択して解析します。',
    actions: [
      { id: 'analyzeCurrent', kind: 'command', label: '現在の関数を解析', repeatLabel: '現在の関数を再解析', commandId: 'unitTestRunner.analyzeCurrentFunction', primary: true },
      { id: 'analyzeSelected', kind: 'command', label: '選択した関数を解析', repeatLabel: '選択した関数を再解析', commandId: 'unitTestRunner.analyzeSelectedFunction' },
    ],
  },
  {
    id: 'finalizeDossier',
    title: '3. dossierを確定',
    purpose: '解析結果を公開function_dossierへまとめます。',
    requiredAction: 'dossierを確定し、通常の差分レビューを行います。',
    actions: [
      { id: 'finalizeDossier', kind: 'command', label: 'dossierを確定', repeatLabel: 'dossierを再確定', commandId: 'unitTestRunner.finalizeDossier', primary: true },
      { id: 'openDossier', kind: 'openReport', label: 'function_dossierを開く', reportKey: 'functionDossierMd' },
      { id: 'openReviewChecklist', kind: 'openReport', label: 'レビュー確認リストを開く', reportKey: 'reviewChecklistMd' },
    ],
  },
  {
    id: 'reviewTestSpec',
    title: '4. TestSpecをレビュー',
    purpose: 'canonical test_spec.jsonの入力、期待値、未解決項目を確認します。',
    requiredAction: '通常のartifact reviewを行い、approvedまたはchanges_requestedを記録します。',
    actions: [
      { id: 'openTestInputEditor', kind: 'command', label: 'TestSpecをレビュー', commandId: 'unitTestRunner.openTestInputEditor', primary: true },
      { id: 'openTestSpecMarkdown', kind: 'openReport', label: 'レビュー用Markdownを開く', reportKey: 'testSpecMd' },
      { id: 'openTestSpecJson', kind: 'openReport', label: 'canonical JSONを開く', reportKey: 'testSpecJson' },
    ],
  },
  {
    id: 'prepareHarness',
    title: '5. ハーネスを準備',
    purpose: 'レビュー済みTestSpecから外部workspaceへC90/CP932ハーネスを生成します。',
    requiredAction: 'TestSpecのapproval後にハーネスを準備します。',
    actions: [{ id: 'prepareHarness', kind: 'command', label: 'ハーネスを準備', repeatLabel: 'ハーネスを再準備', commandId: 'unitTestRunner.prepareHarness', primary: true }],
  },
  {
    id: 'buildProbeDryRun',
    title: '6. ビルド事前確認',
    purpose: '実行せずに生成workspaceとビルド手順を確認します。',
    requiredAction: 'ビルドの事前確認を実行します。',
    actions: [{ id: 'buildProbeDryRun', kind: 'command', label: '事前確認を実行', repeatLabel: '事前確認を再実行', commandId: 'unitTestRunner.buildProbeDryRun', primary: true }],
  },
  {
    id: 'buildProbeRun',
    title: '7. ビルド',
    purpose: '確認済みハーネスをビルドします。',
    requiredAction: '確認ダイアログを確認してビルドします。',
    actions: [
      { id: 'runBuildProbe', kind: 'command', label: 'ビルドを実行', repeatLabel: 'ビルドを再実行', commandId: 'unitTestRunner.runBuildProbe', primary: true, danger: true },
      { id: 'openBuildProbe', kind: 'openReport', label: 'ビルド結果を開く', reportKey: 'buildProbeReportMd' },
    ],
  },
  {
    id: 'runTests',
    title: '8. テスト実行',
    purpose: '明示選択されたテストを実行し、通常のrun reportを保存します。',
    requiredAction: '確認ダイアログを確認してテストを実行します。',
    actions: [
      { id: 'runTests', kind: 'command', label: 'テストを実行', repeatLabel: 'テストを再実行', commandId: 'unitTestRunner.runTests', primary: true, danger: true },
      { id: 'openTestRun', kind: 'openReport', label: 'テスト結果を開く', reportKey: 'testRunReportMd' },
    ],
  },
  {
    id: 'complete',
    title: '9. 完了',
    purpose: '固定されたv0.1 workflowが完了しました。',
    requiredAction: '必要に応じて出力workspaceを開きます。',
    actions: [
      { id: 'openOutputWorkspace', kind: 'openOutputWorkspace', label: '出力ワークスペースを開く', primary: true },
      { id: 'copyLastCommand', kind: 'copyLastCommand', label: '最後のCLIコマンドをコピー' },
    ],
  },
];

export const OPTIONAL_WORKFLOW_ACTIONS: WorkflowAction[] = [
  { id: 'reanalyzeCurrent', kind: 'command', label: '変更後の関数を再解析', commandId: 'unitTestRunner.reanalyzeCurrentFunction', primary: true },
  { id: 'openReanalysis', kind: 'openReport', label: '再解析レポートを開く', reportKey: 'reanalysisReportMd' },
  { id: 'openOutputWorkspace', kind: 'openOutputWorkspace', label: '出力ワークスペースを開く' },
  { id: 'copyLastCommand', kind: 'copyLastCommand', label: '最後のCLIコマンドをコピー' },
];

const COMMAND_STEP_MAP: Record<WorkflowCommandKind, WorkflowStepId> = {
  analyze: 'analyze',
  finalize: 'finalizeDossier',
  review: 'reviewTestSpec',
  harness: 'prepareHarness',
  buildProbeDryRun: 'buildProbeDryRun',
  buildProbeRun: 'buildProbeRun',
  runTests: 'runTests',
  reanalyze: 'analyze',
  applyReanalysis: 'analyze',
};

export function createInitialWorkflowState(settingsReady = false): WorkflowState {
  return { settingsReady, completedStepIds: settingsReady ? ['settings'] : [] };
}

export function markWorkflowCommandSucceeded(state: WorkflowState, event: WorkflowCommandSuccess): WorkflowState {
  const boundaryChanged = Boolean(
    (event.outputWorkspace && event.outputWorkspace !== state.outputWorkspace)
    || (event.workspaceFolderUri && event.workspaceFolderUri !== state.workspaceFolderUri),
  );
  const completed = new Set<WorkflowStepId>(boundaryChanged ? [] : state.completedStepIds);
  completed.add('settings');
  const completedStep = COMMAND_STEP_MAP[event.kind];
  invalidateFrom(completed, completedStep);
  if (event.kind !== 'review' || event.reviewDecision === 'approved') {
    completed.add(completedStep);
  }
  if (event.kind === 'runTests') {
    completed.add('complete');
  }
  return {
    ...state,
    settingsReady: true,
    workspaceFolderUri: event.workspaceFolderUri ?? state.workspaceFolderUri,
    outputWorkspace: event.outputWorkspace ?? state.outputWorkspace,
    sourcePath: event.sourcePath ?? state.sourcePath,
    functionName: event.functionName ?? state.functionName,
    reports: mergeReports(boundaryChanged ? undefined : invalidateReports(state.reports, completedStep), event.reports, event.outputWorkspace),
    completedStepIds: [...completed],
    lastError: undefined,
    updatedAt: timestamp(),
  };
}

export function markWorkflowCommandFailed(state: WorkflowState, message: string): WorkflowState {
  return { ...state, lastError: message, updatedAt: timestamp() };
}

export function setWorkflowSettingsReady(state: WorkflowState, settingsReady: boolean): WorkflowState {
  const completed = new Set(state.completedStepIds);
  if (settingsReady) completed.add('settings'); else completed.delete('settings');
  return { ...state, settingsReady, completedStepIds: [...completed], updatedAt: timestamp() };
}

export function completeWorkflowStep(state: WorkflowState, stepId: WorkflowStepId): WorkflowState {
  const completed = new Set(state.completedStepIds);
  completed.add(stepId);
  return { ...state, completedStepIds: [...completed], updatedAt: timestamp() };
}

export function reportAvailabilityFromPaths(
  reports: Partial<ReportPaths> | undefined,
  exists: (filePath: string) => boolean,
): WorkflowReportAvailability {
  const present = (key: keyof ReportPaths): boolean => {
    const value = reports?.[key];
    return typeof value === 'string' && value.length > 0 && exists(value);
  };
  return {
    functionDossier: present('functionDossierJson') || present('functionDossierMd'),
    testSpec: present('testSpecJson'),
    reviewRecord: present('reviewRecordJson'),
    buildProbeReport: present('buildProbeReportJson') || present('buildProbeReportMd'),
    testRunReport: present('testRunReportJson') || present('testRunReportMd'),
    reanalysisReport: present('reanalysisReportJson') || present('reanalysisReportMd'),
  };
}

export function deriveCurrentWorkflowStepId(state: WorkflowState, _availability: WorkflowReportAvailability): WorkflowStepId {
  if (!state.settingsReady) return 'settings';
  return WORKFLOW_STEP_DEFINITIONS.find((step) => !state.completedStepIds.includes(step.id))?.id ?? 'complete';
}

export function buildWorkflowStepViews(state: WorkflowState, availability: WorkflowReportAvailability): WorkflowStepView[] {
  const current = deriveCurrentWorkflowStepId(state, availability);
  return WORKFLOW_STEP_DEFINITIONS.map((definition) => ({
    ...definition,
    status: state.completedStepIds.includes(definition.id) && definition.id !== current
      ? 'done'
      : definition.id === current ? 'current' : 'pending',
  }));
}

function invalidateFrom(completed: Set<WorkflowStepId>, stepId: WorkflowStepId): void {
  const index = WORKFLOW_STEP_DEFINITIONS.findIndex((step) => step.id === stepId);
  for (const step of WORKFLOW_STEP_DEFINITIONS.slice(Math.max(0, index))) {
    completed.delete(step.id);
  }
}

function invalidateReports(reports: Partial<ReportPaths> | undefined, step: WorkflowStepId): Partial<ReportPaths> | undefined {
  if (!reports) return undefined;
  if (step === 'analyze') return reports.workspace ? { workspace: reports.workspace } : undefined;
  const result = { ...reports };
  const keys: Partial<Record<WorkflowStepId, Array<keyof ReportPaths>>> = {
    finalizeDossier: ['reviewRecordJson', 'buildProbeReportJson', 'buildProbeReportMd', 'testRunReportJson', 'testRunReportMd'],
    reviewTestSpec: ['buildProbeReportJson', 'buildProbeReportMd', 'testRunReportJson', 'testRunReportMd'],
    prepareHarness: ['buildProbeReportJson', 'buildProbeReportMd', 'testRunReportJson', 'testRunReportMd'],
    buildProbeDryRun: ['buildProbeReportJson', 'buildProbeReportMd', 'testRunReportJson', 'testRunReportMd'],
    buildProbeRun: ['testRunReportJson', 'testRunReportMd'],
  };
  for (const key of keys[step] ?? []) delete result[key];
  return result;
}

function mergeReports(
  current: Partial<ReportPaths> | undefined,
  incoming: ReportPaths | undefined,
  workspace: string | undefined,
): Partial<ReportPaths> | undefined {
  if (!current && !incoming && !workspace) return undefined;
  return { ...current, ...incoming, workspace: workspace ?? incoming?.workspace ?? current?.workspace ?? '' };
}

function timestamp(): string {
  return new Date().toISOString();
}

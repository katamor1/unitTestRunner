import * as path from 'path';

import { ReportPaths } from '../reports/reportPathResolver';
import { TestInputFormSummary } from '../testInputEditor/contracts';

export const WORKFLOW_STATE_KEY = 'unitTestRunner.workflowState';

export type WorkflowStepId =
  | 'settings'
  | 'analyze'
  | 'reviewDossier'
  | 'reviewWorkflowReports'
  | 'generateTestDesign'
  | 'reviewTestDesign'
  | 'generateHarnessSkeleton'
  | 'buildProbeDryRun'
  | 'reviewBuildProbe'
  | 'buildProbeRun'
  | 'runTests'
  | 'prepareEvidence'
  | 'reviewEvidence'
  | 'complete';

export type WorkflowStepStatus = 'done' | 'current' | 'pending';

export type WorkflowCommandKind =
  | 'analyze'
  | 'finalize'
  | 'testDesign'
  | 'harness'
  | 'buildProbeDryRun'
  | 'buildProbeRun'
  | 'runTests'
  | 'evidence'
  | 'reanalyze';

export type WorkflowActionKind =
  | 'command'
  | 'openReport'
  | 'confirmStep'
  | 'openSettings'
  | 'openOutputWorkspace'
  | 'copyLastCommand';

export interface AwaitingSave {
  stepId: WorkflowStepId;
  filePath: string;
  reportKey?: keyof ReportPaths;
  startedAt: string;
}

export interface WorkflowState {
  settingsReady: boolean;
  outputWorkspace?: string;
  functionName?: string;
  reports?: Partial<ReportPaths>;
  completedStepIds: WorkflowStepId[];
  awaitingSave?: AwaitingSave;
  lastError?: string;
  testInputSummary?: TestInputSummaryState;
  updatedAt?: string;
}

export type TestInputSummaryState =
  | {
      status: 'ready';
      workspace: string;
      revision: number;
      specSha256: string;
      summary: TestInputFormSummary;
      updatedAt: string;
    }
  | {
      status: 'error';
      workspace: string;
      message: string;
      updatedAt: string;
    };

export interface WorkflowReportAvailability {
  functionDossier: boolean;
  reviewChecklist: boolean;
  unresolvedItems: boolean;
  nextActions: boolean;
  testCaseDesign: boolean;
  harnessSkeletonReport: boolean;
  buildProbeReport: boolean;
  testExecutionReport: boolean;
  evidencePackage: boolean;
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
  outputWorkspace?: string;
  functionName?: string;
  reports?: ReportPaths;
}

export interface WorkflowLegacyProjection {
  lastWorkspace?: string;
  lastDossier?: string;
}

export const EMPTY_REPORT_AVAILABILITY: WorkflowReportAvailability = {
  functionDossier: false,
  reviewChecklist: false,
  unresolvedItems: false,
  nextActions: false,
  testCaseDesign: false,
  harnessSkeletonReport: false,
  buildProbeReport: false,
  testExecutionReport: false,
  evidencePackage: false,
};

export const WORKFLOW_STEP_DEFINITIONS: WorkflowStepDefinition[] = [
  {
    id: 'settings',
    title: '1. 設定確認',
    purpose: 'ソースのルートフォルダー、VC6ワークスペースファイル、出力先フォルダー、UnitTestRunnerの実行ファイルを確認します。',
    requiredAction: '［設定］でテスト対象プロジェクトと出力先を指定します。',
    actions: [
      { id: 'openSettings', kind: 'openSettings', label: '設定を開く', primary: true },
      { id: 'copyLastCommand', kind: 'copyLastCommand', label: '最後に実行したCLIコマンドをコピー' },
    ],
  },
  {
    id: 'analyze',
    title: '2. 関数を解析',
    purpose: '現在のCソースファイルと対象関数を解析し、関数分析レポートを生成します。',
    requiredAction: '関数内にカーソルを置くか関数名を選択して、解析を実行します。',
    actions: [
      { id: 'analyzeCurrent', kind: 'command', label: '現在の関数を解析', repeatLabel: '現在の関数を再解析', commandId: 'unitTestRunner.analyzeCurrentFunction', primary: true },
      { id: 'analyzeSelected', kind: 'command', label: '選択した関数を解析', repeatLabel: '選択した関数を再解析', commandId: 'unitTestRunner.analyzeSelectedFunction' },
    ],
  },
  {
    id: 'reviewDossier',
    title: '3. 関数分析レポート（function_dossier.md）を確認',
    purpose: '関数の概要、依存関係、カバレッジ、未解決事項を確認します。',
    requiredAction: 'function_dossier.mdを開いて内容を確認し、必要に応じて修正して保存します。',
    actions: [
      { id: 'openDossier', kind: 'openReport', label: '関数分析レポートを開く', reportKey: 'functionDossierMd', stepId: 'reviewDossier', primary: true },
      { id: 'confirmDossier', kind: 'confirmStep', label: '保存済みとして確定', stepId: 'reviewDossier' },
    ],
  },
  {
    id: 'reviewWorkflowReports',
    title: '4. レビュー項目を確認',
    purpose: 'レビュー確認リスト、未解決項目、次に行う操作を確認します。',
    requiredAction: '未解決項目と次に行う操作を確認し、必要に応じて編集して保存します。',
    actions: [
      { id: 'openReviewChecklist', kind: 'openReport', label: '確認リストを開く', reportKey: 'reviewChecklistMd', stepId: 'reviewWorkflowReports', primary: true },
      { id: 'openUnresolvedItems', kind: 'openReport', label: '未解決項目を開く', reportKey: 'unresolvedItemsMd', stepId: 'reviewWorkflowReports' },
      { id: 'openNextActions', kind: 'openReport', label: '次に行う操作を開く', reportKey: 'nextActionsMd', stepId: 'reviewWorkflowReports' },
      { id: 'confirmWorkflowReports', kind: 'confirmStep', label: '保存済みとして確定', stepId: 'reviewWorkflowReports' },
    ],
  },
  {
    id: 'generateTestDesign',
    title: '5. テスト設計を生成',
    purpose: '関数分析レポートからテストケース設計を生成します。',
    requiredAction: '［テスト設計を生成］を実行します。',
    actions: [
      { id: 'generateTestDesign', kind: 'command', label: 'テスト設計を生成', repeatLabel: 'テスト設計を再生成', commandId: 'unitTestRunner.generateTestDesign', primary: true },
    ],
  },
  {
    id: 'reviewTestDesign',
    title: '6. テストケース設計を確認',
    purpose: '生成されたテスト仕様を確認します。未確定の入力値・事前状態・スタブ・期待値は専用画面で入力します。',
    requiredAction: '［未確定項目を入力］を開いて必要な値を入力し、確認済みの項目を明示して保存します。CSVとMarkdownは確認用、test_spec.jsonは正本です。',
    actions: [
      { id: 'openTestInputEditor', kind: 'command', label: '未確定項目を入力', commandId: 'unitTestRunner.openTestInputEditor', stepId: 'reviewTestDesign', primary: true },
      { id: 'openTestDesign', kind: 'openReport', label: 'テスト仕様（CSV）を開く', reportKey: 'testSpecCsv', stepId: 'reviewTestDesign' },
      { id: 'openTestDesignMarkdown', kind: 'openReport', label: 'レビュー用Markdownを開く', reportKey: 'testSpecMd', stepId: 'reviewTestDesign' },
      { id: 'openTestDesignJson', kind: 'openReport', label: '正本JSON（test_spec.json）を開く', reportKey: 'testSpecJson', stepId: 'reviewTestDesign' },
      { id: 'confirmTestDesign', kind: 'confirmStep', label: '保存済みとして確定', stepId: 'reviewTestDesign' },
    ],
  },
  {
    id: 'generateHarnessSkeleton',
    title: '7. テストハーネスを生成',
    purpose: 'レビュー済みのtest_spec.jsonから、ビルドの事前確認に使用するテストハーネスを生成します。',
    requiredAction: 'test_spec.jsonの期待値とレビュー項目を保存してから、テストハーネスを生成します。',
    actions: [
      { id: 'generateHarnessSkeleton', kind: 'command', label: 'テストハーネスを生成', repeatLabel: 'テストハーネスを再生成', commandId: 'unitTestRunner.generateHarnessSkeleton', primary: true },
    ],
  },
  {
    id: 'buildProbeDryRun',
    title: '8. ビルドの事前確認',
    purpose: 'harness_skeleton_report.jsonを使用し、実際にビルドする前に生成ワークスペースとビルド手順を確認します。',
    requiredAction: 'テストハーネスの生成後に、ビルドの事前確認を実行します。',
    actions: [
      { id: 'buildProbeDryRun', kind: 'command', label: '事前確認を実行', repeatLabel: '事前確認を再実行', commandId: 'unitTestRunner.buildProbeDryRun', primary: true },
    ],
  },
  {
    id: 'reviewBuildProbe',
    title: '9. ビルド結果を確認',
    purpose: 'ビルドの事前確認結果と、未解決のビルド項目を確認します。',
    requiredAction: 'レポートを開き、必要なら編集して保存または確定します。',
    actions: [
      { id: 'openBuildProbe', kind: 'openReport', label: 'ビルド結果レポートを開く', reportKey: 'buildProbeReportMd', stepId: 'reviewBuildProbe', primary: true },
      { id: 'confirmBuildProbe', kind: 'confirmStep', label: '保存済みとして確定', stepId: 'reviewBuildProbe' },
    ],
  },
  {
    id: 'buildProbeRun',
    title: '10. ビルドを実行',
    purpose: '生成されたテストを、確認後にビルドします。',
    requiredAction: '確認ダイアログで内容を確認し、ビルドを実行します。',
    actions: [
      { id: 'runBuildProbe', kind: 'command', label: 'ビルドを実行', repeatLabel: 'ビルドを再実行', commandId: 'unitTestRunner.runBuildProbe', primary: true, danger: true },
    ],
  },
  {
    id: 'runTests',
    title: '11. テストを実行',
    purpose: '生成されたテストを、確認後に実行します。',
    requiredAction: '確認ダイアログで内容を確認し、テストを実行します。',
    actions: [
      { id: 'runTests', kind: 'command', label: 'テストを実行', repeatLabel: 'テストを再実行', commandId: 'unitTestRunner.runTests', primary: true, danger: true },
    ],
  },
  {
    id: 'prepareEvidence',
    title: '12. 検証資料を作成',
    purpose: '実行結果と定義ファイルを、レビュー用の検証資料として整理します。',
    requiredAction: '［検証資料を作成］を実行します。',
    actions: [
      { id: 'prepareEvidence', kind: 'command', label: '検証資料を作成', repeatLabel: '検証資料を再作成', commandId: 'unitTestRunner.prepareEvidence', primary: true },
    ],
  },
  {
    id: 'reviewEvidence',
    title: '13. 実行結果と検証資料を確認',
    purpose: 'テスト実行レポートと検証資料を確認します。',
    requiredAction: '実行結果と検証資料を開き、内容を確認して保存します。',
    actions: [
      { id: 'openTestExecution', kind: 'openReport', label: 'テスト実行レポートを開く', reportKey: 'testExecutionReportMd', stepId: 'reviewEvidence', primary: true },
      { id: 'openEvidencePackage', kind: 'openReport', label: '検証資料を開く', reportKey: 'evidencePackageMd', stepId: 'reviewEvidence' },
      { id: 'confirmEvidence', kind: 'confirmStep', label: '保存済みとして確定', stepId: 'reviewEvidence' },
    ],
  },
  {
    id: 'complete',
    title: '14. 完了',
    purpose: '関数分析レポート、テスト実行、検証資料の確認が完了しています。',
    requiredAction: '必要に応じて出力ワークスペースを開くか、次の関数のテストへ進みます。',
    actions: [
      { id: 'openOutputWorkspace', kind: 'openOutputWorkspace', label: '出力ワークスペースを開く', primary: true },
      { id: 'copyLastCommand', kind: 'copyLastCommand', label: '最後に実行したCLIコマンドをコピー' },
    ],
  },
];

export const OPTIONAL_WORKFLOW_ACTIONS: WorkflowAction[] = [
  { id: 'reanalyzeCurrent', kind: 'command', label: '変更後の関数を再解析', commandId: 'unitTestRunner.reanalyzeCurrentFunction', primary: true },
  { id: 'openChangeImpact', kind: 'openReport', label: '変更影響を開く', reportKey: 'changeImpactReportMd' },
  { id: 'openRegressionSelection', kind: 'openReport', label: '回帰テストの選定結果を開く', reportKey: 'regressionSelectionCsv' },
  { id: 'openOutputWorkspace', kind: 'openOutputWorkspace', label: '出力ワークスペースを開く' },
  { id: 'copyLastCommand', kind: 'copyLastCommand', label: '最後に実行したCLIコマンドをコピー' },
];

const COMMAND_STEP_MAP: Record<WorkflowCommandKind, WorkflowStepId | undefined> = {
  analyze: 'analyze',
  finalize: 'analyze',
  testDesign: 'generateTestDesign',
  harness: 'generateHarnessSkeleton',
  buildProbeDryRun: 'buildProbeDryRun',
  buildProbeRun: 'buildProbeRun',
  runTests: 'runTests',
  evidence: 'prepareEvidence',
  reanalyze: undefined,
};

export function createInitialWorkflowState(settingsReady = false): WorkflowState {
  return {
    settingsReady,
    completedStepIds: settingsReady ? ['settings'] : [],
  };
}

export function markWorkflowCommandSucceeded(state: WorkflowState, event: WorkflowCommandSuccess): WorkflowState {
  const workspaceChanged = !!event.outputWorkspace && event.outputWorkspace !== state.outputWorkspace;
  const completed = new Set<WorkflowStepId>(workspaceChanged ? [] : state.completedStepIds);
  completed.add('settings');
  const commandStep = COMMAND_STEP_MAP[event.kind];
  if (commandStep) {
    completed.add(commandStep);
  }
  const reports = mergeReports(workspaceChanged ? undefined : state.reports, event.reports, event.outputWorkspace);
  return {
    ...state,
    settingsReady: true,
    outputWorkspace: event.outputWorkspace ?? state.outputWorkspace,
    functionName: event.functionName ?? state.functionName,
    reports,
    completedStepIds: Array.from(completed),
    awaitingSave: undefined,
    lastError: undefined,
    testInputSummary: workspaceChanged ? undefined : state.testInputSummary,
    updatedAt: timestamp(),
  };
}

export function markWorkflowCommandFailed(state: WorkflowState, message: string): WorkflowState {
  return {
    ...state,
    lastError: message,
    updatedAt: timestamp(),
  };
}

export function setWorkflowSettingsReady(state: WorkflowState, settingsReady: boolean): WorkflowState {
  const completed = new Set<WorkflowStepId>(state.completedStepIds);
  if (settingsReady) {
    completed.add('settings');
  } else {
    completed.delete('settings');
  }
  return {
    ...state,
    settingsReady,
    completedStepIds: Array.from(completed),
    updatedAt: timestamp(),
  };
}

export function markStepAwaitingSave(state: WorkflowState, stepId: WorkflowStepId, filePath: string, reportKey?: keyof ReportPaths): WorkflowState {
  return {
    ...state,
    awaitingSave: {
      stepId,
      filePath,
      reportKey,
      startedAt: timestamp(),
    },
    updatedAt: timestamp(),
  };
}

export function completeWorkflowStep(state: WorkflowState, stepId: WorkflowStepId): WorkflowState {
  const completed = new Set<WorkflowStepId>(state.completedStepIds);
  completed.add(stepId);
  return {
    ...state,
    completedStepIds: Array.from(completed),
    awaitingSave: state.awaitingSave?.stepId === stepId ? undefined : state.awaitingSave,
    lastError: undefined,
    updatedAt: timestamp(),
  };
}

export function completeAwaitingSaveIfMatches(state: WorkflowState, savedPath: string): { state: WorkflowState; matched: boolean } {
  if (!state.awaitingSave || !sameFile(state.awaitingSave.filePath, savedPath)) {
    return { state, matched: false };
  }
  return { state: completeWorkflowStep(state, state.awaitingSave.stepId), matched: true };
}

export function reportAvailabilityFromPaths(reports: Partial<ReportPaths> | undefined, exists: (filePath: string) => boolean): WorkflowReportAvailability {
  return {
    functionDossier: reportExists(reports, 'functionDossierMd', exists),
    reviewChecklist: reportExists(reports, 'reviewChecklistMd', exists),
    unresolvedItems: reportExists(reports, 'unresolvedItemsMd', exists),
    nextActions: reportExists(reports, 'nextActionsMd', exists),
    testCaseDesign: reportExists(reports, 'testSpecJson', exists),
    harnessSkeletonReport: reportExists(reports, 'harnessSkeletonReportJson', exists),
    buildProbeReport: reportExists(reports, 'buildProbeReportMd', exists),
    testExecutionReport: reportExists(reports, 'testExecutionReportMd', exists),
    evidencePackage: reportExists(reports, 'evidencePackageMd', exists),
  };
}

export function deriveCurrentWorkflowStepId(state: WorkflowState, availability: WorkflowReportAvailability): WorkflowStepId {
  const completed = effectiveCompletedStepIds(state, availability);
  if (!state.settingsReady) {
    return 'settings';
  }
  if (state.awaitingSave && !completed.has(state.awaitingSave.stepId)) {
    return state.awaitingSave.stepId;
  }
  for (const step of WORKFLOW_STEP_DEFINITIONS) {
    if (step.id === 'settings') {
      continue;
    }
    if (!completed.has(step.id)) {
      return step.id;
    }
  }
  return 'complete';
}

export function buildWorkflowStepViews(state: WorkflowState, availability: WorkflowReportAvailability): WorkflowStepView[] {
  const current = deriveCurrentWorkflowStepId(state, availability);
  const completed = effectiveCompletedStepIds(state, availability);
  return WORKFLOW_STEP_DEFINITIONS.map((definition) => ({
    ...definition,
    status: completed.has(definition.id) && definition.id !== current ? 'done' : definition.id === current ? 'current' : 'pending',
  }));
}

export function workflowLegacyProjection(state: WorkflowState): WorkflowLegacyProjection {
  return {
    lastWorkspace: state.outputWorkspace || state.reports?.workspace,
    lastDossier: state.reports?.functionDossierMd,
  };
}

function effectiveCompletedStepIds(state: WorkflowState, availability: WorkflowReportAvailability): Set<WorkflowStepId> {
  const completed = new Set<WorkflowStepId>(state.completedStepIds);
  if (state.settingsReady) {
    completed.add('settings');
  }
  if (availability.functionDossier) {
    completed.add('analyze');
  }
  if (availability.testCaseDesign) {
    completed.add('analyze');
    completed.add('reviewDossier');
    completed.add('reviewWorkflowReports');
    completed.add('generateTestDesign');
  }
  if (availability.buildProbeReport) {
    completed.add('analyze');
    completed.add('reviewDossier');
    completed.add('reviewWorkflowReports');
    completed.add('generateTestDesign');
    completed.add('reviewTestDesign');
    completed.add('generateHarnessSkeleton');
    completed.add('buildProbeDryRun');
  }
  if (availability.harnessSkeletonReport) {
    completed.add('analyze');
    completed.add('reviewDossier');
    completed.add('reviewWorkflowReports');
    completed.add('generateTestDesign');
    completed.add('reviewTestDesign');
    completed.add('generateHarnessSkeleton');
  }
  if (availability.testExecutionReport) {
    completed.add('reviewBuildProbe');
    completed.add('buildProbeRun');
    completed.add('runTests');
  }
  if (availability.evidencePackage) {
    completed.add('reviewBuildProbe');
    completed.add('buildProbeRun');
    completed.add('runTests');
    completed.add('prepareEvidence');
  }
  return completed;
}

function reportExists(reports: Partial<ReportPaths> | undefined, key: keyof ReportPaths, exists: (filePath: string) => boolean): boolean {
  const value = reports?.[key];
  return typeof value === 'string' && value.length > 0 && exists(value);
}

function mergeReports(current: Partial<ReportPaths> | undefined, incoming: ReportPaths | undefined, outputWorkspace: string | undefined): Partial<ReportPaths> | undefined {
  if (!current && !incoming && !outputWorkspace) {
    return undefined;
  }
  return {
    ...current,
    ...incoming,
    workspace: outputWorkspace ?? incoming?.workspace ?? current?.workspace,
  };
}

function sameFile(left: string, right: string): boolean {
  return path.normalize(left).toLowerCase() === path.normalize(right).toLowerCase();
}

function timestamp(): string {
  return new Date().toISOString();
}

import * as path from 'path';

import { ReportPaths } from '../reports/reportPathResolver';

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
  updatedAt?: string;
}

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
  status: 'done' | 'current' | 'pending';
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
    purpose: 'sourceRoot、dswPath、outputRoot、CLIの利用準備を確認します。',
    requiredAction: 'VS Code設定で対象プロジェクトと外部出力workspaceを指定します。',
    actions: [
      { id: 'openSettings', kind: 'openSettings', label: '設定を開く', primary: true },
      { id: 'copyLastCommand', kind: 'copyLastCommand', label: '最後のCLIをコピー' },
    ],
  },
  {
    id: 'analyze',
    title: '2. 関数解析',
    purpose: '現在のCファイルと関数を対象にdossierを生成します。',
    requiredAction: '関数内にカーソルを置くか関数名を選択して解析します。',
    actions: [
      { id: 'analyzeCurrent', kind: 'command', label: '現在関数を解析', commandId: 'unitTestRunner.analyzeCurrentFunction', primary: true },
      { id: 'analyzeSelected', kind: 'command', label: '選択関数を解析', commandId: 'unitTestRunner.analyzeSelectedFunction' },
    ],
  },
  {
    id: 'reviewDossier',
    title: '3. function_dossier.md 確認',
    purpose: '関数概要、依存、カバレッジ、未解決事項の入口を確認します。',
    requiredAction: 'dossierを開き、必要なレビューを行って保存または確定します。',
    actions: [
      { id: 'openDossier', kind: 'openReport', label: 'dossierを開く', reportKey: 'functionDossierMd', stepId: 'reviewDossier', primary: true },
      { id: 'confirmDossier', kind: 'confirmStep', label: '保存済みとして確定', stepId: 'reviewDossier' },
    ],
  },
  {
    id: 'reviewWorkflowReports',
    title: '4. レビュー項目確認',
    purpose: 'review checklist、unresolved items、next actionsを確認します。',
    requiredAction: '未解決項目と次アクションを確認し、必要なら編集して保存します。',
    actions: [
      { id: 'openReviewChecklist', kind: 'openReport', label: '確認リストを開く', reportKey: 'reviewChecklistMd', stepId: 'reviewWorkflowReports', primary: true },
      { id: 'openUnresolvedItems', kind: 'openReport', label: '未解決項目を開く', reportKey: 'unresolvedItemsMd', stepId: 'reviewWorkflowReports' },
      { id: 'openNextActions', kind: 'openReport', label: '次のアクションを開く', reportKey: 'nextActionsMd', stepId: 'reviewWorkflowReports' },
      { id: 'confirmWorkflowReports', kind: 'confirmStep', label: '保存済みとして確定', stepId: 'reviewWorkflowReports' },
    ],
  },
  {
    id: 'generateTestDesign',
    title: '5. テスト設計生成',
    purpose: 'dossierからtest_case_designを生成します。',
    requiredAction: 'テスト設計生成コマンドを実行します。',
    actions: [
      { id: 'generateTestDesign', kind: 'command', label: 'テスト設計を生成', commandId: 'unitTestRunner.generateTestDesign', primary: true },
    ],
  },
  {
    id: 'reviewTestDesign',
    title: '6. test_case_design.csv 確認',
    purpose: '生成されたテストケース設計を確認します。CSVは一覧確認、Markdownはレビュー、JSONはハーネス生成の入力です。',
    requiredAction: 'CSV/Markdown/JSONを開き、TBD_EXPECTED_RETURNやreview_required項目を埋めて保存または確定します。',
    actions: [
      { id: 'openTestDesign', kind: 'openReport', label: 'CSVを開く', reportKey: 'testCaseDesignCsv', stepId: 'reviewTestDesign', primary: true },
      { id: 'openTestDesignMarkdown', kind: 'openReport', label: 'Markdownを開く', reportKey: 'testCaseDesignMd', stepId: 'reviewTestDesign' },
      { id: 'openTestDesignJson', kind: 'openReport', label: 'JSONを開く', reportKey: 'testCaseDesignJson', stepId: 'reviewTestDesign' },
      { id: 'confirmTestDesign', kind: 'confirmStep', label: '保存済みとして確定', stepId: 'reviewTestDesign' },
    ],
  },
  {
    id: 'generateHarnessSkeleton',
    title: '7. ハーネス生成',
    purpose: 'レビュー済みtest_case_design.jsonを使い、Build Probeの前提になるharness_skeleton_reportを生成します。',
    requiredAction: 'test_case_design.jsonの期待値とレビュー項目を保存した後に、ハーネス生成を実行します。',
    actions: [
      { id: 'generateHarnessSkeleton', kind: 'command', label: 'ハーネスを生成', commandId: 'unitTestRunner.generateHarnessSkeleton', primary: true },
    ],
  },
  {
    id: 'buildProbeDryRun',
    title: '8. ビルドプローブ dry-run',
    purpose: 'harness_skeleton_report.jsonを使い、実ビルド前に生成workspaceとbuild準備を確認します。',
    requiredAction: 'ハーネス生成が完了してから、dry-runでBuild Probeを実行します。',
    actions: [
      { id: 'buildProbeDryRun', kind: 'command', label: 'dry-runを実行', commandId: 'unitTestRunner.buildProbeDryRun', primary: true },
    ],
  },
  {
    id: 'reviewBuildProbe',
    title: '9. ビルドプローブレポート確認',
    purpose: 'ビルドプローブ結果と未解決のビルド項目を確認します。',
    requiredAction: 'レポートを開き、必要なら編集して保存または確定します。',
    actions: [
      { id: 'openBuildProbe', kind: 'openReport', label: 'ビルドレポートを開く', reportKey: 'buildProbeReportMd', stepId: 'reviewBuildProbe', primary: true },
      { id: 'confirmBuildProbe', kind: 'confirmStep', label: '保存済みとして確定', stepId: 'reviewBuildProbe' },
    ],
  },
  {
    id: 'buildProbeRun',
    title: '10. ビルドプローブ実行',
    purpose: '生成されたビルド手順を明示確認のうえ実行します。',
    requiredAction: '確認ダイアログを承認してビルドプローブを実行します。',
    actions: [
      { id: 'runBuildProbe', kind: 'command', label: 'ビルドプローブを実行', commandId: 'unitTestRunner.runBuildProbe', primary: true, danger: true },
    ],
  },
  {
    id: 'runTests',
    title: '11. 生成テスト実行',
    purpose: '生成テストを明示確認のうえ実行します。',
    requiredAction: '確認ダイアログを承認してテストを実行します。',
    actions: [
      { id: 'runTests', kind: 'command', label: 'テストを実行', commandId: 'unitTestRunner.runTests', primary: true, danger: true },
    ],
  },
  {
    id: 'prepareEvidence',
    title: '12. エビデンス準備',
    purpose: '実行結果とmanifestをレビュー用エビデンスへ整理します。',
    requiredAction: 'エビデンス準備コマンドを実行します。',
    actions: [
      { id: 'prepareEvidence', kind: 'command', label: 'エビデンスを準備', commandId: 'unitTestRunner.prepareEvidence', primary: true },
    ],
  },
  {
    id: 'reviewEvidence',
    title: '13. 実行結果・エビデンス確認',
    purpose: 'test_execution_reportとevidence_packageを確認します。',
    requiredAction: '実行結果とエビデンスを開き、保存または確定します。',
    actions: [
      { id: 'openTestExecution', kind: 'openReport', label: 'テスト実行レポートを開く', reportKey: 'testExecutionReportMd', stepId: 'reviewEvidence', primary: true },
      { id: 'openEvidencePackage', kind: 'openReport', label: 'エビデンスを開く', reportKey: 'evidencePackageMd', stepId: 'reviewEvidence' },
      { id: 'confirmEvidence', kind: 'confirmStep', label: '保存済みとして確定', stepId: 'reviewEvidence' },
    ],
  },
  {
    id: 'complete',
    title: '14. 完了',
    purpose: 'dossier、テスト実行、エビデンス確認が完了しています。',
    requiredAction: '必要に応じて出力workspaceを開くか、次の関数へ進みます。',
    actions: [
      { id: 'openOutputWorkspace', kind: 'openOutputWorkspace', label: '出力workspaceを開く', primary: true },
      { id: 'copyLastCommand', kind: 'copyLastCommand', label: '最後のCLIをコピー' },
    ],
  },
];

export const OPTIONAL_WORKFLOW_ACTIONS: WorkflowAction[] = [
  { id: 'reanalyzeCurrent', kind: 'command', label: '変更後に再解析', commandId: 'unitTestRunner.reanalyzeCurrentFunction', primary: true },
  { id: 'openChangeImpact', kind: 'openReport', label: '変更影響を開く', reportKey: 'changeImpactReportMd' },
  { id: 'openRegressionSelection', kind: 'openReport', label: '回帰選定を開く', reportKey: 'regressionSelectionCsv' },
  { id: 'openOutputWorkspace', kind: 'openOutputWorkspace', label: '出力workspaceを開く' },
  { id: 'copyLastCommand', kind: 'copyLastCommand', label: '最後のCLIをコピー' },
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
  const reports = mergeReports(state.reports, event.reports, event.outputWorkspace);
  return {
    ...state,
    settingsReady: true,
    outputWorkspace: event.outputWorkspace ?? state.outputWorkspace,
    functionName: event.functionName ?? state.functionName,
    reports,
    completedStepIds: Array.from(completed),
    awaitingSave: undefined,
    lastError: undefined,
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
    testCaseDesign: reportExists(reports, 'testCaseDesignCsv', exists),
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

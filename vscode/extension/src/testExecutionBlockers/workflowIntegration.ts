import type { ReportPaths } from '../reports/reportPathResolver';
import type { WorkflowState, WorkflowStepId } from '../workflow/workflowState';
import type { ExecutionBlockerActionCode } from './contracts';
import { restoreLatestBlockedRun, VerifiedBlockedRun } from './verification';

const BLOCKED_AND_LATER_STEPS = new Set<WorkflowStepId>([
  'runTests',
  'prepareEvidence',
  'reviewEvidence',
  'complete',
]);

export function isActualNonBlockedTestRun(
  envelope: { version: string; command?: string; outcome?: string },
  invocationArgs: readonly string[],
): boolean {
  return envelope.version === '1.0.0'
    && envelope.command === 'run-tests'
    && envelope.outcome !== undefined
    && envelope.outcome !== 'blocked'
    && invocationArgs.includes('--run')
    && !invocationArgs.includes('--plan');
}

export function restoreWorkflowBlockerState(
  state: WorkflowState,
  workspace: string,
  verifier: (workspace: string) => VerifiedBlockedRun | undefined = restoreLatestBlockedRun,
): WorkflowState {
  let verified: VerifiedBlockedRun | undefined;
  try {
    verified = verifier(workspace);
  } catch {
    verified = undefined;
  }
  return verified ? markWorkflowRunBlocked(state, verified) : clearWorkflowRunBlocked(state);
}

export function markWorkflowRunBlocked(state: WorkflowState, blocker: VerifiedBlockedRun): WorkflowState {
  const activeWorkspace = state.outputWorkspace ?? state.reports?.workspace;
  const workspaceChanged = Boolean(activeWorkspace && !sameWorkspace(activeWorkspace, blocker.workspace));
  const sameRun = !workspaceChanged && state.testExecutionBlockers?.runId === blocker.runId;
  const completedStepIds = workspaceChanged ? ['settings' as WorkflowStepId] : state.completedStepIds;
  return {
    ...state,
    settingsReady: true,
    outputWorkspace: blocker.workspace,
    reports: withBlockerReports(workspaceChanged ? undefined : state.reports, blocker),
    completedStepIds: completedStepIds.filter((item) => !BLOCKED_AND_LATER_STEPS.has(item)),
    awaitingSave: undefined,
    lastError: undefined,
    testInputSummary: workspaceChanged ? undefined : state.testInputSummary,
    testExecutionBlockers: {
      status: 'blocked',
      workspace: blocker.workspace,
      runId: blocker.runId,
      count: blocker.count,
      primaryAction: blocker.primaryAction,
      primaryActionLabel: blocker.primaryActionLabel,
      reportJson: blocker.reportJson,
      reportMarkdown: blocker.reportMarkdown,
      reportSha256: blocker.reportSha256,
      primarySourcePath: blocker.primarySourcePath,
      publicationDiagnostics: blocker.publicationDiagnostics.map((item) => `${item.code}: ${item.message}`),
      autoOpenedRunId: sameRun ? state.testExecutionBlockers?.autoOpenedRunId : undefined,
      updatedAt: blocker.updatedAt,
    },
    updatedAt: blocker.updatedAt,
  };
}

export function clearWorkflowRunBlocked(state: WorkflowState, workspace?: string): WorkflowState {
  if (
    workspace
    && state.testExecutionBlockers
    && !sameWorkspace(state.testExecutionBlockers.workspace, workspace)
  ) {
    return state;
  }
  const reports = stripBlockerReports(state.reports);
  if (!state.testExecutionBlockers && reports === state.reports) {
    return state;
  }
  return {
    ...state,
    reports,
    testExecutionBlockers: undefined,
    updatedAt: new Date().toISOString(),
  };
}

export function markWorkflowBlockerAutoOpened(state: WorkflowState, runId: string): WorkflowState {
  if (!state.testExecutionBlockers || state.testExecutionBlockers.runId !== runId) {
    return state;
  }
  return {
    ...state,
    testExecutionBlockers: {
      ...state.testExecutionBlockers,
      autoOpenedRunId: runId,
    },
    updatedAt: new Date().toISOString(),
  };
}

export type BlockerPrimaryActionTarget =
  | { kind: 'command'; commandId: string }
  | { kind: 'report'; reportKey: keyof ReportPaths }
  | { kind: 'path' };

export function blockerPrimaryActionTarget(code: ExecutionBlockerActionCode): BlockerPrimaryActionTarget {
  const targets: Record<ExecutionBlockerActionCode, BlockerPrimaryActionTarget> = {
    open_test_input_editor: { kind: 'command', commandId: 'unitTestRunner.openTestInputEditor' },
    open_build_probe_report: { kind: 'report', reportKey: 'buildProbeReportMd' },
    generate_harness: { kind: 'command', commandId: 'unitTestRunner.generateHarnessSkeleton' },
    run_build_probe: { kind: 'command', commandId: 'unitTestRunner.runBuildProbe' },
    choose_or_build_executable: { kind: 'command', commandId: 'unitTestRunner.runBuildProbe' },
    open_execution_log: { kind: 'path' },
    open_execution_report: { kind: 'path' },
  };
  return targets[code];
}

function withBlockerReports(
  current: Partial<ReportPaths> | undefined,
  blocker: VerifiedBlockedRun,
): Partial<ReportPaths> {
  const reports = stripBlockerReports(current) ?? {};
  return {
    ...reports,
    workspace: blocker.workspace,
    ...(blocker.reportJson ? { testExecutionBlockersJson: blocker.reportJson } : {}),
    ...(blocker.reportMarkdown ? { testExecutionBlockersMd: blocker.reportMarkdown } : {}),
  };
}

function stripBlockerReports(reports: Partial<ReportPaths> | undefined): Partial<ReportPaths> | undefined {
  if (!reports) {
    return undefined;
  }
  const {
    testExecutionBlockersJson: _json,
    testExecutionBlockersMd: _markdown,
    ...rest
  } = reports;
  if (_json === undefined && _markdown === undefined) {
    return reports;
  }
  return rest;
}

function sameWorkspace(left: string, right: string): boolean {
  return left.replace(/\\/g, '/').toLowerCase() === right.replace(/\\/g, '/').toLowerCase();
}

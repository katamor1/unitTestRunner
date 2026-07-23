import type { CliDiagnostic, ParsedCliEnvelope } from '../cli/cliEnvelope';

export type ExecutionBlockerActionCode =
  | 'open_test_input_editor'
  | 'open_build_probe_report'
  | 'generate_harness'
  | 'run_build_probe'
  | 'choose_or_build_executable'
  | 'open_execution_log'
  | 'open_execution_report';

export interface HandledBlockedRunDetails {
  runId: string;
  count: number;
  primaryAction: ExecutionBlockerActionCode;
  primaryActionLabel: string;
  runJson?: string;
  runMarkdown?: string;
  latestJson?: string;
  latestMarkdown?: string;
  publicationDiagnostics: CliDiagnostic[];
}

const ACTION_CODES = new Set<ExecutionBlockerActionCode>([
  'open_test_input_editor',
  'open_build_probe_report',
  'generate_harness',
  'run_build_probe',
  'choose_or_build_executable',
  'open_execution_log',
  'open_execution_report',
]);

export function parseHandledBlockedRun(
  envelope: ParsedCliEnvelope,
  processExitCode: number | null,
  invocationArgs: readonly string[],
): HandledBlockedRunDetails | undefined {
  if (
    processExitCode !== 35
    || envelope.version !== '1.0.0'
    || envelope.command !== 'run-tests'
    || envelope.outcome !== 'blocked'
    || envelope.exitCode !== 35
    || !invocationArgs.includes('--run')
    || invocationArgs.includes('--plan')
  ) {
    return undefined;
  }
  const execution = record(envelope.details.test_execution, 'test_execution');
  if (execution.status !== 'blocked') {
    throw new Error('Blocked CLI result has a non-blocked execution status.');
  }
  const runId = nonEmptyString(execution.run_id, 'test_execution.run_id');
  const publicationDiagnostics = envelope.diagnostics.filter((item) => item.code.startsWith('blocker_'));
  const rawBlockers = envelope.details.blockers;
  if (rawBlockers === undefined && publicationDiagnostics.length > 0) {
    return {
      runId,
      count: 0,
      primaryAction: 'open_execution_report',
      primaryActionLabel: 'テスト実行レポートを開く',
      publicationDiagnostics,
    };
  }
  const blockers = record(rawBlockers, 'blockers');
  return {
    runId,
    count: positiveInteger(blockers.count, 'blockers.count'),
    primaryAction: actionCode(blockers.primary_action),
    primaryActionLabel: nonEmptyString(blockers.primary_action_label, 'blockers.primary_action_label'),
    runJson: optionalBlockerPath(blockers.run_json, 'blockers.run_json'),
    runMarkdown: optionalBlockerPath(blockers.run_markdown, 'blockers.run_markdown'),
    latestJson: optionalBlockerPath(blockers.latest_json, 'blockers.latest_json'),
    latestMarkdown: optionalBlockerPath(blockers.latest_markdown, 'blockers.latest_markdown'),
    publicationDiagnostics,
  };
}

function record(value: unknown, name: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`Blocked CLI result is missing ${name}.`);
  }
  return value as Record<string, unknown>;
}

function nonEmptyString(value: unknown, name: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`Blocked CLI result has invalid ${name}.`);
  }
  return value;
}

function positiveInteger(value: unknown, name: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 1) {
    throw new Error(`Blocked CLI result has invalid ${name}.`);
  }
  return value;
}

function actionCode(value: unknown): ExecutionBlockerActionCode {
  if (typeof value !== 'string' || !ACTION_CODES.has(value as ExecutionBlockerActionCode)) {
    throw new Error('Blocked CLI result has an invalid primary action.');
  }
  return value as ExecutionBlockerActionCode;
}

function optionalBlockerPath(value: unknown, name: string): string | undefined {
  if (value === undefined) {
    return undefined;
  }
  if (typeof value !== 'string' || !contractPath(value)) {
    throw new Error(`Invalid blocker path at ${name}.`);
  }
  return value;
}

function contractPath(value: string): boolean {
  return value.length > 0
    && !value.includes('\\')
    && !value.startsWith('/')
    && !/^[A-Za-z]:/.test(value)
    && value.split('/').every((part) => part.length > 0 && part !== '.' && part !== '..');
}

export type CliRunOutcome =
  | 'planned'
  | 'passed'
  | 'failed'
  | 'blocked'
  | 'timed_out'
  | 'cancelled'
  | 'error';

export interface CliProducedArtifact {
  artifactKind: string;
  path: string;
  sha256: string;
}

export interface ParsedCliEnvelope {
  command: string;
  outcome: CliRunOutcome;
  message: string;
  producedArtifacts: CliProducedArtifact[];
  diagnostics: Array<{ code: string; level: 'info' | 'warning' | 'error'; message: string }>;
  raw: Record<string, unknown>;
}

const RUN_OUTCOMES = new Set<CliRunOutcome>([
  'planned', 'passed', 'failed', 'blocked', 'timed_out', 'cancelled', 'error',
]);
const ARTIFACT_KINDS = new Set([
  'function_dossier', 'test_spec', 'review_record', 'build_probe_report',
  'test_run_report', 'reanalysis_report', 'suite_manifest', 'suite_run_report',
]);
const DIAGNOSTIC_LEVELS = new Set(['info', 'warning', 'error']);
const SHA256 = /^[0-9a-f]{64}$/;

export function parseCliEnvelopeValue(value: unknown): ParsedCliEnvelope {
  if (!isRecord(value)
    || !hasExactKeys(value, ['command', 'outcome', 'message', 'artifacts', 'diagnostics'])
    || !nonEmptyString(value.command)
    || !RUN_OUTCOMES.has(value.outcome as CliRunOutcome)
    || !nonEmptyString(value.message)
    || !Array.isArray(value.artifacts)
    || !Array.isArray(value.diagnostics)) {
    throw new Error('Malformed v0.1 CLI envelope.');
  }
  const producedArtifacts = value.artifacts.map(parseArtifact);
  const diagnostics = value.diagnostics.map(parseDiagnostic);
  const outcome = value.outcome as CliRunOutcome;
  return {
    command: value.command,
    outcome,
    message: value.message,
    producedArtifacts,
    diagnostics,
    raw: value,
  };
}

function parseArtifact(value: unknown): CliProducedArtifact {
  if (!isRecord(value)
    || !hasExactKeys(value, ['kind', 'path', 'sha256'])
    || !ARTIFACT_KINDS.has(String(value.kind))
    || !contractPath(value.path)
    || typeof value.sha256 !== 'string'
    || !SHA256.test(value.sha256)) {
    throw new Error('Malformed v0.1 CLI envelope: invalid artifact.');
  }
  return { artifactKind: String(value.kind), path: value.path, sha256: value.sha256 };
}

function parseDiagnostic(value: unknown): { code: string; level: 'info' | 'warning' | 'error'; message: string } {
  if (!isRecord(value)
    || !hasExactKeys(value, ['code', 'level', 'message'])
    || !nonEmptyString(value.code)
    || !DIAGNOSTIC_LEVELS.has(String(value.level))
    || typeof value.message !== 'string') {
    throw new Error('Malformed v0.1 CLI envelope: invalid diagnostic.');
  }
  return { code: value.code, level: value.level as 'info' | 'warning' | 'error', message: value.message };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

function hasExactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  const keys = Object.keys(value).sort();
  return keys.length === expected.length && keys.every((key, index) => key === [...expected].sort()[index]);
}

function contractPath(value: unknown): value is string {
  if (!nonEmptyString(value) || value.includes('\\') || value.startsWith('/') || /^[A-Za-z]:/.test(value)) {
    return false;
  }
  return value.split('/').every((part) => part.length > 0 && part !== '.' && part !== '..');
}

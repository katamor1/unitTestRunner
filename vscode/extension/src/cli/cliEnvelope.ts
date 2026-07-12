export type CliRunOutcome =
  | 'planned'
  | 'passed'
  | 'failed'
  | 'blocked'
  | 'inconclusive'
  | 'cancelled'
  | 'timed_out'
  | 'error';

export interface CliProducedArtifact {
  artifactKind: string;
  path: string;
  exists: true;
  sha256: string;
  schemaVersion: string | null;
}

export interface CliExpectedArtifact {
  artifactKind: string;
  path: string;
}

export interface ParsedCliEnvelope {
  version: '1.0.0' | '0.1';
  outcome?: CliRunOutcome;
  exitCode: number;
  producedArtifacts: CliProducedArtifact[];
  expectedArtifacts: CliExpectedArtifact[];
  reportedPaths: Record<string, string>;
  warnings: string[];
  raw: Record<string, unknown>;
}

const RUN_OUTCOMES = new Set<CliRunOutcome>([
  'planned',
  'passed',
  'failed',
  'blocked',
  'inconclusive',
  'cancelled',
  'timed_out',
  'error',
]);
const LIFECYCLES = new Set(['queued', 'running', 'finished']);
const DIAGNOSTIC_SEVERITIES = new Set(['info', 'warning', 'error']);
const SHA256 = /^[0-9a-f]{64}$/;
const SCHEMA_VERSION = /^[0-9]+\.[0-9]+(?:\.[0-9]+)?$/;


export function parseCliEnvelopeValue(value: unknown): ParsedCliEnvelope {
  if (!isRecord(value)) {
    throw new Error('CLI envelope must be a JSON object.');
  }
  if (value.artifact_kind === 'cli_result') {
    const version = stringValue(value.schema_version);
    if (version !== '1.0.0') {
      throw new Error(`Unsupported CLI envelope version: ${version ?? '<missing>'}`);
    }
    return parseV1(value);
  }
  const version = value.schema_version;
  if (version !== '0.1') {
    throw new Error(`Unsupported CLI envelope version: ${version === undefined ? '<missing>' : String(version)}`);
  }
  return parseLegacy(value);
}


function parseV1(raw: Record<string, unknown>): ParsedCliEnvelope {
  const producer = requiredRecord(raw.producer);
  const subject = requiredRecord(raw.subject);
  const data = requiredRecord(raw.data);
  const extensions = requiredRecord(raw.extensions);
  const malformed = (): never => {
    throw new Error('Malformed v1 CLI envelope.');
  };
  if (
    !hasOnlyKeys(raw, ['artifact_kind', 'schema_version', 'producer', 'subject', 'data', 'extensions'])
    || !hasOnlyKeys(producer, ['name', 'version', 'commit'])
    || !nonEmptyString(producer.name)
    || !nonEmptyString(producer.version)
    || !nonEmptyString(producer.commit)
    || !hasOnlyKeys(subject, ['invocation_id'])
    || !nonEmptyString(subject.invocation_id)
    || !hasOnlyKeys(data, [
      'invocation_id',
      'command',
      'lifecycle',
      'outcome_kind',
      'outcome',
      'green',
      'exit_code',
      'message',
      'diagnostics',
      'artifacts',
      'expected_artifacts',
      'errors',
      'details',
    ])
    || !nonEmptyString(data.invocation_id)
    || data.invocation_id !== subject.invocation_id
    || !nonEmptyString(data.command)
    || !LIFECYCLES.has(String(data.lifecycle))
    || !nonEmptyString(data.outcome_kind)
    || !RUN_OUTCOMES.has(data.outcome as CliRunOutcome)
    || (data.green !== null && typeof data.green !== 'boolean')
    || !nonNegativeInteger(data.exit_code)
    || typeof data.message !== 'string'
    || !Array.isArray(data.diagnostics)
    || !Array.isArray(data.artifacts)
    || !Array.isArray(data.expected_artifacts)
    || !Array.isArray(data.errors)
    || !isRecord(data.details)
    || !isRecord(extensions)
  ) {
    return malformed();
  }

  const diagnostics = data.diagnostics.map(parseDiagnostic);
  const producedArtifacts = data.artifacts.map(parseProducedArtifact);
  const expectedArtifacts = data.expected_artifacts.map(parseExpectedArtifact);
  data.errors.forEach(parseError);
  const outcome = data.outcome as CliRunOutcome;
  if (data.outcome_kind === 'test_run' || data.outcome_kind === 'suite_run') {
    const exitByOutcome: Record<CliRunOutcome, number> = {
      planned: 0,
      passed: 0,
      failed: 32,
      inconclusive: 33,
      timed_out: 34,
      blocked: 35,
      cancelled: 36,
      error: 10,
    };
    const expectedGreen = outcome === 'planned' ? null : outcome === 'passed';
    if (data.exit_code !== exitByOutcome[outcome] || data.green !== expectedGreen) {
      return malformed();
    }
  }
  return {
    version: '1.0.0',
    outcome,
    exitCode: data.exit_code as number,
    producedArtifacts,
    expectedArtifacts,
    reportedPaths: reportPathsFromArtifacts(producedArtifacts),
    warnings: diagnostics
      .filter((item) => item.severity === 'warning')
      .map((item) => item.message),
    raw,
  };
}


function parseLegacy(raw: Record<string, unknown>): ParsedCliEnvelope {
  if (
    !nonEmptyString(raw.status)
    || !nonEmptyString(raw.command)
    || !nonNegativeInteger(raw.exit_code)
    || !isRecord(raw.data)
    || !Array.isArray(raw.warnings)
    || !Array.isArray(raw.errors)
  ) {
    throw new Error('Malformed v0.1 CLI envelope.');
  }
  const data = raw.data;
  const review = isRecord(data.review) ? data.review : {};
  const source = firstRecord(raw.reports, data.reports, review.reports);
  const reportedPaths: Record<string, string> = {};
  if (source) {
    for (const [key, path] of Object.entries(source)) {
      if (typeof path === 'string' && path.length > 0) {
        reportedPaths[key] = path;
      }
    }
  }
  const warnings = raw.warnings.filter((item): item is string => typeof item === 'string');
  warnings.unshift('CLI v0.1 compatibility mode: migrate the CLI to the v1 envelope.');
  return {
    version: '0.1',
    exitCode: raw.exit_code as number,
    producedArtifacts: [],
    expectedArtifacts: [],
    reportedPaths,
    warnings,
    raw,
  };
}


function parseProducedArtifact(value: unknown): CliProducedArtifact {
  if (!isRecord(value)
    || !hasOnlyKeys(value, ['artifact_kind', 'path', 'exists', 'sha256', 'schema_version'])
    || !nonEmptyString(value.artifact_kind)
    || !contractPath(value.path)
    || value.exists !== true
    || typeof value.sha256 !== 'string'
    || !SHA256.test(value.sha256)
    || (value.schema_version !== null
      && (typeof value.schema_version !== 'string' || !SCHEMA_VERSION.test(value.schema_version)))) {
    throw new Error('Malformed v1 CLI envelope: invalid produced artifact.');
  }
  return {
    artifactKind: value.artifact_kind,
    path: value.path,
    exists: true,
    sha256: value.sha256,
    schemaVersion: value.schema_version as string | null,
  };
}


function parseExpectedArtifact(value: unknown): CliExpectedArtifact {
  if (!isRecord(value)
    || !hasOnlyKeys(value, ['artifact_kind', 'path'])
    || !nonEmptyString(value.artifact_kind)
    || !contractPath(value.path)) {
    throw new Error('Malformed v1 CLI envelope: invalid expected artifact.');
  }
  return { artifactKind: value.artifact_kind, path: value.path };
}


function parseDiagnostic(value: unknown): { code: string; severity: string; message: string } {
  if (!isRecord(value)
    || !hasOnlyKeys(value, ['code', 'severity', 'message'])
    || !nonEmptyString(value.code)
    || !DIAGNOSTIC_SEVERITIES.has(String(value.severity))
    || typeof value.message !== 'string') {
    throw new Error('Malformed v1 CLI envelope: invalid diagnostic.');
  }
  return { code: value.code, severity: String(value.severity), message: value.message };
}


function parseError(value: unknown): void {
  if (!isRecord(value)
    || !hasOnlyKeys(value, ['code', 'message'])
    || !nonEmptyString(value.code)
    || typeof value.message !== 'string') {
    throw new Error('Malformed v1 CLI envelope: invalid error.');
  }
}


function reportPathsFromArtifacts(artifacts: CliProducedArtifact[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const artifact of artifacts) {
    const name = artifact.path.split('/').pop() ?? '';
    const key = reportKeyForArtifact(artifact, name);
    if (key) {
      result[key] = artifact.path;
    }
  }
  return result;
}


function reportKeyForArtifact(artifact: CliProducedArtifact, name: string): string | undefined {
  const extension = name.includes('.') ? name.slice(name.lastIndexOf('.')).toLowerCase() : '';
  if (artifact.artifactKind === 'function_dossier' && extension === '.md') {
    return 'function_dossier_md';
  }
  return REPORT_KEY_BY_FILENAME[name];
}


const REPORT_KEY_BY_FILENAME: Record<string, string> = {
  'function_dossier.md': 'function_dossier_md',
  'review_checklist.md': 'review_checklist',
  'unresolved_items.md': 'unresolved_items',
  'next_actions.md': 'next_actions',
  'quick_summary.json': 'quick_summary_json',
  'quick_summary.md': 'quick_summary_md',
  'test_case_design.json': 'test_case_design_json',
  'test_case_design.md': 'test_case_design_md',
  'test_case_design.csv': 'test_case_design_csv',
  'function_signature.json': 'function_signature_json',
  'global_access.json': 'global_access_json',
  'call_report.json': 'call_report_json',
  'harness_skeleton_report.json': 'harness_skeleton_report_json',
  'harness_skeleton_report.md': 'harness_skeleton_report_md',
  'build_probe_report.md': 'build_probe_report_md',
  'test_execution_report.md': 'test_execution_report_md',
  'evidence_package.md': 'evidence_package_md',
  'change_impact_report.md': 'change_impact_report_md',
  'test_case_reconciliation_report.md': 'test_case_reconciliation_report_md',
  'regression_selection.csv': 'regression_selection_csv',
};


function requiredRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}


function firstRecord(...values: unknown[]): Record<string, unknown> | undefined {
  return values.find(isRecord) as Record<string, unknown> | undefined;
}


function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}


function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}


function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}


function nonNegativeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}


function hasOnlyKeys(value: Record<string, unknown>, allowed: string[]): boolean {
  const allowedKeys = new Set(allowed);
  return Object.keys(value).every((key) => allowedKeys.has(key))
    && allowed.every((key) => Object.prototype.hasOwnProperty.call(value, key));
}


function contractPath(value: unknown): value is string {
  if (!nonEmptyString(value) || value.includes('\\') || value.startsWith('/') || /^[A-Za-z]:/.test(value)) {
    return false;
  }
  return value.split('/').every((part) => part.length > 0 && part !== '..');
}

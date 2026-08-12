import { resolveReportedPath } from '../platform/pathDialect';
import { ReportPaths } from '../reports/reportPathResolver';
import { CliProducedArtifact, parseCliEnvelopeValue } from './cliEnvelope';

export interface ParsedCliResult {
  status: string;
  parsedJson: Record<string, unknown>;
  artifacts: CliProducedArtifact[];
  reports: ReportPaths;
  warnings: string[];
}

export function parseCliResultReportPaths(stdout: string, stderr: string, workspace: string): ReportPaths {
  return parseCliResult(stdout, stderr, workspace).reports;
}

export function formatCliFailureMessage(stdout: string, stderr: string, exitCode: number | null): string {
  const prefix = `UnitTestRunner CLIが終了コード ${exitCode ?? '不明'} で終了しました。`;
  try {
    const envelope = parseCliEnvelopeValue(JSON.parse(stdout) as unknown);
    const details = envelope.diagnostics
      .filter((item) => item.level === 'error')
      .map((item) => item.message);
    if (envelope.message && !details.includes(envelope.message)) {
      details.push(envelope.message);
    }
    return `${prefix} ${[`${envelope.command} / ${envelope.outcome}`, ...details].join(': ')}`;
  } catch {
    return stderr.trim() ? `${prefix} ${stderr.trim()}` : prefix;
  }
}

export function parseCliResult(stdout: string, stderr: string, workspace: string): ParsedCliResult {
  let value: unknown;
  try {
    value = JSON.parse(stdout) as unknown;
  } catch {
    throw new Error('CLI success response must be a JSON envelope.');
  }
  const envelope = parseCliEnvelopeValue(value);
  const warnings = envelope.diagnostics
    .filter((item) => item.level === 'warning')
    .map((item) => item.message);
  if (stderr.trim()) {
    warnings.push(stderr.trim());
  }
  return {
    status: envelope.outcome,
    parsedJson: envelope.raw,
    artifacts: envelope.producedArtifacts,
    reports: reportsFromArtifacts(envelope.producedArtifacts, workspace),
    warnings,
  };
}

export function parseValidatedCliSuccess(
  stdout: string,
  stderr: string,
  workspace: string,
  allowPlanned: boolean,
): ParsedCliResult {
  const parsed = parseCliResult(stdout, stderr, workspace);
  if (parsed.status === 'passed' || (allowPlanned && parsed.status === 'planned')) {
    return parsed;
  }
  throw new Error(`CLI outcome ${parsed.status} cannot advance the workflow.`);
}

function reportsFromArtifacts(
  artifacts: Array<{ artifactKind: string; path: string }>,
  workspace: string,
): ReportPaths {
  const reports: ReportPaths = { workspace };
  const resolve = (value: string): string => resolveReportedPath(value, workspace);
  const sibling = (value: string, extension: string): string => value.replace(/\.json$/i, extension);
  for (const artifact of artifacts) {
    const jsonPath = resolve(artifact.path);
    switch (artifact.artifactKind) {
      case 'function_dossier':
        reports.functionDossierJson = jsonPath;
        reports.functionDossierMd = resolve(sibling(artifact.path, '.md'));
        break;
      case 'test_spec':
        reports.testSpecJson = jsonPath;
        reports.testSpecMd = resolve(sibling(artifact.path, '.md'));
        reports.testSpecCsv = resolve(sibling(artifact.path, '.csv'));
        break;
      case 'review_record':
        reports.reviewRecordJson = jsonPath;
        break;
      case 'build_probe_report':
        reports.buildProbeReportJson = jsonPath;
        reports.buildProbeReportMd = resolve(sibling(artifact.path, '.md'));
        break;
      case 'test_run_report':
        reports.testRunReportJson = jsonPath;
        reports.testRunReportMd = resolve(sibling(artifact.path, '.md'));
        break;
      case 'reanalysis_report':
        reports.reanalysisReportJson = jsonPath;
        reports.reanalysisReportMd = resolve(sibling(artifact.path, '.md'));
        break;
      case 'suite_manifest':
        reports.suiteManifestJson = jsonPath;
        break;
      case 'suite_run_report':
        reports.suiteRunReportJson = jsonPath;
        reports.suiteRunReportMd = resolve(sibling(artifact.path, '.md'));
        break;
    }
  }
  return reports;
}

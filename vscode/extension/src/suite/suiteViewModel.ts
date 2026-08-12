import * as fs from 'fs';
import * as path from 'path';

export const SUITE_SELECTION_KEY = 'unitTestRunner.suiteSelection';

export interface SuiteRunSummaryView {
  total: number;
  green: number;
  notGreen: number;
  executed: number;
  failed: number;
}

export interface SuiteEntryView {
  entryId: string;
  enabled: boolean;
  selected: boolean;
  tags: string[];
  functionName: string;
  source: string;
  project: string;
  configuration: string;
  workspace: string;
  lastRunStatus: string;
  greenStatus: string;
  executed: boolean;
  totalTests: number;
  passedTests: number;
  failedTests: number;
  inconclusiveTests: number;
  unresolvedReviewCount: number;
  error: string;
}

export interface SuiteViewModel {
  suitePath: string;
  reportPath: string;
  reportExists: boolean;
  lastRunStatus: string;
  lastError?: string;
  summary: SuiteRunSummaryView;
  entries: SuiteEntryView[];
}

interface ManifestEntry {
  entry_id?: unknown;
  enabled?: unknown;
  tags?: unknown;
  subject?: unknown;
  workspace?: unknown;
}

interface SuiteRunResult {
  entry_id?: unknown;
  outcome?: unknown;
  green_status?: unknown;
  executed?: unknown;
  total_tests?: unknown;
  passed_tests?: unknown;
  failed_tests?: unknown;
  inconclusive_tests?: unknown;
  unresolved_review_count?: unknown;
  error?: unknown;
}

export function suiteRunReportJsonPath(suitePath: string): string {
  return path.join(path.dirname(suitePath), 'reports', 'suite_run_report.json');
}

export function suiteRunReportMarkdownPath(suitePath: string): string {
  return path.join(path.dirname(suitePath), 'reports', 'suite_run_report.md');
}

export function readSuiteViewModel(suitePath: string, selected: Set<string>, lastError?: string): SuiteViewModel {
  const reportPath = suiteRunReportJsonPath(suitePath);
  const manifest = readPublicData(suitePath, 'suite_manifest');
  const report = readPublicData(reportPath, 'suite_run_report');
  const results = new Map(
    arrayValue(report.results)
      .map((item) => objectValue(item) as SuiteRunResult)
      .map((item) => [stringValue(item.entry_id), item] as const)
      .filter(([entryId]) => entryId.length > 0),
  );
  const entries = arrayValue(manifest.entries).map((item) => buildEntryView(objectValue(item) as ManifestEntry, results, selected));
  const reportExists = fs.existsSync(reportPath);
  return {
    suitePath,
    reportPath,
    reportExists,
    lastRunStatus: stringValue(report.outcome) || 'not_run',
    lastError,
    summary: summaryView(objectValue(report.summary), reportExists ? entries.length : 0),
    entries,
  };
}

function buildEntryView(entry: ManifestEntry, results: Map<string, SuiteRunResult>, selected: Set<string>): SuiteEntryView {
  const entryId = stringValue(entry.entry_id);
  const functionPayload = objectValue(entry.subject);
  const result = results.get(entryId);
  return {
    entryId,
    enabled: entry.enabled !== false,
    selected: selected.has(entryId),
    tags: arrayValue(entry.tags).map((item) => stringValue(item)).filter((item) => item.length > 0),
    functionName: stringValue(functionPayload.function) || entryId,
    source: stringValue(functionPayload.source_path),
    project: stringValue(functionPayload.project),
    configuration: stringValue(functionPayload.configuration),
    workspace: stringValue(entry.workspace),
    lastRunStatus: result ? stringValue(result.outcome) || 'unknown' : 'not_run',
    greenStatus: result ? stringValue(result.green_status) || 'not_green' : 'not_run',
    executed: result ? Boolean(result.executed) : false,
    totalTests: numberValue(result?.total_tests),
    passedTests: numberValue(result?.passed_tests),
    failedTests: numberValue(result?.failed_tests),
    inconclusiveTests: numberValue(result?.inconclusive_tests),
    unresolvedReviewCount: numberValue(result?.unresolved_review_count),
    error: result ? stringValue(result.error) : '',
  };
}

export function readSuiteManifestRevision(suitePath: string): number {
  if (!suitePath || !fs.existsSync(suitePath)) {
    return 0;
  }
  const envelope = readJsonObject(suitePath);
  if (envelope.schema_version !== '1.0.0' || envelope.artifact_kind !== 'suite_manifest') {
    throw new Error('スイート定義は v0.1 の suite_manifest として再生成してください。');
  }
  const revision = objectValue(envelope.data).revision;
  if (!Number.isInteger(revision) || Number(revision) < 1) {
    throw new Error('スイート定義の revision が不正です。');
  }
  return Number(revision);
}

function readPublicData(filePath: string, artifactKind: string): Record<string, unknown> {
  if (!filePath || !fs.existsSync(filePath)) {
    return {};
  }
  const envelope = readJsonObject(filePath);
  if (envelope.schema_version !== '1.0.0' || envelope.artifact_kind !== artifactKind) {
    return {};
  }
  return objectValue(envelope.data);
}

function summaryView(summary: Record<string, unknown>, fallbackTotal: number): SuiteRunSummaryView {
  const nonPassed =
    numberValue(summary.failed)
    + numberValue(summary.blocked)
    + numberValue(summary.timed_out)
    + numberValue(summary.cancelled)
    + numberValue(summary.error);
  return {
    total: numberValue(summary.total, fallbackTotal),
    green: numberValue(summary.green),
    notGreen: numberValue(summary.not_green),
    executed: numberValue(summary.executed),
    failed: nonPassed,
  };
}

function readJsonObject(filePath: string): Record<string, unknown> {
  if (!filePath || !fs.existsSync(filePath)) {
    return {};
  }
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, 'utf-8')) as unknown;
    return objectValue(parsed);
  } catch {
    return {};
  }
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

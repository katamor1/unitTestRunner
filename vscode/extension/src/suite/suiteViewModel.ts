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
  function?: unknown;
  workspace?: unknown;
}

interface SuiteRunResult {
  entry_id?: unknown;
  execution_status?: unknown;
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
  const manifest = readJsonObject(suitePath);
  const report = readJsonObject(reportPath);
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
    lastRunStatus: stringValue(report.status) || 'not_run',
    lastError,
    summary: summaryView(objectValue(report.summary), reportExists ? entries.length : 0),
    entries,
  };
}

function buildEntryView(entry: ManifestEntry, results: Map<string, SuiteRunResult>, selected: Set<string>): SuiteEntryView {
  const entryId = stringValue(entry.entry_id);
  const functionPayload = objectValue(entry.function);
  const result = results.get(entryId);
  return {
    entryId,
    enabled: entry.enabled !== false,
    selected: selected.has(entryId),
    tags: arrayValue(entry.tags).map((item) => stringValue(item)).filter((item) => item.length > 0),
    functionName: stringValue(functionPayload.name) || entryId,
    source: stringValue(functionPayload.source),
    project: stringValue(functionPayload.project),
    configuration: stringValue(functionPayload.configuration),
    workspace: stringValue(entry.workspace),
    lastRunStatus: result ? stringValue(result.execution_status) || 'unknown' : 'not_run',
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

function summaryView(summary: Record<string, unknown>, fallbackTotal: number): SuiteRunSummaryView {
  return {
    total: numberValue(summary.total, fallbackTotal),
    green: numberValue(summary.green),
    notGreen: numberValue(summary.not_green),
    executed: numberValue(summary.executed),
    failed: numberValue(summary.failed),
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

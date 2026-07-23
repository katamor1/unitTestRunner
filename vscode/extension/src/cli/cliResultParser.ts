import { resolveReportPaths, ReportPaths } from '../reports/reportPathResolver';
import { resolveReportedPath } from '../platform/pathDialect';
import { parseCliEnvelopeValue } from './cliEnvelope';

export interface ParsedCliResult {
  status?: string;
  parsedJson?: unknown;
  reports: ReportPaths;
  warnings: string[];
}

export function parseCliResultReportPaths(stdout: string, stderr: string, workspace: string): ReportPaths {
  const parsed = parseCliResult(stdout, stderr, workspace);
  return parsed.reports;
}

export function formatCliFailureMessage(stdout: string, stderr: string, exitCode: number | null): string {
  const exitText = `UnitTestRunner CLIが終了コード ${exitCode ?? '不明'} で終了しました。`;
  const parsed = parseJsonObject(stdout);
  if (!parsed) {
    const detail = stderr.trim();
    return detail ? `${exitText} ${detail}` : exitText;
  }
  let version: '1.0.0' | '0.1';
  try {
    version = parseCliEnvelopeValue(parsed).version;
  } catch {
    const detail = stderr.trim();
    return detail ? `${exitText} ${detail}` : exitText;
  }
  if (version === '1.0.0') {
    return formatV1Failure(parsed, exitCode, exitText);
  }
  const suiteMessage = formatSuiteRunFailure(parsed, exitCode);
  if (suiteMessage) {
    return `${exitText} ${suiteMessage}`;
  }
  const command = stringValue(parsed.command);
  const details = stringArrayValue(parsed.errors);
  const message = stringValue(parsed.message);
  const status = stringValue(parsed.status);
  const detailParts = [...details];
  if (message && message !== 'Build workspace generated.' && !detailParts.includes(message)) {
    detailParts.push(message);
  }
  const context = [command, status].filter(Boolean).join(' / ');
  const suffix = [context, ...detailParts].filter(Boolean).join(': ');
  return suffix ? `${exitText} ${suffix}` : exitText;
}

function formatV1Failure(parsed: Record<string, unknown>, exitCode: number | null, exitText: string): string {
  const data = objectValue(parsed.data);
  const normalized = {
    command: data.command,
    status: data.outcome,
    data: data.details,
  };
  const suiteMessage = formatSuiteRunFailure(normalized, exitCode);
  const command = stringValue(data.command);
  const outcome = stringValue(data.outcome);
  const details = messageArrayValue(data.errors);
  for (const diagnostic of Array.isArray(data.diagnostics) ? data.diagnostics : []) {
    if (isMessageRecord(diagnostic)) {
      details.push(diagnostic.message);
    }
  }
  const message = stringValue(data.message);
  const detailParts = suiteMessage ? [suiteMessage, ...details] : [...details];
  if (message && !detailParts.includes(message)) {
    detailParts.push(message);
  }
  const context = [command, outcome].filter(Boolean).join(' / ');
  const suffix = [context, ...detailParts].filter(Boolean).join(': ');
  return suffix ? `${exitText} ${suffix}` : exitText;
}

function formatSuiteRunFailure(parsed: Record<string, unknown>, exitCode: number | null): string | undefined {
  const command = stringValue(parsed.command);
  const status = stringValue(parsed.status);
  if (command !== 'suite-run' && status !== 'suite_run_failed') {
    return undefined;
  }
  if (exitCode !== 32 && status !== 'suite_run_failed') {
    return undefined;
  }
  const data = objectValue(parsed.data);
  const summary = objectValue(data.summary);
  const reports = objectValue(data.reports);
  const total = numberValue(summary.total);
  const green = numberValue(summary.green);
  const notGreen = numberValue(summary.not_green);
  const reportPath = stringValue(reports.suite_run_report_md);
  const parts = [`全件の合格条件を満たしていません。合計${total}件 / 合格${green}件 / 不合格${notGreen}件`];
  if (reportPath) {
    parts.push(`実行レポート: ${reportPath}`);
  }
  return parts.join(' ');
}

export function parseCliResult(stdout: string, stderr: string, workspace: string): ParsedCliResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout) as unknown;
  } catch {
    const warnings = ['CLIの出力がJSON形式ではないため、生成されたレポートのパスを取得できませんでした。'];
    if (stderr.trim()) {
      warnings.push(stderr.trim());
    }
    return { parsedJson: undefined, reports: reportsFromSource({}, workspace), warnings };
  }
  const envelope = parseCliEnvelopeValue(parsed);
  const reports = reportsFromSource(envelope.reportedPaths, workspace);
  const warnings = [...envelope.warnings];
  if (stderr.trim()) {
    warnings.push(stderr.trim());
  }
  const legacyStatus = stringValue(envelope.raw.status);
  return {
    status: envelope.outcome ?? legacyStatus,
    parsedJson: envelope.raw,
    reports,
    warnings,
  };
}

function reportsFromSource(reportSource: Record<string, string>, workspace: string): ReportPaths {
  const reportPath = (value: unknown): string | undefined => {
    const reported = stringValue(value);
    return reported ? resolveReportedPath(reported, workspace) : undefined;
  };
  return {
    workspace,
    functionDossierMd: reportPath(reportSource.function_dossier_md),
    reviewChecklistMd: reportPath(reportSource.review_checklist),
    unresolvedItemsMd: reportPath(reportSource.unresolved_items),
    nextActionsMd: reportPath(reportSource.next_actions),
    quickSummaryJson: reportPath(reportSource.quick_summary_json),
    quickSummaryMd: reportPath(reportSource.quick_summary_md),
    testCaseDesignMd: reportPath(reportSource.test_case_design_md),
    testCaseDesignJson: reportPath(reportSource.test_case_design_json),
    testCaseDesignCsv: reportPath(reportSource.test_case_design_csv),
    testSpecJson: reportPath(reportSource.test_spec_json),
    testSpecMd: reportPath(reportSource.test_spec_md),
    testSpecCsv: reportPath(reportSource.test_spec_csv),
    functionSignatureJson: reportPath(reportSource.function_signature_json),
    globalAccessJson: reportPath(reportSource.global_access_json),
    callReportJson: reportPath(reportSource.call_report_json),
    harnessSkeletonReportJson: reportPath(reportSource.harness_skeleton_report_json),
    harnessSkeletonReportMd: reportPath(reportSource.harness_skeleton_report_md),
    buildProbeReportMd: reportPath(reportSource.build_probe_report_md),
    testExecutionReportMd: reportPath(reportSource.test_execution_report_md),
    testExecutionBlockersJson: reportPath(reportSource.test_execution_blockers_json),
    testExecutionBlockersMd: reportPath(reportSource.test_execution_blockers_md),
    evidencePackageMd: reportPath(reportSource.evidence_package_md),
    changeImpactReportMd: reportPath(reportSource.change_impact_report_md),
    testCaseReconciliationReportMd: reportPath(reportSource.test_case_reconciliation_report_md),
    regressionSelectionCsv: reportPath(reportSource.regression_selection_csv),
  };
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function stringArrayValue(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string');
}

function messageArrayValue(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (typeof item === 'string') {
      return [item];
    }
    return isMessageRecord(item) ? [item.message] : [];
  });
}

function isMessageRecord(value: unknown): value is { message: string } {
  return Boolean(value)
    && typeof value === 'object'
    && !Array.isArray(value)
    && typeof (value as Record<string, unknown>).message === 'string';
}

function numberValue(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function parseJsonObject(value: string): Record<string, unknown> | undefined {
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : undefined;
  } catch {
    return undefined;
  }
}

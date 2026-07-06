import { resolveReportPaths, ReportPaths } from '../reports/reportPathResolver';

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

export function parseCliResult(stdout: string, stderr: string, workspace: string): ParsedCliResult {
  const warnings: string[] = [];
  const fallback = resolveReportPaths(workspace);
  try {
    const parsed = JSON.parse(stdout) as Record<string, unknown>;
    const reports = reportsFromParsed(parsed, fallback, warnings);
    return {
      status: typeof parsed.status === 'string' ? parsed.status : undefined,
      parsedJson: parsed,
      reports,
      warnings,
    };
  } catch {
    if (stderr.trim()) {
      warnings.push(stderr.trim());
    }
    return { parsedJson: undefined, reports: fallback, warnings };
  }
}

function reportsFromParsed(parsed: Record<string, unknown>, fallback: ReportPaths, warnings: string[]): ReportPaths {
  const data = objectValue(parsed.data);
  const review = objectValue(data.review);
  const reportSource = optionalObjectValue(parsed.reports) ?? optionalObjectValue(data.reports) ?? optionalObjectValue(review.reports);
  if (!reportSource) {
    warnings.push('CLI JSONにレポートパスが含まれていません。既定のパスを使います。');
    return fallback;
  }
  const missing = [
    ['function_dossier_md', 'functionDossierMd'],
    ['review_checklist', 'reviewChecklistMd'],
    ['unresolved_items', 'unresolvedItemsMd'],
    ['next_actions', 'nextActionsMd'],
  ].filter(([jsonKey]) => stringValue(reportSource[jsonKey]) === undefined);
  if (missing.length > 0) {
    warnings.push(`CLI JSONにレポートパスが含まれていません: ${missing.map(([jsonKey]) => jsonKey).join(', ')}。既定のパスを使います。`);
  }
  return {
    workspace: fallback.workspace,
    functionDossierMd: stringValue(reportSource.function_dossier_md) ?? fallback.functionDossierMd,
    reviewChecklistMd: stringValue(reportSource.review_checklist) ?? fallback.reviewChecklistMd,
    unresolvedItemsMd: stringValue(reportSource.unresolved_items) ?? fallback.unresolvedItemsMd,
    nextActionsMd: stringValue(reportSource.next_actions) ?? fallback.nextActionsMd,
    testCaseDesignMd: stringValue(reportSource.test_case_design_md) ?? fallback.testCaseDesignMd,
    testCaseDesignJson: stringValue(reportSource.test_case_design_json) ?? fallback.testCaseDesignJson,
    testCaseDesignCsv: stringValue(reportSource.test_case_design_csv) ?? fallback.testCaseDesignCsv,
    functionSignatureJson: stringValue(reportSource.function_signature_json) ?? fallback.functionSignatureJson,
    globalAccessJson: stringValue(reportSource.global_access_json) ?? fallback.globalAccessJson,
    callReportJson: stringValue(reportSource.call_report_json) ?? fallback.callReportJson,
    harnessSkeletonReportJson: stringValue(reportSource.harness_skeleton_report_json) ?? stringValue(objectValue(data.harness_skeleton).json) ?? fallback.harnessSkeletonReportJson,
    harnessSkeletonReportMd: stringValue(reportSource.harness_skeleton_report_md) ?? stringValue(objectValue(data.harness_skeleton).markdown) ?? fallback.harnessSkeletonReportMd,
    buildProbeReportMd: stringValue(reportSource.build_probe_report_md) ?? fallback.buildProbeReportMd,
    testExecutionReportMd: stringValue(reportSource.test_execution_report_md) ?? fallback.testExecutionReportMd,
    evidencePackageMd: stringValue(reportSource.evidence_package_md) ?? fallback.evidencePackageMd,
    changeImpactReportMd: stringValue(reportSource.change_impact_report_md) ?? fallback.changeImpactReportMd,
    testCaseReconciliationReportMd: stringValue(reportSource.test_case_reconciliation_report_md) ?? fallback.testCaseReconciliationReportMd,
    regressionSelectionCsv: stringValue(reportSource.regression_selection_csv) ?? fallback.regressionSelectionCsv,
  };
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function optionalObjectValue(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

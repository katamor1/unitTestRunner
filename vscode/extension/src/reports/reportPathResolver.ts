import { pathDialect } from '../platform/pathDialect';

export interface ReportPaths {
  workspace: string;
  functionDossierMd?: string;
  reviewChecklistMd?: string;
  unresolvedItemsMd?: string;
  nextActionsMd?: string;
  quickSummaryJson?: string;
  quickSummaryMd?: string;
  testCaseDesignMd?: string;
  testCaseDesignJson?: string;
  testCaseDesignCsv?: string;
  functionSignatureJson?: string;
  globalAccessJson?: string;
  callReportJson?: string;
  harnessSkeletonReportJson?: string;
  harnessSkeletonReportMd?: string;
  buildProbeReportMd?: string;
  testExecutionReportMd?: string;
  evidencePackageMd?: string;
  changeImpactReportMd?: string;
  testCaseReconciliationReportMd?: string;
  regressionSelectionCsv?: string;
}

export function resolveReportPaths(workspace: string): ReportPaths {
  const dialect = pathDialect(workspace);
  const reports = dialect.join(workspace, 'reports');
  return {
    workspace,
    functionDossierMd: dialect.join(reports, 'function_dossier.md'),
    reviewChecklistMd: dialect.join(reports, 'review_checklist.md'),
    unresolvedItemsMd: dialect.join(reports, 'unresolved_items.md'),
    nextActionsMd: dialect.join(reports, 'next_actions.md'),
    quickSummaryJson: dialect.join(reports, 'quick_summary.json'),
    quickSummaryMd: dialect.join(reports, 'quick_summary.md'),
    testCaseDesignMd: dialect.join(reports, 'test_case_design.md'),
    testCaseDesignJson: dialect.join(reports, 'test_case_design.json'),
    testCaseDesignCsv: dialect.join(reports, 'test_case_design.csv'),
    functionSignatureJson: dialect.join(reports, 'function_signature.json'),
    globalAccessJson: dialect.join(reports, 'global_access.json'),
    callReportJson: dialect.join(reports, 'call_report.json'),
    harnessSkeletonReportJson: dialect.join(reports, 'harness_skeleton_report.json'),
    harnessSkeletonReportMd: dialect.join(reports, 'harness_skeleton_report.md'),
    buildProbeReportMd: dialect.join(reports, 'build_probe_report.md'),
    testExecutionReportMd: dialect.join(reports, 'test_execution_report.md'),
    evidencePackageMd: dialect.join(reports, 'evidence_package.md'),
    changeImpactReportMd: dialect.join(reports, 'change_impact_report.md'),
    testCaseReconciliationReportMd: dialect.join(reports, 'test_case_reconciliation_report.md'),
    regressionSelectionCsv: dialect.join(reports, 'regression_selection.csv'),
  };
}

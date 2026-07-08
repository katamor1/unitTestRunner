import * as path from 'path';

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
  const reports = path.join(workspace, 'reports');
  return {
    workspace,
    functionDossierMd: path.join(reports, 'function_dossier.md'),
    reviewChecklistMd: path.join(reports, 'review_checklist.md'),
    unresolvedItemsMd: path.join(reports, 'unresolved_items.md'),
    nextActionsMd: path.join(reports, 'next_actions.md'),
    quickSummaryJson: path.join(reports, 'quick_summary.json'),
    quickSummaryMd: path.join(reports, 'quick_summary.md'),
    testCaseDesignMd: path.join(reports, 'test_case_design.md'),
    testCaseDesignJson: path.join(reports, 'test_case_design.json'),
    testCaseDesignCsv: path.join(reports, 'test_case_design.csv'),
    functionSignatureJson: path.join(reports, 'function_signature.json'),
    globalAccessJson: path.join(reports, 'global_access.json'),
    callReportJson: path.join(reports, 'call_report.json'),
    harnessSkeletonReportJson: path.join(reports, 'harness_skeleton_report.json'),
    harnessSkeletonReportMd: path.join(reports, 'harness_skeleton_report.md'),
    buildProbeReportMd: path.join(reports, 'build_probe_report.md'),
    testExecutionReportMd: path.join(reports, 'test_execution_report.md'),
    evidencePackageMd: path.join(reports, 'evidence_package.md'),
    changeImpactReportMd: path.join(reports, 'change_impact_report.md'),
    testCaseReconciliationReportMd: path.join(reports, 'test_case_reconciliation_report.md'),
    regressionSelectionCsv: path.join(reports, 'regression_selection.csv'),
  };
}

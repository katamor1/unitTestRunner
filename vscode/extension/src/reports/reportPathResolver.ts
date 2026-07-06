import * as path from 'path';

export interface ReportPaths {
  workspace: string;
  functionDossierMd?: string;
  reviewChecklistMd?: string;
  unresolvedItemsMd?: string;
  nextActionsMd?: string;
  testCaseDesignMd?: string;
  testCaseDesignJson?: string;
  testCaseDesignCsv?: string;
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
    testCaseDesignMd: path.join(reports, 'test_case_design.md'),
    testCaseDesignJson: path.join(reports, 'test_case_design.json'),
    testCaseDesignCsv: path.join(reports, 'test_case_design.csv'),
    buildProbeReportMd: path.join(reports, 'build_probe_report.md'),
    testExecutionReportMd: path.join(reports, 'test_execution_report.md'),
    evidencePackageMd: path.join(reports, 'evidence_package.md'),
    changeImpactReportMd: path.join(reports, 'change_impact_report.md'),
    testCaseReconciliationReportMd: path.join(reports, 'test_case_reconciliation_report.md'),
    regressionSelectionCsv: path.join(reports, 'regression_selection.csv'),
  };
}

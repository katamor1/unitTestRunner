import { pathDialect } from '../platform/pathDialect';

export interface ReportPaths {
  workspace: string;
  functionDossierJson?: string;
  functionDossierMd?: string;
  reviewRecordJson?: string;
  reviewChecklistMd?: string;
  testSpecJson?: string;
  testSpecMd?: string;
  testSpecCsv?: string;
  buildProbeReportJson?: string;
  buildProbeReportMd?: string;
  testRunReportJson?: string;
  testRunReportMd?: string;
  reanalysisReportJson?: string;
  reanalysisReportMd?: string;
  suiteManifestJson?: string;
  suiteRunReportJson?: string;
  suiteRunReportMd?: string;
}

export function resolveReportPaths(workspace: string): ReportPaths {
  const dialect = pathDialect(workspace);
  const reports = dialect.join(workspace, 'reports');
  return {
    workspace,
    functionDossierJson: dialect.join(reports, 'function_dossier.json'),
    functionDossierMd: dialect.join(reports, 'function_dossier.md'),
    reviewRecordJson: dialect.join(reports, 'review_record.json'),
    reviewChecklistMd: dialect.join(reports, 'review_checklist.md'),
    testSpecJson: dialect.join(reports, 'test_spec.json'),
    testSpecMd: dialect.join(reports, 'test_spec.md'),
    testSpecCsv: dialect.join(reports, 'test_spec.csv'),
    buildProbeReportJson: dialect.join(reports, 'build_probe_report.json'),
    buildProbeReportMd: dialect.join(reports, 'build_probe_report.md'),
    reanalysisReportJson: dialect.join(reports, 'reanalysis_report.json'),
    reanalysisReportMd: dialect.join(reports, 'reanalysis_report.md'),
  };
}

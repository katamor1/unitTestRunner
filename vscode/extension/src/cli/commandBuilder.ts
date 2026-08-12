import * as path from 'path';

import { AdapterSettings } from '../config/settings';

export interface FunctionTarget {
  sourcePath: string;
  sourceRelativePath?: string;
  functionName: string;
  project?: string;
  configuration?: string;
  outputWorkspace: string;
}

export interface CliInvocation {
  command: string;
  args: string[];
  workingDirectory: string;
  displayCommand: string;
  timeoutSeconds: number;
  requiresConfirmation: boolean;
}

export type AnalyzePhase = 'analysis' | 'design' | 'harness';

export interface TestRunSelector {
  caseIds?: string[];
  tag?: string;
  all?: boolean;
}

export interface SuiteRunSelector extends TestRunSelector {
  entryIds?: string[];
  run: boolean;
}

export function buildAnalyzeFunctionInvocation(
  settings: AdapterSettings,
  target: FunctionTarget,
  phase: AnalyzePhase = 'design',
): CliInvocation {
  const args = jsonPrefix().concat([
    'analyze-function',
    '--workspace', settings.sourceRoot,
    '--dsw', settings.dswPath,
    '--source', target.sourceRelativePath ?? relativeSourcePath(target.sourcePath, settings.sourceRoot),
    '--function', target.functionName,
    '--configuration', target.configuration || settings.defaultConfiguration,
    '--out', target.outputWorkspace,
    '--phase', phase,
  ]);
  const project = target.project || settings.defaultProject;
  if (project) {
    args.push('--project', project);
  }
  return invocation(settings, args, false);
}

export function buildPrepareHarnessInvocation(settings: AdapterSettings, target: FunctionTarget): CliInvocation {
  return buildAnalyzeFunctionInvocation(settings, target, 'harness');
}

export function buildReanalyzeFunctionInvocation(settings: AdapterSettings, target: FunctionTarget): CliInvocation {
  const reports = path.join(target.outputWorkspace, 'reports');
  const args = jsonPrefix().concat([
    'reanalyze-function',
    '--workspace', settings.sourceRoot,
    '--dsw', settings.dswPath,
    '--source', target.sourceRelativePath ?? relativeSourcePath(target.sourcePath, settings.sourceRoot),
    '--function', target.functionName,
    '--configuration', target.configuration || settings.defaultConfiguration,
    '--out', target.outputWorkspace,
    '--previous-dossier', path.join(reports, 'function_dossier.json'),
    '--previous-test-spec', path.join(reports, 'test_spec.json'),
  ]);
  const project = target.project || settings.defaultProject;
  if (project) {
    args.push('--project', project);
  }
  return invocation(settings, args, false);
}

export function buildApplyReanalysisInvocation(
  settings: AdapterSettings,
  workspace: string,
  candidatePath: string,
  candidateSha256: string,
  expectedRevision: number,
): CliInvocation {
  return invocation(settings, jsonPrefix().concat([
    'apply-reanalysis',
    '--workspace', workspace,
    '--candidate', candidatePath,
    '--candidate-sha256', candidateSha256,
    '--expected-revision', String(expectedRevision),
  ]), false);
}

export function buildFinalizeDossierInvocation(settings: AdapterSettings, workspace: string): CliInvocation {
  return invocation(settings, jsonPrefix().concat(['finalize-dossier', '--workspace', workspace]), false);
}

export function buildReviewSetInvocation(
  settings: AdapterSettings,
  workspace: string,
  artifactKind: string,
  artifactSha256: string,
  decision: 'approved' | 'changes_requested',
  reviewer: string,
  comment: string,
): CliInvocation {
  return invocation(settings, jsonPrefix().concat([
    'review-set',
    '--workspace', workspace,
    '--artifact-kind', artifactKind,
    '--artifact-sha256', artifactSha256,
    '--decision', decision,
    '--reviewer', reviewer,
    '--comment', comment,
  ]), false);
}

export function buildBuildProbeInvocation(settings: AdapterSettings, workspace: string, run: boolean): CliInvocation {
  const args = jsonPrefix().concat(['build-probe', '--workspace', workspace, run ? '--run' : '--dry-run']);
  if (settings.vcvarsPath) {
    args.push('--vcvars', settings.vcvarsPath);
  }
  return invocation(settings, args, run && settings.runBuildProbeRequiresConfirmation);
}

export function buildRunTestsInvocation(
  settings: AdapterSettings,
  workspace: string,
  run: boolean,
  selector: TestRunSelector = { all: true },
): CliInvocation {
  const args = jsonPrefix().concat(['run-tests', '--workspace', workspace]);
  appendTestSelector(args, selector);
  args.push(run ? '--run' : '--plan');
  return invocation(settings, args, run && settings.runTestsRequiresConfirmation);
}

export function buildSuiteManifestPath(settings: AdapterSettings): string {
  return settings.suiteManifestPath || path.join(settings.outputRoot, 'suites', 'default', 'suite_manifest.json');
}

export function buildSuiteRegisterInvocation(
  settings: AdapterSettings,
  target: FunctionTarget,
  tags: string[],
  expectedRevision: number,
): CliInvocation {
  const args = jsonPrefix().concat([
    'suite-register',
    '--suite', buildSuiteManifestPath(settings),
    '--workspace', target.outputWorkspace,
    '--expected-revision', String(expectedRevision),
  ]);
  if (tags.length > 0) {
    args.push('--tags', tags.join(','));
  }
  return invocation(settings, args, false);
}

export function buildSuiteUpdateInvocation(
  settings: AdapterSettings,
  entryId: string,
  enabled: boolean,
  expectedRevision: number,
): CliInvocation {
  return invocation(settings, jsonPrefix().concat([
    'suite-update',
    '--suite', buildSuiteManifestPath(settings),
    '--entry-id', entryId,
    '--enabled', String(enabled),
    '--expected-revision', String(expectedRevision),
  ]), false);
}

export function buildSuiteRunInvocation(settings: AdapterSettings, selector: SuiteRunSelector): CliInvocation {
  const args = jsonPrefix().concat(['suite-run', '--suite', buildSuiteManifestPath(settings)]);
  if (selector.entryIds?.length) {
    for (const entryId of selector.entryIds) {
      args.push('--entry-id', entryId);
    }
  } else {
    appendTestSelector(args, selector);
  }
  args.push(selector.run ? '--run' : '--plan');
  return invocation(settings, args, selector.run && settings.runTestsRequiresConfirmation);
}

export function buildGetTestInputFormInvocation(
  settings: AdapterSettings,
  workspace: string,
  summaryOnly = false,
): CliInvocation {
  const args = jsonPrefix().concat(['get-test-input-form', '--workspace', workspace]);
  if (summaryOnly) {
    args.push('--summary-only');
  }
  return invocation(settings, args, false);
}

export function buildApplyTestInputFormInvocation(
  settings: AdapterSettings,
  workspace: string,
  inputPath: string,
  expectedRevision: number,
): CliInvocation {
  return invocation(settings, jsonPrefix().concat([
    'apply-test-input-form',
    '--workspace', workspace,
    '--input', inputPath,
    '--expected-revision', String(expectedRevision),
  ]), false);
}

export function relativeSourcePath(sourcePath: string, sourceRoot: string): string {
  return path.relative(sourceRoot, sourcePath).split(path.sep).join('/');
}

function appendTestSelector(args: string[], selector: TestRunSelector): void {
  if (selector.caseIds?.length) {
    for (const caseId of selector.caseIds) {
      args.push('--case-id', caseId);
    }
  } else if (selector.tag) {
    args.push('--tag', selector.tag);
  } else {
    args.push('--all');
  }
}

function jsonPrefix(): string[] {
  return ['--json'];
}

function invocation(settings: AdapterSettings, args: string[], requiresConfirmation: boolean): CliInvocation {
  return {
    command: settings.cliPath,
    args,
    workingDirectory: settings.sourceRoot || process.cwd(),
    displayCommand: [quoteForDisplay(settings.cliPath), ...args.map(quoteForDisplay)].join(' '),
    timeoutSeconds: settings.commandTimeoutSeconds,
    requiresConfirmation,
  };
}

function quoteForDisplay(value: string): string {
  return /\s/.test(value) ? `"${value}"` : value;
}

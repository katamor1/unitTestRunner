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

export function buildAnalyzeFunctionInvocation(settings: AdapterSettings, target: FunctionTarget): CliInvocation {
  const args = jsonPrefix(settings).concat([
    'analyze-function',
    '--workspace',
    settings.sourceRoot,
    '--dsw',
    settings.dswPath,
    '--source',
    target.sourceRelativePath ?? relativeSourcePath(target.sourcePath, settings.sourceRoot),
    '--function',
    target.functionName,
    '--configuration',
    target.configuration || settings.defaultConfiguration,
    '--out',
    target.outputWorkspace,
  ]);
  const project = target.project || settings.defaultProject;
  if (project) {
    args.push('--project', project);
  }
  if (settings.finalizeDossierAfterAnalyze) {
    args.push('--finalize-dossier');
  }
  return invocation(settings, args, false);
}

export function buildReanalyzeFunctionInvocation(settings: AdapterSettings, target: FunctionTarget): CliInvocation {
  const reports = path.join(target.outputWorkspace, 'reports');
  const args = jsonPrefix(settings).concat([
    'reanalyze-function',
    '--workspace',
    settings.sourceRoot,
    '--dsw',
    settings.dswPath,
    '--source',
    target.sourceRelativePath ?? relativeSourcePath(target.sourcePath, settings.sourceRoot),
    '--function',
    target.functionName,
    '--configuration',
    target.configuration || settings.defaultConfiguration,
    '--out',
    target.outputWorkspace,
    '--previous-dossier',
    path.join(reports, 'function_dossier.json'),
    '--previous-test-case-design',
    path.join(reports, 'test_case_design.json'),
  ]);
  const project = target.project || settings.defaultProject;
  if (project) {
    args.push('--project', project);
  }
  return invocation(settings, args, false);
}

export function buildFinalizeDossierInvocation(settings: AdapterSettings, workspace: string): CliInvocation {
  return invocation(settings, jsonPrefix(settings).concat(['finalize-dossier', '--workspace', workspace]), false);
}

export function buildBuildProbeInvocation(settings: AdapterSettings, workspace: string, run: boolean): CliInvocation {
  const args = jsonPrefix(settings).concat(['build-probe', '--workspace', workspace, run ? '--run' : '--dry-run']);
  return invocation(settings, args, run && settings.runBuildProbeRequiresConfirmation);
}

export function buildRunTestsInvocation(settings: AdapterSettings, workspace: string, run: boolean): CliInvocation {
  const args = jsonPrefix(settings).concat(['run-tests', '--workspace', workspace, run ? '--run' : '--dry-run']);
  return invocation(settings, args, run && settings.runTestsRequiresConfirmation);
}

export function buildPrepareEvidenceInvocation(settings: AdapterSettings, workspace: string): CliInvocation {
  return invocation(settings, jsonPrefix(settings).concat(['prepare-evidence', '--workspace', workspace]), false);
}

export function buildGenerateTestDesignInvocation(settings: AdapterSettings, dossierPath: string): CliInvocation {
  return invocation(settings, jsonPrefix(settings).concat(['generate-test-design', '--dossier', dossierPath]), false);
}

export function buildGenerateHarnessSkeletonInvocation(settings: AdapterSettings, workspace: string): CliInvocation {
  const reports = path.join(workspace, 'reports');
  const args = jsonPrefix(settings).concat([
    'generate-harness-skeleton',
    '--function-signature',
    path.join(reports, 'function_signature.json'),
    '--global-access',
    path.join(reports, 'global_access.json'),
    '--call-report',
    path.join(reports, 'call_report.json'),
    '--test-case-design',
    path.join(reports, 'test_case_design.json'),
    '--out',
    workspace,
    '--overwrite',
  ]);
  return invocation(settings, args, false);
}

export function relativeSourcePath(sourcePath: string, sourceRoot: string): string {
  return path.relative(sourceRoot, sourcePath).split(path.sep).join('/');
}

function jsonPrefix(settings: AdapterSettings): string[] {
  return settings.useJsonOutput ? ['--json'] : [];
}

function invocation(settings: AdapterSettings, args: string[], requiresConfirmation: boolean): CliInvocation {
  return {
    command: settings.cliPath,
    args,
    workingDirectory: settings.sourceRoot || process.cwd(),
    displayCommand: [quoteForDisplay(settings.cliPath)].concat(args.map(quoteForDisplay)).join(' '),
    timeoutSeconds: settings.commandTimeoutSeconds,
    requiresConfirmation,
  };
}

function quoteForDisplay(value: string): string {
  return /\s/.test(value) ? `"${value}"` : value;
}

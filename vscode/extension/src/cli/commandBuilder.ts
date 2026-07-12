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

export interface SuiteRunSelector {
  entryIds?: string[];
  tag?: string;
  all?: boolean;
  run: boolean;
  requireGreen?: boolean;
}

export type QuickCheckProfile = 'design' | 'harness' | 'build-dry-run';

interface AnalyzeInvocationOptions {
  finalizeDossier: boolean;
  phase?: 'analysis' | 'design' | 'harness' | 'build' | 'execution';
  outputWorkspace?: string;
}

export function buildAnalyzeFunctionInvocation(settings: AdapterSettings, target: FunctionTarget): CliInvocation {
  const args = buildAnalyzeFunctionArgs(settings, target, {
    finalizeDossier: settings.finalizeDossierAfterAnalyze,
  });
  return invocation(settings, args, false);
}

export function buildQuickCheckInvocation(settings: AdapterSettings, target: FunctionTarget): CliInvocation {
  const outputWorkspace = buildQuickOutputWorkspace(settings, target);
  const args = buildAnalyzeFunctionArgs(settings, target, {
    finalizeDossier: false,
    phase: quickCheckPhase(normalizeQuickCheckProfile(settings.quickProfile)),
    outputWorkspace,
  });
  return invocation(settings, args, false);
}

export function buildFullGateAnalyzeInvocation(settings: AdapterSettings, target: FunctionTarget): CliInvocation {
  const args = buildAnalyzeFunctionArgs(settings, target, {
    finalizeDossier: true,
  });
  return invocation(settings, args, false);
}

export function buildQuickOutputWorkspace(settings: AdapterSettings, target: FunctionTarget): string {
  const root = settings.quickOutputRoot || path.join(settings.outputRoot, '_quick');
  const sourceRelativePath = target.sourceRelativePath ?? relativeSourcePath(target.sourcePath, settings.sourceRoot);
  const sourceSegment = truncateSegment(sanitizeQuickWorkspaceSegment(stripExtension(sourceRelativePath)), 48) || 'source';
  const hash = shortStableHash(sourceRelativePath);
  return path.join(root, `${sourceSegment}_${target.functionName}_${hash}`);
}

export function normalizeQuickCheckProfile(value: string | undefined): QuickCheckProfile {
  if (value === 'design' || value === 'harness' || value === 'build-dry-run') {
    return value;
  }
  return 'design';
}

export function quickCheckPhase(profile: QuickCheckProfile): 'design' | 'harness' | 'build' {
  return profile === 'build-dry-run' ? 'build' : profile;
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
  if (settings.vcvarsPath) {
    args.push('--vcvars', settings.vcvarsPath);
  }
  return invocation(settings, args, run && settings.runBuildProbeRequiresConfirmation);
}

export function buildRunTestsInvocation(settings: AdapterSettings, workspace: string, run: boolean): CliInvocation {
  const args = jsonPrefix(settings).concat(['run-tests', '--workspace', workspace, run ? '--run' : '--plan']);
  return invocation(settings, args, run && settings.runTestsRequiresConfirmation);
}

export function buildSuiteManifestPath(settings: AdapterSettings): string {
  return settings.suiteManifestPath || path.join(settings.outputRoot, 'suites', 'default', 'suite_manifest.json');
}

export function buildSuiteRegisterInvocation(settings: AdapterSettings, target: FunctionTarget, tags: string[]): CliInvocation {
  const args = jsonPrefix(settings).concat([
    'suite-register',
    '--suite',
    buildSuiteManifestPath(settings),
    '--workspace',
    target.outputWorkspace,
    '--tags',
    tags.join(','),
    '--source-root',
    settings.sourceRoot,
    '--dsw',
    settings.dswPath,
  ]);
  return invocation(settings, args, false);
}

export function buildSuiteRunInvocation(settings: AdapterSettings, selector: SuiteRunSelector): CliInvocation {
  const args = jsonPrefix(settings).concat(['suite-run', '--suite', buildSuiteManifestPath(settings)]);
  if (selector.all) {
    args.push('--all');
  } else if (selector.tag) {
    args.push('--tag', selector.tag);
  } else {
    for (const entryId of selector.entryIds ?? []) {
      args.push('--entry-id', entryId);
    }
  }
  args.push(selector.run ? '--run' : '--plan');
  if (selector.requireGreen) {
    args.push('--require-green');
  }
  return invocation(settings, args, selector.run && settings.runTestsRequiresConfirmation);
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
    '--dependency-policy',
    path.join(reports, 'dependency_policy.json'),
    '--out',
    workspace,
    '--overwrite',
  ]);
  return invocation(settings, args, false);
}

export function relativeSourcePath(sourcePath: string, sourceRoot: string): string {
  return path.relative(sourceRoot, sourcePath).split(path.sep).join('/');
}

function buildAnalyzeFunctionArgs(settings: AdapterSettings, target: FunctionTarget, options: AnalyzeInvocationOptions): string[] {
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
    options.outputWorkspace ?? target.outputWorkspace,
  ]);
  const project = target.project || settings.defaultProject;
  if (project) {
    args.push('--project', project);
  }
  if (options.phase) {
    args.push('--phase', options.phase);
  }
  if (options.finalizeDossier) {
    args.push('--finalize-dossier');
  }
  return args;
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

function stripExtension(value: string): string {
  return value.replace(/\.[^/.\\]+$/, '');
}

function sanitizeQuickWorkspaceSegment(value: string): string {
  return value
    .replace(/\\/g, '/')
    .split('/')
    .filter(Boolean)
    .join('_')
    .replace(/[^A-Za-z0-9_.-]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function truncateSegment(value: string, maxLength: number): string {
  return value.length > maxLength ? value.slice(value.length - maxLength) : value;
}

function shortStableHash(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0').slice(0, 8);
}

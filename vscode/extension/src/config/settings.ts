import { DEFAULT_CLI_PATH } from './bundledCli';

export interface AdapterSettings {
  cliPath: string;
  sourceRoot: string;
  dswPath: string;
  outputRoot: string;
  defaultConfiguration: string;
  defaultProject?: string;
  autoOpenDossier: boolean;
  finalizeDossierAfterAnalyze: boolean;
  useJsonOutput: boolean;
  showOutputChannel: boolean;
  runBuildProbeRequiresConfirmation: boolean;
  runTestsRequiresConfirmation: boolean;
  commandTimeoutSeconds: number;
}

export type RawSettings = Record<string, unknown>;

export interface WorkspaceFolderLike {
  uri: {
    fsPath: string;
  };
}

export function defaultSourceRootFromWorkspaceFolders(workspaceFolders: readonly WorkspaceFolderLike[] | undefined): string {
  return workspaceFolders?.[0]?.uri.fsPath ?? '';
}

export function readAdapterSettingsFromObject(raw: RawSettings, defaultSourceRoot: string): AdapterSettings {
  return {
    cliPath: stringValue(raw.cliPath, DEFAULT_CLI_PATH),
    sourceRoot: stringValue(nonEmptyString(raw.sourceRoot) ?? nonEmptyString(raw.workspaceRoot), defaultSourceRoot),
    dswPath: stringValue(raw.dswPath, ''),
    outputRoot: stringValue(raw.outputRoot, ''),
    defaultConfiguration: stringValue(nonEmptyString(raw.defaultConfiguration), 'Win32 Debug'),
    defaultProject: stringValue(nonEmptyString(raw.defaultProject) ?? nonEmptyString(raw.projectName), ''),
    autoOpenDossier: booleanValue(raw.autoOpenDossier, true),
    finalizeDossierAfterAnalyze: booleanValue(raw.finalizeDossierAfterAnalyze, true),
    useJsonOutput: booleanValue(raw.useJsonOutput, true),
    showOutputChannel: booleanValue(raw.showOutputChannel, true),
    runBuildProbeRequiresConfirmation: booleanValue(raw.runBuildProbeRequiresConfirmation, true),
    runTestsRequiresConfirmation: booleanValue(raw.runTestsRequiresConfirmation, true),
    commandTimeoutSeconds: numberValue(raw.commandTimeoutSeconds, 300),
  };
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback;
}

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function booleanValue(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function numberValue(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

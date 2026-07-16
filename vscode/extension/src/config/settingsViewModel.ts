import { DEFAULT_CLI_PATH } from './bundledCli';
import { RawSettings, readAdapterSettingsFromObject } from './settings';
import { validateSettings } from './validation';

export type SettingsFieldId =
  | 'sourceRoot'
  | 'dswPath'
  | 'outputRoot'
  | 'suiteManifestPath'
  | 'defaultConfiguration'
  | 'defaultProject'
  | 'vcvarsPath'
  | 'cliPath';

export type SettingsFieldState = 'configured' | 'default' | 'missing' | 'warning' | 'optional';
export type SettingsActionKind = 'pickFolder' | 'pickFile' | 'inputText' | 'reset';

export interface SettingsAction {
  id: string;
  kind: SettingsActionKind;
  label: string;
  primary?: boolean;
}

export interface SettingsFieldView {
  id: SettingsFieldId;
  label: string;
  settingKey: string;
  description: string;
  effectiveValue: string;
  configuredValue: string;
  state: SettingsFieldState;
  statusLabel: string;
  messages: string[];
  actions: SettingsAction[];
  advanced?: boolean;
}

export interface SettingsViewModel {
  ready: boolean;
  defaultSourceRoot: string;
  fields: SettingsFieldView[];
  warnings: string[];
}

export interface ConfigUpdateRequest {
  key: SettingsFieldId;
  value?: string;
  reset?: boolean;
}

interface FieldSpec {
  id: SettingsFieldId;
  label: string;
  settingKey: string;
  description: string;
  effectiveValue: string;
  configuredValue: string;
  defaulted: boolean;
  optional?: boolean;
  advanced?: boolean;
  actions: SettingsAction[];
}

const WARNING_FIELD_MAP: Record<string, SettingsFieldId> = {
  missing_cli_path: 'cliPath',
  missing_source_root: 'sourceRoot',
  missing_dsw_path: 'dswPath',
  missing_output_root: 'outputRoot',
  output_root_inside_source_root: 'outputRoot',
};

export function buildSettingsViewModel(raw: RawSettings, defaultSourceRoot: string): SettingsViewModel {
  const normalizedRaw = normalizeRaw(raw);
  const settings = readAdapterSettingsFromObject(normalizedRaw, defaultSourceRoot);
  const validation = validateSettings(settings);
  const messagesByField = new Map<SettingsFieldId, string[]>();
  const missingFields = new Set<SettingsFieldId>();
  for (const warning of validation.warnings) {
    const fieldId = WARNING_FIELD_MAP[warning.code];
    if (!fieldId) {
      continue;
    }
    if (warning.code.startsWith('missing_')) {
      missingFields.add(fieldId);
    }
    const messages = messagesByField.get(fieldId) ?? [];
    messages.push(warning.message);
    messagesByField.set(fieldId, messages);
  }

  const fields = fieldSpecs(raw, settings, defaultSourceRoot).map((spec) => toFieldView(spec, messagesByField.get(spec.id) ?? [], missingFields.has(spec.id)));
  return {
    ready: validation.ok,
    defaultSourceRoot,
    fields,
    warnings: validation.warnings.map((warning) => warning.message),
  };
}

function normalizeRaw(raw: RawSettings): RawSettings {
  return {
    ...raw,
    cliPath: nonEmptyString(raw.cliPath) ?? undefined,
    sourceRoot: nonEmptyString(raw.sourceRoot) ?? nonEmptyString(raw.workspaceRoot),
    defaultConfiguration: nonEmptyString(raw.defaultConfiguration) ?? undefined,
  };
}

function fieldSpecs(raw: RawSettings, settings: ReturnType<typeof readAdapterSettingsFromObject>, defaultSourceRoot: string): FieldSpec[] {
  const configuredSourceRoot = nonEmptyString(raw.sourceRoot) ?? nonEmptyString(raw.workspaceRoot) ?? '';
  const configuredCliPath = nonEmptyString(raw.cliPath) ?? '';
  const configuredDefaultConfiguration = nonEmptyString(raw.defaultConfiguration) ?? '';
  const configuredDefaultProject = nonEmptyString(raw.defaultProject) ?? nonEmptyString(raw.projectName) ?? '';
  const configuredVcvarsPath = nonEmptyString(raw.vcvarsPath) ?? '';
  const configuredSuiteManifestPath = nonEmptyString(raw.suiteManifestPath) ?? '';
  return [
    {
      id: 'sourceRoot',
      label: 'ソースのルートフォルダー',
      settingKey: 'unitTestRunner.sourceRoot',
      description: 'テスト対象のソースコードを読み込むルートフォルダーです。未設定の場合は、VS Codeで最初に開いたフォルダーを使用します。',
      effectiveValue: settings.sourceRoot,
      configuredValue: configuredSourceRoot,
      defaulted: !configuredSourceRoot && !!defaultSourceRoot,
      actions: [
        { id: 'pickSourceRoot', kind: 'pickFolder', label: 'フォルダーを選択', primary: true },
        { id: 'inputSourceRoot', kind: 'inputText', label: 'フォルダーのパスを入力' },
        { id: 'resetSourceRoot', kind: 'reset', label: '既定値に戻す' },
      ],
    },
    {
      id: 'dswPath',
      label: 'VC6ワークスペースファイル（.dsw）',
      settingKey: 'unitTestRunner.dswPath',
      description: 'テスト対象プロジェクトのVisual C++ 6.0ワークスペースファイルです。',
      effectiveValue: settings.dswPath,
      configuredValue: nonEmptyString(raw.dswPath) ?? '',
      defaulted: false,
      actions: [
        { id: 'pickDswPath', kind: 'pickFile', label: '.dswファイルを選択', primary: true },
        { id: 'inputDswPath', kind: 'inputText', label: 'ファイルのパスを入力' },
      ],
    },
    {
      id: 'outputRoot',
      label: '出力先フォルダー',
      settingKey: 'unitTestRunner.outputRoot',
      description: '関数分析レポートやテスト設計などの生成物を保存する出力先フォルダーです。ソースのルートフォルダーとは別の場所を指定してください。',
      effectiveValue: settings.outputRoot,
      configuredValue: nonEmptyString(raw.outputRoot) ?? '',
      defaulted: false,
      actions: [
        { id: 'pickOutputRoot', kind: 'pickFolder', label: '出力先フォルダーを選択', primary: true },
        { id: 'inputOutputRoot', kind: 'inputText', label: 'フォルダーのパスを入力' },
      ],
    },
    {
      id: 'suiteManifestPath',
      label: 'スイート定義ファイル',
      settingKey: 'unitTestRunner.suiteManifestPath',
      description: '複数の関数をまとめて実行するスイート定義ファイルです。未設定の場合は、出力先フォルダー配下のsuites\\default\\suite_manifest.jsonを使用します。',
      effectiveValue: settings.suiteManifestPath || (settings.outputRoot ? `${settings.outputRoot}\\suites\\default\\suite_manifest.json` : ''),
      configuredValue: configuredSuiteManifestPath,
      defaulted: !configuredSuiteManifestPath,
      optional: true,
      advanced: true,
      actions: [
        { id: 'pickSuiteManifestPath', kind: 'pickFile', label: '定義ファイルを選択' },
        { id: 'inputSuiteManifestPath', kind: 'inputText', label: 'ファイルのパスを入力' },
        { id: 'resetSuiteManifestPath', kind: 'reset', label: '既定値に戻す' },
      ],
    },
    {
      id: 'defaultConfiguration',
      label: '既定のビルド構成',
      settingKey: 'unitTestRunner.defaultConfiguration',
      description: '関数解析とビルドで既定として使用するVisual C++ 6.0のビルド構成名です。',
      effectiveValue: settings.defaultConfiguration,
      configuredValue: configuredDefaultConfiguration,
      defaulted: !configuredDefaultConfiguration,
      actions: [
        { id: 'inputDefaultConfiguration', kind: 'inputText', label: 'ビルド構成名を入力', primary: true },
        { id: 'resetDefaultConfiguration', kind: 'reset', label: '既定値に戻す' },
      ],
    },
    {
      id: 'defaultProject',
      label: '既定のVC6プロジェクト',
      settingKey: 'unitTestRunner.defaultProject',
      description: 'ソースファイルが複数のVisual C++ 6.0プロジェクトに含まれる場合に使用する既定のプロジェクト名です。',
      effectiveValue: settings.defaultProject ?? '',
      configuredValue: configuredDefaultProject,
      defaulted: false,
      optional: true,
      actions: [
        { id: 'inputDefaultProject', kind: 'inputText', label: 'プロジェクト名を入力', primary: true },
        { id: 'resetDefaultProject', kind: 'reset', label: '設定をクリア' },
      ],
    },
    {
      id: 'vcvarsPath',
      label: 'VC6環境設定ファイル',
      settingKey: 'unitTestRunner.vcvarsPath',
      description: 'ビルド前に実行するVisual C++ 6.0の環境設定バッチファイルです。nmakeまたはclがPATHにない場合に指定します。',
      effectiveValue: settings.vcvarsPath ?? '',
      configuredValue: configuredVcvarsPath,
      defaulted: false,
      optional: true,
      advanced: true,
      actions: [
        { id: 'pickVcvarsPath', kind: 'pickFile', label: 'バッチファイルを選択', primary: true },
        { id: 'inputVcvarsPath', kind: 'inputText', label: 'ファイルのパスを入力' },
        { id: 'resetVcvarsPath', kind: 'reset', label: '設定をクリア' },
      ],
    },
    {
      id: 'cliPath',
      label: 'UnitTestRunnerの実行ファイル',
      settingKey: 'unitTestRunner.cliPath',
      description: '通常は同梱のCLIを使用します。外部の実行ファイルを使用する場合だけ指定してください。',
      effectiveValue: configuredCliPath || DEFAULT_CLI_PATH,
      configuredValue: configuredCliPath,
      defaulted: !configuredCliPath,
      advanced: true,
      actions: [
        { id: 'pickCliPath', kind: 'pickFile', label: '実行ファイルを選択' },
        { id: 'inputCliPath', kind: 'inputText', label: '実行ファイルのパスを入力' },
        { id: 'resetCliPath', kind: 'reset', label: '既定値に戻す' },
      ],
    },
  ];
}

function toFieldView(spec: FieldSpec, messages: string[], missing: boolean): SettingsFieldView {
  const state = fieldState(spec, missing, messages);
  return {
    id: spec.id,
    label: spec.label,
    settingKey: spec.settingKey,
    description: spec.description,
    effectiveValue: spec.effectiveValue,
    configuredValue: spec.configuredValue,
    state,
    statusLabel: statusLabel(state),
    messages,
    actions: spec.actions,
    advanced: spec.advanced,
  };
}

function fieldState(spec: FieldSpec, missing: boolean, messages: string[]): SettingsFieldState {
  if (missing) {
    return spec.optional ? 'optional' : 'missing';
  }
  if (messages.length > 0) {
    return 'warning';
  }
  if (spec.defaulted) {
    return 'default';
  }
  if (spec.configuredValue) {
    return 'configured';
  }
  return spec.optional ? 'optional' : 'configured';
}

function statusLabel(state: SettingsFieldState): string {
  if (state === 'configured') {
    return '設定済み';
  }
  if (state === 'default') {
    return '既定値';
  }
  if (state === 'missing') {
    return '未設定';
  }
  if (state === 'warning') {
    return '要確認';
  }
  return '任意';
}

function nonEmptyString(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? value : undefined;
}

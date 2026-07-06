import { DEFAULT_CLI_PATH } from './bundledCli';
import { RawSettings, readAdapterSettingsFromObject } from './settings';
import { validateSettings } from './validation';

export type SettingsFieldId =
  | 'sourceRoot'
  | 'dswPath'
  | 'outputRoot'
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
  return [
    {
      id: 'sourceRoot',
      label: 'プロジェクトルート',
      settingKey: 'unitTestRunner.sourceRoot',
      description: '本番ソースを読むルートフォルダです。未設定時はVS Codeで開いた先頭フォルダを使います。',
      effectiveValue: settings.sourceRoot,
      configuredValue: configuredSourceRoot,
      defaulted: !configuredSourceRoot && !!defaultSourceRoot,
      actions: [
        { id: 'pickSourceRoot', kind: 'pickFolder', label: 'フォルダを選択', primary: true },
        { id: 'inputSourceRoot', kind: 'inputText', label: 'パスを入力' },
        { id: 'resetSourceRoot', kind: 'reset', label: '既定値に戻す' },
      ],
    },
    {
      id: 'dswPath',
      label: 'VC6 .dsw',
      settingKey: 'unitTestRunner.dswPath',
      description: '対象プロジェクトのVisual C++ 6.0 workspaceファイルです。',
      effectiveValue: settings.dswPath,
      configuredValue: nonEmptyString(raw.dswPath) ?? '',
      defaulted: false,
      actions: [
        { id: 'pickDswPath', kind: 'pickFile', label: '.dswを選択', primary: true },
        { id: 'inputDswPath', kind: 'inputText', label: 'パスを入力' },
      ],
    },
    {
      id: 'outputRoot',
      label: '出力ルート',
      settingKey: 'unitTestRunner.outputRoot',
      description: 'dossierやテスト設計などの生成物を書き出す外部フォルダです。',
      effectiveValue: settings.outputRoot,
      configuredValue: nonEmptyString(raw.outputRoot) ?? '',
      defaulted: false,
      actions: [
        { id: 'pickOutputRoot', kind: 'pickFolder', label: '出力フォルダを選択', primary: true },
        { id: 'inputOutputRoot', kind: 'inputText', label: 'パスを入力' },
      ],
    },
    {
      id: 'defaultConfiguration',
      label: '既定構成',
      settingKey: 'unitTestRunner.defaultConfiguration',
      description: '解析時に既定で渡すVC6構成名です。',
      effectiveValue: settings.defaultConfiguration,
      configuredValue: configuredDefaultConfiguration,
      defaulted: !configuredDefaultConfiguration,
      actions: [
        { id: 'inputDefaultConfiguration', kind: 'inputText', label: '構成名を入力', primary: true },
        { id: 'resetDefaultConfiguration', kind: 'reset', label: '既定値に戻す' },
      ],
    },
    {
      id: 'defaultProject',
      label: '既定プロジェクト',
      settingKey: 'unitTestRunner.defaultProject',
      description: 'ソースが複数プロジェクトに属する場合の既定プロジェクト名です。',
      effectiveValue: settings.defaultProject ?? '',
      configuredValue: configuredDefaultProject,
      defaulted: false,
      optional: true,
      actions: [
        { id: 'inputDefaultProject', kind: 'inputText', label: 'プロジェクト名を入力', primary: true },
        { id: 'resetDefaultProject', kind: 'reset', label: 'クリア' },
      ],
    },
    {
      id: 'vcvarsPath',
      label: 'VC6 vcvars32.bat',
      settingKey: 'unitTestRunner.vcvarsPath',
      description: 'ビルドプローブ実行前に呼び出すVC6環境設定バッチです。nmake/clがPATHに無い場合に指定します。',
      effectiveValue: settings.vcvarsPath ?? '',
      configuredValue: configuredVcvarsPath,
      defaulted: false,
      optional: true,
      advanced: true,
      actions: [
        { id: 'pickVcvarsPath', kind: 'pickFile', label: 'batを選択', primary: true },
        { id: 'inputVcvarsPath', kind: 'inputText', label: 'パスを入力' },
        { id: 'resetVcvarsPath', kind: 'reset', label: 'クリア' },
      ],
    },
    {
      id: 'cliPath',
      label: 'CLI実行ファイル',
      settingKey: 'unitTestRunner.cliPath',
      description: '通常は同梱CLIを使います。外部exeを使う場合だけ指定します。',
      effectiveValue: configuredCliPath || DEFAULT_CLI_PATH,
      configuredValue: configuredCliPath,
      defaulted: !configuredCliPath,
      advanced: true,
      actions: [
        { id: 'pickCliPath', kind: 'pickFile', label: 'exeを選択' },
        { id: 'inputCliPath', kind: 'inputText', label: 'パスを入力' },
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

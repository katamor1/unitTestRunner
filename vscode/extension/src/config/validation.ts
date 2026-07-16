import { isPathInside } from '../platform/pathDialect';
import { AdapterSettings } from './settings';

export interface SettingsValidationWarning {
  code: string;
  message: string;
}

export interface SettingsValidationResult {
  ok: boolean;
  warnings: SettingsValidationWarning[];
}

export function validateSettings(settings: AdapterSettings): SettingsValidationResult {
  const warnings: SettingsValidationWarning[] = [];
  if (!settings.cliPath) {
    warnings.push({ code: 'missing_cli_path', message: 'UnitTestRunnerの実行ファイルが設定されていません。' });
  }
  if (!settings.sourceRoot) {
    warnings.push({ code: 'missing_source_root', message: 'ソースのルートフォルダーが設定されていません。' });
  }
  if (!settings.dswPath) {
    warnings.push({ code: 'missing_dsw_path', message: 'VC6ワークスペースファイル（.dsw）が設定されていません。' });
  }
  if (!settings.outputRoot) {
    warnings.push({ code: 'missing_output_root', message: '出力先フォルダーが設定されていません。' });
  }
  if (settings.sourceRoot && settings.outputRoot && isPathInside(settings.outputRoot, settings.sourceRoot)) {
    warnings.push({ code: 'output_root_inside_source_root', message: '出力先フォルダーがソースのルートフォルダー内にあります。生成物が本番ソースへ混在する可能性があります。別のフォルダーを指定してください。' });
  }
  if (settings.sourceRoot && settings.quickOutputRoot && isPathInside(settings.quickOutputRoot, settings.sourceRoot)) {
    warnings.push({ code: 'quick_output_root_inside_source_root', message: 'クイックチェックの出力先がソースのルートフォルダー内にあります。生成物が本番ソースへ混在する可能性があります。別のフォルダーを指定してください。' });
  }
  return { ok: !warnings.some((warning) => warning.code.startsWith('missing_')), warnings };
}

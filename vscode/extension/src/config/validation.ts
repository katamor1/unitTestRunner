import * as path from 'path';

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
    warnings.push({ code: 'missing_cli_path', message: 'unitTestRunner.cliPath が未設定です。' });
  }
  if (!settings.sourceRoot) {
    warnings.push({ code: 'missing_source_root', message: 'unitTestRunner.sourceRoot が未設定です。' });
  }
  if (!settings.dswPath) {
    warnings.push({ code: 'missing_dsw_path', message: 'unitTestRunner.dswPath が未設定です。' });
  }
  if (!settings.outputRoot) {
    warnings.push({ code: 'missing_output_root', message: 'unitTestRunner.outputRoot が未設定です。' });
  }
  if (settings.sourceRoot && settings.outputRoot && isSubPath(settings.outputRoot, settings.sourceRoot)) {
    warnings.push({ code: 'output_root_inside_source_root', message: 'unitTestRunner.outputRoot が sourceRoot 配下です。本番リポジトリへ生成物が混入する可能性があります。' });
  }
  if (settings.sourceRoot && settings.quickOutputRoot && isSubPath(settings.quickOutputRoot, settings.sourceRoot)) {
    warnings.push({ code: 'quick_output_root_inside_source_root', message: 'unitTestRunner.quickOutputRoot が sourceRoot 配下です。Quick Check生成物が本番リポジトリへ混入する可能性があります。' });
  }
  return { ok: !warnings.some((warning) => warning.code.startsWith('missing_')), warnings };
}

function isSubPath(candidate: string, root: string): boolean {
  const relative = path.relative(path.resolve(root), path.resolve(candidate));
  return relative === '' || (!!relative && !relative.startsWith('..') && !path.isAbsolute(relative));
}

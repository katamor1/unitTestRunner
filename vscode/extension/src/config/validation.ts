import * as fs from 'fs';
import * as path from 'path';

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
  return { ok: !warnings.some((warning) => warning.code.startsWith('missing_')), warnings };
}

export function preflightInvocation(settings: AdapterSettings, sourcePath?: string): SettingsValidationResult {
  const warnings = [...validateSettings(settings).warnings];
  if (!Number.isFinite(settings.commandTimeoutSeconds) || settings.commandTimeoutSeconds <= 0) {
    warnings.push({ code: 'invalid_timeout', message: 'CLIのタイムアウトは0より大きい有限値にしてください。' });
  }
  if (settings.cliPath && !resolveExecutable(settings.cliPath)) {
    warnings.push({ code: 'cli_not_executable', message: 'UnitTestRunner CLIを実行可能ファイルとして確認できません。' });
  }
  if (settings.sourceRoot && !isDirectory(settings.sourceRoot)) {
    warnings.push({ code: 'source_root_not_directory', message: 'ソースのルートフォルダーが存在しません。' });
  }
  if (settings.dswPath && !isFile(settings.dswPath)) {
    warnings.push({ code: 'dsw_not_file', message: 'VC6ワークスペースファイルが存在しません。' });
  }
  if (sourcePath) {
    if (!isFile(sourcePath)) {
      warnings.push({ code: 'source_not_file', message: '対象ソースファイルが存在しません。' });
    }
    if (settings.sourceRoot && !isPathInside(sourcePath, settings.sourceRoot)) {
      warnings.push({ code: 'source_outside_root', message: '対象ソースは選択中のソースルート外です。' });
    }
  }
  if (settings.outputRoot) {
    if (settings.sourceRoot && isPathInside(settings.outputRoot, settings.sourceRoot)) {
      warnings.push({ code: 'output_root_inside_source_root', message: '出力先はソースルート外にしてください。' });
    } else if (!writableOutputBoundary(settings.outputRoot)) {
      warnings.push({ code: 'output_root_not_writable', message: '出力先または最寄りの既存親へ書き込めません。' });
    }
  }
  return { ok: warnings.length === 0, warnings: deduplicateWarnings(warnings) };
}

function resolveExecutable(value: string): string | undefined {
  if (path.isAbsolute(value) || value.includes('/') || value.includes('\\')) {
    return isFile(value) ? value : undefined;
  }
  const pathEntries = (process.env.PATH ?? '').split(path.delimiter).filter(Boolean);
  const extensions = process.platform === 'win32'
    ? (process.env.PATHEXT ?? '.EXE;.CMD;.BAT;.COM').split(';').filter(Boolean)
    : [''];
  for (const directory of pathEntries) {
    for (const extension of extensions) {
      const candidate = path.join(directory, value.toLowerCase().endsWith(extension.toLowerCase()) ? value : `${value}${extension}`);
      if (isFile(candidate)) {
        return candidate;
      }
    }
  }
  return undefined;
}

function writableOutputBoundary(value: string): boolean {
  let candidate = path.resolve(value);
  while (!fs.existsSync(candidate)) {
    const parent = path.dirname(candidate);
    if (parent === candidate) {
      return false;
    }
    candidate = parent;
  }
  try {
    if (!fs.statSync(candidate).isDirectory()) {
      return false;
    }
    fs.accessSync(candidate, fs.constants.W_OK);
    return true;
  } catch {
    return false;
  }
}

function isFile(value: string): boolean {
  try {
    return fs.statSync(value).isFile();
  } catch {
    return false;
  }
}

function isDirectory(value: string): boolean {
  try {
    return fs.statSync(value).isDirectory();
  } catch {
    return false;
  }
}

function deduplicateWarnings(warnings: SettingsValidationWarning[]): SettingsValidationWarning[] {
  const seen = new Set<string>();
  return warnings.filter((warning) => {
    if (seen.has(warning.code)) {
      return false;
    }
    seen.add(warning.code);
    return true;
  });
}

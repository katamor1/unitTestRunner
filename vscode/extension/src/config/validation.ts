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
    warnings.push({ code: 'missing_cli_path', message: 'unitTestRunner.cliPath is empty.' });
  }
  if (!settings.sourceRoot) {
    warnings.push({ code: 'missing_source_root', message: 'unitTestRunner.sourceRoot is empty.' });
  }
  if (!settings.dswPath) {
    warnings.push({ code: 'missing_dsw_path', message: 'unitTestRunner.dswPath is empty.' });
  }
  if (!settings.outputRoot) {
    warnings.push({ code: 'missing_output_root', message: 'unitTestRunner.outputRoot is empty.' });
  }
  if (settings.sourceRoot && settings.outputRoot && isSubPath(settings.outputRoot, settings.sourceRoot)) {
    warnings.push({ code: 'output_root_inside_source_root', message: 'unitTestRunner.outputRoot is inside sourceRoot; production repository pollution is possible.' });
  }
  return { ok: !warnings.some((warning) => warning.code.startsWith('missing_')), warnings };
}

function isSubPath(candidate: string, root: string): boolean {
  const relative = path.relative(path.resolve(root), path.resolve(candidate));
  return relative === '' || (!!relative && !relative.startsWith('..') && !path.isAbsolute(relative));
}

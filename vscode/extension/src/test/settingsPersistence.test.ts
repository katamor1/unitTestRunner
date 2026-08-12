import * as assert from 'assert';
import { it } from 'node:test';

import { buildSettingsViewModel } from '../config/settingsViewModel';
import { renderSettings } from '../workflow/settingsPanelRenderer';

it('renders resource-scoped settings as named controls without legacy aliases', () => {
  const model = buildSettingsViewModel({
    cliPath: 'unit-test-runner', sourceRoot: 'C:\\work', dswPath: 'C:\\work\\P.dsw',
    outputRoot: 'D:\\out', defaultConfiguration: 'Win32 Debug', defaultProject: 'Control',
    workspaceRoot: 'C:\\legacy', projectName: 'Legacy',
  }, 'C:\\default');
  const html = renderSettings(model);
  assert.equal(model.fields.find((field) => field.id === 'sourceRoot')?.effectiveValue, 'C:\\work');
  assert.equal(model.fields.find((field) => field.id === 'defaultProject')?.effectiveValue, 'Control');
  assert.match(html, /<details id="unitTestRunnerSettings"/);
  assert.match(html, /data-focus-key="setting:sourceRoot:pickFolder"/);
  assert.doesNotMatch(html, /workspaceRoot|projectName/);
});

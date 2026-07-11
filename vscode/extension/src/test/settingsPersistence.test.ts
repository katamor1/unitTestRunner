import * as assert from 'assert';
import { it } from 'node:test';
import * as vm from 'node:vm';

import { buildSettingsViewModel } from '../config/settingsViewModel';
import { renderWorkflowHtml } from '../workflow/workflowPanel';
import { buildWorkflowStepViews, EMPTY_REPORT_AVAILABILITY, OPTIONAL_WORKFLOW_ACTIONS, WorkflowState } from '../workflow/workflowState';

interface FakeButton {
  dataset: Record<string, string>;
  classList: { toggle: (name: string, active?: boolean) => void };
  addEventListener: (event: string, listener: () => void) => void;
  click: () => void;
  setAttribute: () => void;
}

function fakeButton(dataset: Record<string, string>): FakeButton {
  let clickListener = () => {};
  return {
    dataset,
    classList: { toggle: () => {} },
    addEventListener: (event, listener) => {
      if (event === 'click') clickListener = listener;
    },
    click: () => clickListener(),
    setAttribute: () => {},
  };
}

it('restores settingsOpen and preserves it when panelMode changes', () => {
  const settings = buildSettingsViewModel(
    {
      cliPath: 'unit-test-runner',
      sourceRoot: 'C:\\work\\product',
      dswPath: 'C:\\work\\product\\Product.dsw',
      outputRoot: 'D:\\unit-test-output',
      defaultConfiguration: 'Win32 Debug',
    },
    'C:\\work\\product',
  );
  const state: WorkflowState = {
    settingsReady: true,
    functionName: 'Control_Update',
    outputWorkspace: 'D:\\unit-test-output\\Control_Update',
    completedStepIds: ['settings'],
  };
  const steps = buildWorkflowStepViews(state, EMPTY_REPORT_AVAILABILITY);
  const html = renderWorkflowHtml({} as never, state, settings, steps, OPTIONAL_WORKFLOW_ACTIONS);
  assert.match(html, /<details id="unitTestRunnerSettings" class="settings">/);
  const script = html.match(/<script nonce="[^"]+">([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script);

  let webviewState: Record<string, unknown> = { panelMode: 'full', settingsOpen: true };
  const settingsListeners = new Map<string, () => void>();
  const settingsElement = {
    open: false,
    addEventListener: (event: string, listener: () => void) => settingsListeners.set(event, listener),
  };
  const simpleModeButton = fakeButton({ viewMode: 'simple' });
  const fullModeButton = fakeButton({ viewMode: 'full' });
  const document = {
    getElementById: (id: string) => {
      if (id === 'unitTestRunnerSettings') return settingsElement;
      if (id === 'simplePanel' || id === 'fullPanel') return { classList: { toggle: () => {} } };
      return undefined;
    },
    querySelectorAll: (selector: string) => selector === 'button[data-view-mode]' ? [simpleModeButton, fullModeButton] : [],
  };

  vm.runInNewContext(script, {
    acquireVsCodeApi: () => ({
      getState: () => webviewState,
      setState: (next: Record<string, unknown>) => { webviewState = next; },
      postMessage: () => {},
    }),
    document,
  });

  assert.equal(settingsElement.open, true);
  settingsElement.open = false;
  settingsListeners.get('toggle')?.();
  assert.deepEqual(webviewState, { panelMode: 'full', settingsOpen: false });
  simpleModeButton.click();
  assert.deepEqual(webviewState, { panelMode: 'simple', settingsOpen: false });
});

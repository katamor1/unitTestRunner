import * as assert from 'assert';
import * as vscode from 'vscode';

import { UNIT_TEST_RUNNER_COMMAND_IDS } from '../../commands/commandRegistry';
import { deactivate } from '../../extension';


export async function run(): Promise<void> {
  const extension = vscode.extensions.getExtension('local.unit-test-runner-vscode');
  assert.ok(extension, 'Unit Test Runner extension must be installed in the test host.');

  await extension.activate();
  assert.equal(extension.isActive, true);

  const registered = new Set(await vscode.commands.getCommands(true));
  for (const command of UNIT_TEST_RUNNER_COMMAND_IDS) {
    assert.ok(registered.has(command), `Expected registered command: ${command}`);
  }

  deactivate();
}

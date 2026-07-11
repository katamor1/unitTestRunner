import * as assert from 'assert';
import * as fs from 'fs';
import * as path from 'path';
import { describe, it } from 'node:test';

import {
  CommandHandler,
  CommandRegistry,
  registerUnitTestRunnerCommands,
  UNIT_TEST_RUNNER_COMMAND_IDS,
  UnitTestRunnerCommandHandlers,
} from '../commands/commandRegistry';
import { createQuickCommandHandlers } from '../commands/quickCommands';
import { QuickCheckProfile } from '../cli/commandBuilder';


describe('extension command registry', () => {
  it('registers every manifest command exactly once and no undeclared command', () => {
    const manifest = JSON.parse(
      fs.readFileSync(path.resolve(__dirname, '../../package.json'), 'utf8'),
    ) as { contributes: { commands: Array<{ command: string }> } };
    const manifestIds = manifest.contributes.commands.map((item) => item.command).sort();
    const registrations = new Map<string, number>();
    const registry: CommandRegistry = {
      registerCommand(command: string, _handler: CommandHandler) {
        registrations.set(command, (registrations.get(command) ?? 0) + 1);
        return { dispose() {} };
      },
    };
    const handlers = Object.fromEntries(
      UNIT_TEST_RUNNER_COMMAND_IDS.map((command) => [command, () => undefined]),
    ) as UnitTestRunnerCommandHandlers;

    const disposables = registerUnitTestRunnerCommands(
      { subscriptions: [] },
      { registry, handlers },
    );

    assert.deepEqual([...registrations.keys()].sort(), manifestIds);
    assert.equal(disposables.length, manifestIds.length);
    for (const command of manifestIds) {
      assert.equal(registrations.get(command), 1, command);
    }
  });

  for (const profile of ['design', 'harness', 'build-dry-run'] as QuickCheckProfile[]) {
    it(`preserves the selected ${profile} Quick profile in the actual command handler`, async () => {
      const executed: QuickCheckProfile[] = [];
      const errors: string[] = [];
      const handlers = createQuickCommandHandlers({
        getQuickProfile: () => profile,
        runQuickCheck: async (selected) => {
          executed.push(selected);
        },
        openGeneratedTestSource: async () => undefined,
        openQuickSummary: async () => undefined,
        runFullGate: async () => undefined,
        showError: (message) => errors.push(message),
      });

      await handlers['unitTestRunner.quickCheckCurrentFunction']();

      assert.deepEqual(executed, [profile]);
      assert.deepEqual(errors, []);
    });
  }
});

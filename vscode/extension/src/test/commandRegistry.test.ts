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

describe('extension command registry', () => {
  it('registers every declared v0.1 command exactly once', () => {
    const manifest = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../package.json'), 'utf8')) as { contributes: { commands: Array<{ command: string }> } };
    const manifestIds = manifest.contributes.commands.map((item) => item.command).sort();
    const registrations = new Map<string, number>();
    const registry: CommandRegistry = {
      registerCommand(command: string, _handler: CommandHandler) {
        registrations.set(command, (registrations.get(command) ?? 0) + 1);
        return { dispose() {} };
      },
    };
    const handlers = Object.fromEntries(UNIT_TEST_RUNNER_COMMAND_IDS.map((command) => [command, () => undefined])) as UnitTestRunnerCommandHandlers;
    registerUnitTestRunnerCommands({ subscriptions: [] }, { registry, handlers });
    assert.deepEqual([...UNIT_TEST_RUNNER_COMMAND_IDS].sort(), manifestIds);
    assert.equal(manifestIds.length, 16);
    assert.equal(manifestIds.some((id) => /quick|Evidence|generateTestDesign|generateHarnessSkeleton|Dashboard/.test(id)), false);
    for (const command of manifestIds) assert.equal(registrations.get(command), 1, command);
  });
});

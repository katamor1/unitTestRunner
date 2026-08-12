export interface Disposable {
  dispose(): unknown;
}

export type CommandHandler = (...args: unknown[]) => unknown;

export interface CommandRegistry {
  registerCommand(command: string, handler: CommandHandler): Disposable;
}

export interface RegistrationContext {
  subscriptions: Disposable[];
}

export const UNIT_TEST_RUNNER_COMMAND_IDS = [
  'unitTestRunner.analyzeCurrentFunction',
  'unitTestRunner.analyzeSelectedFunction',
  'unitTestRunner.reanalyzeCurrentFunction',
  'unitTestRunner.finalizeDossier',
  'unitTestRunner.openFunctionDossier',
  'unitTestRunner.openReviewChecklist',
  'unitTestRunner.openTestInputEditor',
  'unitTestRunner.prepareHarness',
  'unitTestRunner.buildProbeDryRun',
  'unitTestRunner.runBuildProbe',
  'unitTestRunner.runTests',
  'unitTestRunner.registerCurrentFunctionInSuite',
  'unitTestRunner.runSelectedSuiteTests',
  'unitTestRunner.openSuiteRunReport',
  'unitTestRunner.openOutputWorkspace',
  'unitTestRunner.copyLastCommand',
] as const;

export type UnitTestRunnerCommandId = typeof UNIT_TEST_RUNNER_COMMAND_IDS[number];
export type UnitTestRunnerCommandHandlers = Record<UnitTestRunnerCommandId, CommandHandler>;

export interface CommandRegistrationDependencies {
  registry: CommandRegistry;
  handlers: UnitTestRunnerCommandHandlers;
}

export function registerUnitTestRunnerCommands(
  context: RegistrationContext,
  dependencies: CommandRegistrationDependencies,
): Disposable[] {
  void context;
  return UNIT_TEST_RUNNER_COMMAND_IDS.map((command) => {
    const handler = dependencies.handlers[command];
    if (typeof handler !== 'function') {
      throw new Error(`Missing command handler: ${command}`);
    }
    return dependencies.registry.registerCommand(command, handler);
  });
}

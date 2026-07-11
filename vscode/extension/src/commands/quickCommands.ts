import { QuickCheckProfile } from '../cli/commandBuilder';
import { CommandHandler } from './commandRegistry';


export type QuickCommandId =
  | 'unitTestRunner.quickCheckCurrentFunction'
  | 'unitTestRunner.quickCheckSelectedFunction'
  | 'unitTestRunner.openGeneratedTestSource'
  | 'unitTestRunner.openQuickSummary'
  | 'unitTestRunner.runFullGateForCurrentFunction';

export type QuickCommandHandlers = Record<QuickCommandId, CommandHandler>;

export interface QuickCommandDependencies {
  getQuickProfile(): QuickCheckProfile;
  runQuickCheck(profile: QuickCheckProfile): Promise<void>;
  openGeneratedTestSource(): Promise<void>;
  openQuickSummary(): Promise<void>;
  runFullGate(): Promise<void>;
  showError(message: string): void;
}

export function createQuickCommandHandlers(
  dependencies: QuickCommandDependencies,
): QuickCommandHandlers {
  const run = (action: () => Promise<void>) => async () => {
    try {
      await action();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      dependencies.showError(`UnitTestRunner: ${message}`);
    }
  };
  const quickCheck = () => dependencies.runQuickCheck(dependencies.getQuickProfile());
  return {
    'unitTestRunner.quickCheckCurrentFunction': run(quickCheck),
    'unitTestRunner.quickCheckSelectedFunction': run(quickCheck),
    'unitTestRunner.openGeneratedTestSource': run(dependencies.openGeneratedTestSource),
    'unitTestRunner.openQuickSummary': run(dependencies.openQuickSummary),
    'unitTestRunner.runFullGateForCurrentFunction': run(dependencies.runFullGate),
  };
}

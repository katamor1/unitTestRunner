export function commandRequiresConfirmation(command: string, options: { run?: boolean; dryRun?: boolean }): boolean {
  if (command === 'build-probe') {
    return options.run === true && options.dryRun !== true;
  }
  if (command === 'run-tests') {
    return options.run === true && options.dryRun !== true;
  }
  if (command === 'complete-build') {
    return true;
  }
  return false;
}

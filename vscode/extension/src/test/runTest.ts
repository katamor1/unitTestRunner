import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { runTests } from '@vscode/test-electron';


async function main(): Promise<void> {
  if (process.platform !== 'win32' && !process.env.TAR_OPTIONS) {
    process.env.TAR_OPTIONS = '--no-same-owner';
  }
  if (process.platform !== 'win32') {
    const testHome = path.join(os.tmpdir(), 'unit-test-runner-vscode-home');
    const cacheHome = path.join(testHome, '.cache');
    fs.mkdirSync(cacheHome, { recursive: true });
    process.env.HOME = testHome;
    process.env.XDG_CACHE_HOME = cacheHome;
  }
  const extensionDevelopmentPath = path.resolve(__dirname, '../..');
  const extensionTestsPath = path.resolve(__dirname, 'extensionHost', 'index');
  await runTests({
    version: '1.85.2',
    extensionDevelopmentPath,
    extensionTestsPath,
    launchArgs: ['--disable-extensions', '--disable-gpu', '--no-sandbox'],
  });
}

main().catch((error) => {
  console.error('Extension Host tests failed.');
  console.error(error);
  process.exitCode = 1;
});

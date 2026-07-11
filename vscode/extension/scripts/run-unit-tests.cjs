const { spawnSync } = require('node:child_process');
const { readdirSync } = require('node:fs');
const path = require('node:path');

const testDirectory = path.join(__dirname, '..', 'dist', 'test');
const testFiles = readdirSync(testDirectory, { withFileTypes: true })
  .filter((entry) => entry.isFile() && entry.name.endsWith('.test.js'))
  .map((entry) => path.join(testDirectory, entry.name))
  .sort();

if (testFiles.length === 0) {
  console.error(`No compiled unit tests found in ${testDirectory}`);
  process.exit(1);
}

const completed = spawnSync(process.execPath, ['--test', ...testFiles], {
  stdio: 'inherit',
});

if (completed.error) {
  throw completed.error;
}

process.exit(completed.status ?? 1);

const { spawnSync } = require('node:child_process');
const { readdirSync, rmSync, writeFileSync } = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const bootstrapPath = path.join(__dirname, 'apply-japanese-gui-copy.cjs');
const targetBranch = 'chore/japanese-gui-copy';
const shouldBootstrap = process.env.GITHUB_ACTIONS === 'true'
  && process.env.GITHUB_HEAD_REF === targetBranch;

function runBootstrap(mode, diagnosticPath) {
  const args = [bootstrapPath, mode];
  if (diagnosticPath) {
    args.push(diagnosticPath);
  }
  const completed = spawnSync(process.execPath, args, {
    cwd: path.join(__dirname, '..'),
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });
  if (completed.stdout) {
    process.stdout.write(completed.stdout);
  }
  if (completed.stderr) {
    process.stderr.write(completed.stderr);
  }
  if (completed.error) {
    throw completed.error;
  }
  return completed.status ?? 1;
}

if (shouldBootstrap) {
  const prepareStatus = runBootstrap('prepare');
  if (prepareStatus !== 0) {
    process.exit(prepareStatus);
  }
}

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
  encoding: 'utf8',
  maxBuffer: 64 * 1024 * 1024,
});

if (completed.stdout) {
  process.stdout.write(completed.stdout);
}
if (completed.stderr) {
  process.stderr.write(completed.stderr);
}
if (completed.error) {
  throw completed.error;
}

const testStatus = completed.status ?? 1;
if (shouldBootstrap && testStatus !== 0) {
  const diagnosticPath = path.join(os.tmpdir(), `japanese-gui-copy-tests-${process.pid}.log`);
  writeFileSync(
    diagnosticPath,
    [completed.stdout || '', completed.stderr || ''].filter(Boolean).join('\n'),
    'utf8',
  );
  runBootstrap('fail', diagnosticPath);
  rmSync(diagnosticPath, { force: true });
  process.exit(testStatus);
}

if (shouldBootstrap) {
  const finalizeStatus = runBootstrap('finalize');
  if (finalizeStatus !== 0) {
    process.exit(finalizeStatus);
  }
}

process.exit(testStatus);

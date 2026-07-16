const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const https = require('node:https');
const os = require('node:os');
const path = require('node:path');
const zlib = require('node:zlib');

const TARGET_BRANCH = 'chore/japanese-gui-copy';
const PATCH_BLOB_SHA = '80280b54dafb9a80e19f6af5973901c9e38aec1a';
const REPOSITORY = process.env.GITHUB_REPOSITORY || 'katamor1/unitTestRunner';
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EXTENSION_ROOT = path.join(REPO_ROOT, 'vscode', 'extension');
const FAILURE_LOG = path.join(REPO_ROOT, '.github', 'apply-japanese-gui-copy.log');
const RUNNER_PATH = path.join(EXTENSION_ROOT, 'scripts', 'run-unit-tests.cjs');
const SELF_PATH = __filename;

function run(command, args, options = {}) {
  const completed = spawnSync(command, args, {
    cwd: options.cwd || REPO_ROOT,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
    ...options,
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
  if ((completed.status ?? 1) !== 0) {
    const detail = [completed.stdout, completed.stderr].filter(Boolean).join('\n').trim();
    const error = new Error(`${command} ${args.join(' ')} failed with exit code ${completed.status ?? 'unknown'}.`);
    error.detail = detail;
    throw error;
  }
  return completed.stdout || '';
}

function runGit(args) {
  return run('git', args, { cwd: REPO_ROOT });
}

function downloadPatchBlob() {
  const options = {
    hostname: 'api.github.com',
    path: `/repos/${REPOSITORY}/git/blobs/${PATCH_BLOB_SHA}`,
    headers: {
      Accept: 'application/vnd.github+json',
      'User-Agent': 'unitTestRunner-japanese-gui-copy-bootstrap',
      'X-GitHub-Api-Version': '2022-11-28',
    },
  };
  return new Promise((resolve, reject) => {
    https.get(options, (response) => {
      const chunks = [];
      response.on('data', (chunk) => chunks.push(chunk));
      response.on('end', () => {
        const body = Buffer.concat(chunks).toString('utf8');
        if (response.statusCode !== 200) {
          reject(new Error(`GitHub blob download failed with HTTP ${response.statusCode}: ${body}`));
          return;
        }
        try {
          const payload = JSON.parse(body);
          const compressed = Buffer.from(String(payload.content || '').replace(/\s/g, ''), 'base64');
          resolve(zlib.gunzipSync(compressed));
        } catch (error) {
          reject(error);
        }
      });
    }).on('error', reject);
  });
}

function runPython(scriptPath) {
  const candidates = process.platform === 'win32'
    ? [['python', [scriptPath]], ['py', ['-3', scriptPath]]]
    : [['python3', [scriptPath]], ['python', [scriptPath]]];
  const failures = [];
  for (const [command, args] of candidates) {
    const completed = spawnSync(command, args, {
      cwd: REPO_ROOT,
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
    });
    if (completed.stdout) {
      process.stdout.write(completed.stdout);
    }
    if (completed.stderr) {
      process.stderr.write(completed.stderr);
    }
    if (!completed.error && completed.status === 0) {
      return;
    }
    failures.push(`${command}: ${completed.error?.message || `exit ${completed.status}`}\n${completed.stdout || ''}\n${completed.stderr || ''}`);
  }
  const error = new Error('Python patch script could not be executed successfully.');
  error.detail = failures.join('\n---\n');
  throw error;
}

function configureGitIdentity() {
  runGit(['config', 'user.name', 'github-actions[bot]']);
  runGit(['config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com']);
}

function persistFailure(stage, detail) {
  try {
    runGit(['reset', '--hard', 'HEAD']);
    runGit(['clean', '-fd']);
    fs.mkdirSync(path.dirname(FAILURE_LOG), { recursive: true });
    fs.writeFileSync(
      FAILURE_LOG,
      [`stage: ${stage}`, `branch: ${TARGET_BRANCH}`, '', detail || 'No additional diagnostic output was captured.', ''].join('\n'),
      'utf8',
    );
    configureGitIdentity();
    runGit(['add', FAILURE_LOG]);
    const diff = spawnSync('git', ['diff', '--cached', '--quiet'], { cwd: REPO_ROOT });
    if (diff.status !== 0) {
      runGit(['commit', '-m', 'chore: record Japanese GUI copy automation failure']);
      runGit(['push', 'origin', `HEAD:${TARGET_BRANCH}`]);
    }
  } catch (persistError) {
    process.stderr.write(`Unable to persist GUI-copy failure diagnostics: ${persistError.stack || persistError}\n`);
  }
}

async function prepare() {
  runGit(['fetch', '--no-tags', 'origin', `refs/heads/${TARGET_BRANCH}:refs/remotes/origin/${TARGET_BRANCH}`]);
  runGit(['checkout', '-B', TARGET_BRANCH, `refs/remotes/origin/${TARGET_BRANCH}`]);

  const script = await downloadPatchBlob();
  const scriptPath = path.join(os.tmpdir(), `apply-japanese-gui-copy-${process.pid}.py`);
  fs.writeFileSync(scriptPath, script);
  try {
    runPython(scriptPath);
  } finally {
    fs.rmSync(scriptPath, { force: true });
  }
  run('npm.cmd', ['run', 'compile'], { cwd: EXTENSION_ROOT });
}

function restoreOriginalRunner() {
  runGit(['fetch', '--no-tags', 'origin', 'main']);
  const completed = spawnSync('git', ['show', 'FETCH_HEAD:vscode/extension/scripts/run-unit-tests.cjs'], {
    cwd: REPO_ROOT,
    encoding: 'buffer',
    maxBuffer: 4 * 1024 * 1024,
  });
  if (completed.error) {
    throw completed.error;
  }
  if ((completed.status ?? 1) !== 0) {
    throw new Error(`Unable to restore the original test runner: ${completed.stderr?.toString('utf8') || ''}`);
  }
  fs.writeFileSync(RUNNER_PATH, completed.stdout);
}

function finalize() {
  restoreOriginalRunner();
  fs.rmSync(SELF_PATH, { force: true });
  fs.rmSync(FAILURE_LOG, { force: true });
  configureGitIdentity();
  runGit(['add', '-A']);
  const diff = spawnSync('git', ['diff', '--cached', '--quiet'], { cwd: REPO_ROOT });
  if (diff.status !== 0) {
    runGit(['commit', '-m', 'feat: improve Japanese GUI copy']);
    runGit(['push', 'origin', `HEAD:${TARGET_BRANCH}`]);
  }
}

async function main() {
  const mode = process.argv[2];
  try {
    if (mode === 'prepare') {
      await prepare();
      return;
    }
    if (mode === 'finalize') {
      finalize();
      return;
    }
    if (mode === 'fail') {
      const diagnosticPath = process.argv[3];
      const detail = diagnosticPath && fs.existsSync(diagnosticPath)
        ? fs.readFileSync(diagnosticPath, 'utf8')
        : 'The test process failed without a diagnostic file.';
      persistFailure('tests', detail);
      process.exitCode = 1;
      return;
    }
    throw new Error(`Unknown bootstrap mode: ${mode || '(missing)'}`);
  } catch (error) {
    const detail = [error.stack || String(error), error.detail || ''].filter(Boolean).join('\n\n');
    persistFailure(mode || 'unknown', detail);
    process.stderr.write(`${detail}\n`);
    process.exitCode = 1;
  }
}

main();

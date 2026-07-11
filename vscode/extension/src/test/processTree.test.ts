import * as assert from 'assert';
import * as fs from 'fs';
import { it } from 'node:test';
import * as os from 'os';
import * as path from 'path';

import { runCliInvocation } from '../cli/cliRunner';

function processExists(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === 'EPERM';
  }
}

async function waitForProcessesToExit(pids: number[], timeoutMs = 3000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (pids.every((pid) => !processExists(pid))) return true;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return pids.every((pid) => !processExists(pid));
}

it('terminates the CLI process tree before returning a timeout result', async () => {
  const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'unit-test-runner-cli-tree-'));
  const pidFile = path.join(fixtureRoot, 'pids.json');
  const script = [
    "const childProcess = require('child_process');",
    "const fs = require('fs');",
    `const pidFile = ${JSON.stringify(pidFile)};`,
    "const child = childProcess.spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });",
    "fs.writeFileSync(pidFile, JSON.stringify({ parent: process.pid, child: child.pid }));",
    "setInterval(() => {}, 1000);",
  ].join('\n');
  let pids: number[] = [];

  try {
    const result = await runCliInvocation({
      command: process.execPath,
      args: ['-e', script],
      workingDirectory: process.cwd(),
      displayCommand: 'node timeout-process-tree-fixture',
      timeoutSeconds: 0.5,
      requiresConfirmation: false,
    });

    assert.equal(result.timedOut, true);
    assert.equal(result.exitCode, null);
    const recorded = JSON.parse(fs.readFileSync(pidFile, 'utf-8')) as { parent: number; child: number };
    pids = [recorded.parent, recorded.child];
    assert.equal(await waitForProcessesToExit(pids), true, `processes still running after timeout: ${pids.filter(processExists).join(', ')}`);
  } finally {
    for (const pid of pids) {
      if (processExists(pid)) {
        try {
          process.kill(pid, 'SIGKILL');
        } catch {
          // Best-effort fixture cleanup.
        }
      }
    }
    fs.rmSync(fixtureRoot, { recursive: true, force: true });
  }
});

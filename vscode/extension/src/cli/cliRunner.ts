import * as childProcess from 'child_process';

import { CliInvocation } from './commandBuilder';

export interface CliResult {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  commandLine: string;
}

const PROCESS_GROUP_GRACE_MS = 250;
const TERMINATION_WAIT_MS = 2000;

export function runCliInvocation(invocation: CliInvocation): Promise<CliResult> {
  return new Promise((resolve, reject) => {
    const child = childProcess.spawn(invocation.command, invocation.args, {
      cwd: invocation.workingDirectory,
      shell: false,
      detached: process.platform !== 'win32',
      windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    let settled = false;
    let timeoutTriggered = false;

    const settle = (result: CliResult): void => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timeout);
      resolve(result);
    };

    const timeout = setTimeout(() => {
      if (settled || timeoutTriggered) {
        return;
      }
      timeoutTriggered = true;
      void terminateProcessTree(child)
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : String(error);
          stderr += `${stderr.endsWith('\n') || !stderr ? '' : '\n'}Process-tree termination warning: ${message}\n`;
        })
        .finally(() => {
          settle({ exitCode: null, stdout, stderr, timedOut: true, commandLine: invocation.displayCommand });
        });
    }, invocation.timeoutSeconds * 1000);

    child.stdout?.on('data', (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr?.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on('error', (error) => {
      if (timeoutTriggered) {
        stderr += `${stderr.endsWith('\n') || !stderr ? '' : '\n'}Process error during timeout cleanup: ${error.message}\n`;
        return;
      }
      if (!settled) {
        settled = true;
        clearTimeout(timeout);
        reject(error);
      }
    });
    child.on('close', (code) => {
      if (timeoutTriggered || settled) {
        return;
      }
      settle({ exitCode: code, stdout, stderr, timedOut: false, commandLine: invocation.displayCommand });
    });
  });
}

export async function terminateProcessTree(child: childProcess.ChildProcess): Promise<void> {
  const pid = child.pid;
  if (!pid) {
    child.kill('SIGKILL');
    return;
  }

  if (process.platform === 'win32') {
    const taskkillSucceeded = await runTaskkill(pid);
    if (!taskkillSucceeded && child.exitCode === null && child.signalCode === null) {
      child.kill('SIGKILL');
    }
  } else {
    signalProcessGroup(pid, 'SIGTERM');
    await delay(PROCESS_GROUP_GRACE_MS);
    signalProcessGroup(pid, 'SIGKILL');
  }

  if (await waitForClose(child, TERMINATION_WAIT_MS)) {
    return;
  }
  if (child.exitCode === null && child.signalCode === null) {
    child.kill('SIGKILL');
  }
  await waitForClose(child, PROCESS_GROUP_GRACE_MS);
}

function runTaskkill(pid: number): Promise<boolean> {
  return new Promise((resolve) => {
    const killer = childProcess.spawn('taskkill.exe', ['/PID', String(pid), '/T', '/F'], {
      windowsHide: true,
      stdio: 'ignore',
    });
    let finished = false;
    const finish = (value: boolean): void => {
      if (finished) {
        return;
      }
      finished = true;
      clearTimeout(timeout);
      resolve(value);
    };
    const timeout = setTimeout(() => {
      killer.kill('SIGKILL');
      finish(false);
    }, TERMINATION_WAIT_MS);
    killer.once('error', () => finish(false));
    killer.once('close', (code) => finish(code === 0));
  });
}

function signalProcessGroup(pid: number, signal: NodeJS.Signals): void {
  try {
    process.kill(-pid, signal);
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code !== 'ESRCH') {
      throw error;
    }
  }
}

function waitForClose(child: childProcess.ChildProcess, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) {
    return Promise.resolve(true);
  }
  return new Promise((resolve) => {
    let finished = false;
    const finish = (closed: boolean): void => {
      if (finished) {
        return;
      }
      finished = true;
      clearTimeout(timeout);
      child.removeListener('close', onClose);
      resolve(closed);
    };
    const onClose = (): void => finish(true);
    const timeout = setTimeout(() => finish(false), timeoutMs);
    child.once('close', onClose);
  });
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

import * as childProcess from 'child_process';

import { CliInvocation } from './commandBuilder';

export interface CliResult {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  commandLine: string;
}

export function runCliInvocation(invocation: CliInvocation): Promise<CliResult> {
  return new Promise((resolve, reject) => {
    const child = childProcess.spawn(invocation.command, invocation.args, {
      cwd: invocation.workingDirectory,
      shell: false,
    });
    let stdout = '';
    let stderr = '';
    let finished = false;
    const timeout = setTimeout(() => {
      if (!finished) {
        child.kill();
        finished = true;
        resolve({ exitCode: null, stdout, stderr, timedOut: true, commandLine: invocation.displayCommand });
      }
    }, invocation.timeoutSeconds * 1000);
    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.on('close', (code) => {
      if (finished) {
        return;
      }
      finished = true;
      clearTimeout(timeout);
      resolve({ exitCode: code, stdout, stderr, timedOut: false, commandLine: invocation.displayCommand });
    });
  });
}

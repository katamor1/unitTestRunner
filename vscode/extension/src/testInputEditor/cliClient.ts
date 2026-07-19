import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

import { runCliInvocation, CliResult } from '../cli/cliRunner';
import {
  buildApplyTestInputFormInvocation,
  buildGetTestInputFormInvocation,
  CliInvocation,
} from '../cli/commandBuilder';
import { AdapterSettings } from '../config/settings';
import {
  parseTestInputApplyEnvelope,
  parseTestInputCliError,
  parseTestInputFormEnvelope,
  TestInputApplyResult,
  TestInputChangeDraft,
  TestInputFormModel,
} from './contracts';

export interface TestInputFormClient {
  load(workspace: string, summaryOnly?: boolean): Promise<TestInputFormModel>;
  apply(workspace: string, revision: number, changes: readonly TestInputChangeDraft[]): Promise<TestInputApplyResult>;
}

export interface TestInputCliClientDependencies {
  settings: () => AdapterSettings;
  storageRoot: string;
  run?: (invocation: CliInvocation) => Promise<CliResult>;
  mkdir?: typeof fs.promises.mkdir;
  writeFile?: typeof fs.promises.writeFile;
  unlink?: typeof fs.promises.unlink;
  randomUUID?: () => string;
}

export class TestInputCliError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly commandLine?: string,
  ) {
    super(message);
    this.name = 'TestInputCliError';
  }
}

export class TestInputCliClient implements TestInputFormClient {
  private readonly run: (invocation: CliInvocation) => Promise<CliResult>;
  private readonly mkdir: typeof fs.promises.mkdir;
  private readonly writeFile: typeof fs.promises.writeFile;
  private readonly unlink: typeof fs.promises.unlink;
  private readonly randomUUID: () => string;

  constructor(private readonly dependencies: TestInputCliClientDependencies) {
    this.run = dependencies.run ?? runCliInvocation;
    this.mkdir = dependencies.mkdir ?? fs.promises.mkdir;
    this.writeFile = dependencies.writeFile ?? fs.promises.writeFile;
    this.unlink = dependencies.unlink ?? fs.promises.unlink;
    this.randomUUID = dependencies.randomUUID ?? crypto.randomUUID;
  }

  async load(workspace: string, summaryOnly = false): Promise<TestInputFormModel> {
    const invocation = buildGetTestInputFormInvocation(this.dependencies.settings(), workspace, summaryOnly);
    const result = await this.run(invocation);
    if (result.timedOut) {
      throw new TestInputCliError('timed_out', 'テスト入力フォームの取得がタイムアウトしました。', invocation.displayCommand);
    }
    if (result.exitCode !== 0) {
      throw cliFailure(parseJsonIfAvailable(result.stdout), result, invocation.displayCommand);
    }
    const parsed = parseJson(result.stdout, invocation.displayCommand);
    try {
      return parseTestInputFormEnvelope(parsed);
    } catch (error) {
      throw new TestInputCliError(
        'invalid_cli_response',
        `テスト入力フォームの応答を解釈できません: ${errorMessage(error)}`,
        invocation.displayCommand,
      );
    }
  }

  async apply(
    workspace: string,
    revision: number,
    changes: readonly TestInputChangeDraft[],
  ): Promise<TestInputApplyResult> {
    await this.mkdir(this.dependencies.storageRoot, { recursive: true });
    const requestPath = path.join(
      this.dependencies.storageRoot,
      `test-input-changes-${this.randomUUID()}.json`,
    );
    const payload = {
      schema_version: '1.0',
      changes: changes.map((change) => ({
        item_id: change.itemId,
        subject_fingerprint: change.subjectFingerprint,
        values: { ...change.values },
        confirmed: change.confirmed,
      })),
    };
    await this.writeFile(requestPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
    const invocation = buildApplyTestInputFormInvocation(
      this.dependencies.settings(),
      workspace,
      requestPath,
      revision,
    );
    try {
      const result = await this.run(invocation);
      if (result.timedOut) {
        throw new TestInputCliError('timed_out', 'テスト入力の保存がタイムアウトしました。', invocation.displayCommand);
      }
      if (result.exitCode !== 0) {
        throw cliFailure(parseJsonIfAvailable(result.stdout), result, invocation.displayCommand);
      }
      const parsed = parseJson(result.stdout, invocation.displayCommand);
      try {
        return parseTestInputApplyEnvelope(parsed);
      } catch (error) {
        throw new TestInputCliError(
          'invalid_cli_response',
          `保存結果を解釈できません: ${errorMessage(error)}`,
          invocation.displayCommand,
        );
      }
    } finally {
      try {
        await this.unlink(requestPath);
      } catch (error) {
        const code = (error as NodeJS.ErrnoException).code;
        if (code !== 'ENOENT') {
          // A stale request file is safer than masking the canonical save result.
        }
      }
    }
  }
}

function parseJsonIfAvailable(stdout: string): unknown {
  const trimmed = stdout.trim();
  if (!trimmed) {
    return undefined;
  }
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return undefined;
  }
}

function parseJson(stdout: string, commandLine: string): unknown {
  try {
    return JSON.parse(stdout) as unknown;
  } catch (error) {
    throw new TestInputCliError(
      'invalid_cli_response',
      `CLIのJSON出力を解釈できません: ${errorMessage(error)}`,
      commandLine,
    );
  }
}

function cliFailure(parsed: unknown, result: CliResult, commandLine: string): TestInputCliError {
  const structured = parseTestInputCliError(parsed);
  if (structured) {
    return new TestInputCliError(structured.code, structured.message, commandLine);
  }
  const detail = result.stderr.trim() || `CLIが終了コード ${result.exitCode ?? '不明'} で終了しました。`;
  return new TestInputCliError('cli_error', detail, commandLine);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

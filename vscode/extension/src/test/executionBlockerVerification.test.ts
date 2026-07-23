import * as assert from 'assert';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { describe, it } from 'node:test';

import { CliProducedArtifact } from '../cli/cliEnvelope';
import { HandledBlockedRunDetails } from '../testExecutionBlockers/contracts';
import { restoreLatestBlockedRun, verifyBlockedRunArtifacts } from '../testExecutionBlockers/verification';

function sha256(filePath: string): string {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function writeJson(filePath: string, value: unknown): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(value), 'utf8');
}

function envelope(kind: string, subject: Record<string, string>, data: Record<string, unknown>) {
  return {
    artifact_kind: kind,
    schema_version: '1.0.0',
    producer: { name: 'unit-test-runner', version: '0.1.0', commit: 'test-commit' },
    subject,
    data,
    extensions: {},
  };
}

function fixture(workspace: string) {
  const runId = 'run-001';
  const runRoot = path.join(workspace, 'runs', runId);
  fs.mkdirSync(runRoot, { recursive: true });
  const subject = {
    function_id: 'fn_sample',
    source_path: 'src/sample.c',
    source_sha256: 'a'.repeat(64),
  };
  const executionRelative = `runs/${runId}/test_execution_report.json`;
  const executionPath = path.join(workspace, ...executionRelative.split('/'));
  writeJson(executionPath, envelope('test_execution_report', subject, {
    function: { name: 'sample', status: 'blocked' },
  }));
  const executionHash = sha256(executionPath);
  const blockerRelative = `runs/${runId}/test_execution_blockers.json`;
  const blockerMarkdownRelative = `runs/${runId}/test_execution_blockers.md`;
  const blockerPath = path.join(workspace, ...blockerRelative.split('/'));
  const blockerMarkdownPath = path.join(workspace, ...blockerMarkdownRelative.split('/'));
  writeJson(blockerPath, envelope('test_execution_blocker_report', subject, {
    run_id: runId,
    execution_status: 'blocked',
    execution_report: {
      artifact_kind: 'test_execution_report',
      path: executionRelative,
      sha256: executionHash,
    },
    blocker_count: 1,
    primary_action: {
      code: 'open_test_input_editor',
      label: '未確定項目を入力',
      affected_count: 1,
    },
    blockers: [
      {
        blocker_id: 'BLK-001',
        source_artifact: 'reports/test_spec.json',
        recommended_action: { code: 'open_test_input_editor', label: '未確定項目を入力' },
      },
    ],
  }));
  fs.writeFileSync(blockerMarkdownPath, '# blockers\n', 'utf8');
  return {
    runId,
    subject,
    executionRelative,
    executionPath,
    executionHash,
    blockerRelative,
    blockerMarkdownRelative,
    blockerPath,
    blockerMarkdownPath,
  };
}

describe('execution blocker artifact verification', () => {
  it('verifies immediate blocker artifacts and their execution report reference', () => {
    const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'utr-blocker-'));
    try {
      const files = fixture(workspace);
      const details: HandledBlockedRunDetails = {
        runId: files.runId,
        count: 1,
        primaryAction: 'open_test_input_editor',
        primaryActionLabel: '未確定項目を入力',
        runJson: files.blockerRelative,
        runMarkdown: files.blockerMarkdownRelative,
        publicationDiagnostics: [],
      };
      const artifacts: CliProducedArtifact[] = [
        {
          artifactKind: 'test_execution_blocker_report',
          path: files.blockerRelative,
          exists: true,
          sha256: sha256(files.blockerPath),
          schemaVersion: '1.0.0',
        },
        {
          artifactKind: 'test_execution_blocker_report_markdown',
          path: files.blockerMarkdownRelative,
          exists: true,
          sha256: sha256(files.blockerMarkdownPath),
          schemaVersion: null,
        },
        {
          artifactKind: 'test_execution_report',
          path: files.executionRelative,
          exists: true,
          sha256: files.executionHash,
          schemaVersion: '1.0.0',
        },
      ];

      const verified = verifyBlockedRunArtifacts(workspace, details, artifacts);

      assert.equal(verified.reportJson, files.blockerPath);
      assert.equal(verified.reportMarkdown, files.blockerMarkdownPath);
      assert.equal(verified.count, 1);
      assert.deepEqual(verified.publicationDiagnostics, []);
    } finally {
      fs.rmSync(workspace, { recursive: true, force: true });
    }
  });

  it('refuses a modified blocker artifact and falls back to the verified execution report', () => {
    const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'utr-blocker-'));
    try {
      const files = fixture(workspace);
      const details: HandledBlockedRunDetails = {
        runId: files.runId,
        count: 1,
        primaryAction: 'open_test_input_editor',
        primaryActionLabel: '未確定項目を入力',
        runJson: files.blockerRelative,
        runMarkdown: files.blockerMarkdownRelative,
        publicationDiagnostics: [],
      };
      const artifacts: CliProducedArtifact[] = [
        {
          artifactKind: 'test_execution_blocker_report',
          path: files.blockerRelative,
          exists: true,
          sha256: 'b'.repeat(64),
          schemaVersion: '1.0.0',
        },
        {
          artifactKind: 'test_execution_blocker_report_markdown',
          path: files.blockerMarkdownRelative,
          exists: true,
          sha256: sha256(files.blockerMarkdownPath),
          schemaVersion: null,
        },
        {
          artifactKind: 'test_execution_report',
          path: files.executionRelative,
          exists: true,
          sha256: files.executionHash,
          schemaVersion: '1.0.0',
        },
      ];

      const verified = verifyBlockedRunArtifacts(workspace, details, artifacts);

      assert.equal(verified.reportMarkdown, undefined);
      assert.equal(verified.primarySourcePath, files.executionPath);
      assert.ok(verified.publicationDiagnostics.some((item) => item.code === 'blocker_report_verification_failed'));
    } finally {
      fs.rmSync(workspace, { recursive: true, force: true });
    }
  });

  it('restores only a matching latest-run pointer and blocker hash', () => {
    const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'utr-blocker-'));
    try {
      const files = fixture(workspace);
      const pointerPath = path.join(workspace, 'reports', 'latest_run.json');
      writeJson(pointerPath, envelope('latest_run_pointer', files.subject, {
        run_id: files.runId,
        execution_report: {
          artifact_kind: 'test_execution_report',
          path: files.executionRelative,
          sha256: files.executionHash,
        },
        blocker_report: {
          artifact_kind: 'test_execution_blocker_report',
          path: files.blockerRelative,
          markdown_path: files.blockerMarkdownRelative,
          sha256: sha256(files.blockerPath),
        },
        updated_at: '2026-07-20T00:00:00.000Z',
      }));

      const restored = restoreLatestBlockedRun(workspace);
      assert.equal(restored?.runId, files.runId);
      assert.equal(restored?.reportMarkdown, files.blockerMarkdownPath);

      fs.appendFileSync(files.blockerPath, 'tampered', 'utf8');
      assert.equal(restoreLatestBlockedRun(workspace), undefined);
    } finally {
      fs.rmSync(workspace, { recursive: true, force: true });
    }
  });
});

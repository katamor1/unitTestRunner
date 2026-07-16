import * as assert from 'assert';
import * as fs from 'fs';
import { describe, it } from 'node:test';
import * as path from 'path';

import { buildSettingsViewModel } from '../config/settingsViewModel';
import { renderSettings } from '../workflow/settingsPanelRenderer';
import { renderWorkflowHtml } from '../workflow/workflowPanel';
import {
  buildWorkflowStepViews,
  EMPTY_REPORT_AVAILABILITY,
  OPTIONAL_WORKFLOW_ACTIONS,
  WorkflowState,
} from '../workflow/workflowState';

function settingsModel() {
  return buildSettingsViewModel(
    {
      cliPath: 'unit-test-runner',
      sourceRoot: 'C:\\work\\product',
      dswPath: 'C:\\work\\product\\Product.dsw',
      outputRoot: 'D:\\unit-test-output',
      defaultConfiguration: 'Win32 Debug',
      defaultProject: 'Control',
    },
    'C:\\work\\product',
  );
}

function fieldById(id: string) {
  const field = settingsModel().fields.find((item) => item.id === id);
  assert.ok(field, id);
  return field;
}

function source(relativePath: string): string {
  return fs.readFileSync(path.join(process.cwd(), relativePath), 'utf-8');
}

describe('Japanese GUI copy contract', () => {
  it('uses clear Japanese labels and descriptions in the settings panel', () => {
    assert.equal(fieldById('sourceRoot').label, 'ソースのルートフォルダー');
    assert.equal(fieldById('dswPath').label, 'VC6ワークスペースファイル（.dsw）');
    assert.equal(fieldById('outputRoot').label, '出力先フォルダー');
    assert.equal(fieldById('suiteManifestPath').label, 'スイート定義ファイル');
    assert.equal(fieldById('defaultConfiguration').label, '既定のビルド構成');
    assert.equal(fieldById('vcvarsPath').label, 'VC6環境設定ファイル');
    assert.match(fieldById('outputRoot').description, /出力先フォルダー/);
    assert.match(fieldById('suiteManifestPath').description, /スイート定義ファイル/);

    const html = renderSettings(settingsModel());
    assert.match(html, /必須項目はすべて設定されています。/);
    assert.doesNotMatch(html, /設定確認は完了しています。/);
  });

  it('uses Japanese workflow terminology without changing report file names', () => {
    const state: WorkflowState = {
      settingsReady: true,
      functionName: 'Control_Update',
      outputWorkspace: 'D:\\unit-test-output\\Control_Update',
      completedStepIds: ['settings'],
    };
    const steps = buildWorkflowStepViews(state, EMPTY_REPORT_AVAILABILITY);
    const html = renderWorkflowHtml({} as never, state, settingsModel(), steps, OPTIONAL_WORKFLOW_ACTIONS);

    assert.match(html, /クイックチェックを実行/);
    assert.match(html, /クイックチェックの概要を開く/);
    assert.match(html, /フルゲートへ進む/);
    assert.match(html, /出力ワークスペースを開く/);
    assert.match(html, /事前確認を実行/);
    assert.match(html, /function_dossier\.md/);
    assert.doesNotMatch(html, /出力workspace/);
    assert.doesNotMatch(html, /dry-runを実行/);
    assert.doesNotMatch(html, /Quick Summary/);
  });

  it('uses concrete Japanese actions and result labels in both suite views', () => {
    const panel = source(path.join('src', 'suite', 'suitePanel.ts'));
    const dashboard = source(path.join('src', 'suite', 'suiteDashboard.ts'));
    const combined = `${panel}\n${dashboard}`;

    for (const label of [
      '現在の関数をスイートに登録',
      'スイート一覧を開く',
      '選択したテストを実行',
      'タグを指定して実行',
      '全件テストを実行して合否を確認',
      'スイート定義ファイルを開く',
      '合計',
      '合格',
      '不合格',
      '実行済み',
      '実行結果',
      'ワークスペース',
    ]) {
      assert.match(combined, new RegExp(label));
    }

    assert.match(combined, /現在の関数をスイートに登録.*追加してください。/s);
    assert.doesNotMatch(combined, /広い一覧を開く/);
    assert.doesNotMatch(combined, /実行status/);
    assert.doesNotMatch(combined, /suite manifest未設定/);
    assert.doesNotMatch(combined, /Not GREEN/);
  });

  it('uses Japanese command palette, view, setting, dialog, and notification copy', () => {
    const packageJson = JSON.parse(source('package.json'));
    const commands = new Map<string, string>(
      packageJson.contributes.commands.map((item: { command: string; title: string }) => [item.command, item.title]),
    );
    const views = new Map<string, string>(
      packageJson.contributes.views.unitTestRunner.map((item: { id: string; name: string }) => [item.id, item.name]),
    );
    const properties = packageJson.contributes.configuration.properties as Record<string, { description: string }>;

    assert.equal(commands.get('unitTestRunner.quickCheckCurrentFunction'), 'UnitTestRunner: 現在の関数をクイックチェック');
    assert.equal(commands.get('unitTestRunner.quickCheckSelectedFunction'), 'UnitTestRunner: 選択した関数をクイックチェック');
    assert.equal(commands.get('unitTestRunner.runFullGateForCurrentFunction'), 'UnitTestRunner: 現在の関数でフルゲートを実行');
    assert.equal(commands.get('unitTestRunner.analyzeCurrentFunction'), 'UnitTestRunner: 現在の関数を解析');
    assert.equal(commands.get('unitTestRunner.openSuiteManifest'), 'UnitTestRunner: スイート定義ファイルを開く');
    assert.equal(commands.get('unitTestRunner.runAllSuiteTestsRequireGreen'), 'UnitTestRunner: 全件テストを実行して合否を確認');
    assert.equal(views.get('unitTestRunner.workflow'), '関数テスト');
    assert.equal(views.get('unitTestRunner.suite'), 'テストスイート');
    assert.doesNotMatch(properties['unitTestRunner.sourceRoot'].description, /workspace folder/);
    assert.doesNotMatch(properties['unitTestRunner.suiteManifestPath'].description, /スイートmanifest|manifestのパス/);

    const extension = source(path.join('src', 'extension.ts'));
    assert.match(extension, /'ビルドを実行'/);
    assert.match(extension, /'テストを実行'/);
    assert.match(extension, /'全件テストを実行'/);
    assert.match(extension, /合計\$\{summary\.total\}件のうち/);
    assert.doesNotMatch(extension, /'続行'/);
    assert.doesNotMatch(extension, /出力workspaceのパス/);
  });
});

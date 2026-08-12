import * as assert from 'assert';
import * as fs from 'fs';
import * as path from 'path';
import { describe, it } from 'node:test';

import { buildSettingsViewModel } from '../config/settingsViewModel';
import { renderSuiteHtml } from '../suite/suitePanel';
import { renderSettings } from '../workflow/settingsPanelRenderer';

function source(relative: string): string {
  return fs.readFileSync(path.join(process.cwd(), relative), 'utf8');
}

describe('Japanese v0.1 UI copy', () => {
  it('uses clear settings labels and no migration language', () => {
    const model = buildSettingsViewModel({
      cliPath: 'unit-test-runner', sourceRoot: 'C:\\work', dswPath: 'C:\\work\\P.dsw',
      outputRoot: 'D:\\out', defaultConfiguration: 'Win32 Debug',
    }, 'C:\\work');
    const html = renderSettings(model);
    for (const label of ['ソースのルートフォルダー', 'VC6ワークスペースファイル', '出力先フォルダー', 'スイート定義ファイル']) {
      assert.match(html, new RegExp(label));
    }
    assert.doesNotMatch(html, /旧設定|互換|migration/);
  });

  it('offers only register, explicit selection, enable, filter, run, and latest report in suite UI', () => {
    const html = renderSuiteHtml({
      suitePath: 'D:\\out\\suite_manifest.json', reportPath: 'D:\\out\\reports\\suite_run_report.json',
      reportExists: false, lastRunStatus: 'not_run', summary: { total: 0, green: 0, notGreen: 0, executed: 0, failed: 0 },
      entries: [{
        entryId: 'entry-1', enabled: true, selected: false, tags: ['smoke'], functionName: 'Control_Update',
        source: 'src/control.c', project: 'Control', configuration: 'Control - Win32 Debug', workspace: '../fn',
        lastRunStatus: 'not_run', greenStatus: 'not_run', executed: false, totalTests: 0, passedTests: 0,
        failedTests: 0, inconclusiveTests: 0, unresolvedReviewCount: 0, error: '',
      }],
    });
    for (const label of ['現在の関数をスイートに登録', '選択したテストを実行', '最新レポートを開く', '関数名またはタグで絞り込み', '実行対象', '有効']) {
      assert.match(html, new RegExp(label));
    }
    assert.match(html, /aria-label="実行対象を選択:/);
    assert.match(html, /aria-label="有効化:/);
    assert.doesNotMatch(html, /ダッシュボード|全件テスト|タグを指定して実行/);
  });

  it('declares only the thin adapter command and setting surface', () => {
    const manifest = JSON.parse(source('package.json')) as { contributes: { commands: Array<{ command: string; title: string }>; configuration: { properties: Record<string, unknown> } } };
    const ids = manifest.contributes.commands.map((item) => item.command);
    assert.equal(ids.length, 16);
    assert.equal(ids.includes('unitTestRunner.prepareHarness'), true);
    assert.equal(ids.includes('unitTestRunner.openTestInputEditor'), true);
    assert.equal(ids.some((id) => /quick|Evidence|generateTestDesign|generateHarnessSkeleton|Dashboard/.test(id)), false);
    const settings = Object.keys(manifest.contributes.configuration.properties);
    assert.equal(settings.length, 12);
    assert.equal(settings.some((key) => /workspaceRoot|projectName|quick|useJsonOutput|showOutputChannel/.test(key)), false);
  });
});

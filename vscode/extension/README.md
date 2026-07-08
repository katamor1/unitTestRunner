# Unit Test Runner

Visual C++ 6.0 / C90 の既存Cプロジェクトで、指定関数の単体テスト準備成果物を作るための VS Code 拡張です。

この拡張は Python CLI を呼び出す薄い adapter です。解析、dossier生成、テスト設計、build probe、エビデンス準備の本体処理は `unit-test-runner` CLI が担当します。Windows x64 向けVSIXでは、通常 `bin/win32-x64/unit-test-runner.exe` が同梱されるため、利用者がexe配置場所を個別に管理する必要はありません。

## 最初に行うこと

1. VS Codeで対象Cプロジェクトのルートフォルダを開きます。
2. Activity Bar の `Unit Test Runner` を開き、`Workflow` パネルを表示します。
3. パネル上部の `設定` で以下を指定します。各項目はファイル/フォルダ選択、または `パスを入力` で貼り付け入力できます。
   - `プロジェクトルート`: 未設定時はVS Codeで開いた先頭フォルダを使います。
   - `VC6 .dsw`: 対象プロジェクトの `.dsw` ファイルを選択します。
   - `出力ルート`: 本番ソースツリー外の生成物出力先を選択します。
   - `既定構成`: 例: `Win32 Debug`。
   - `既定プロジェクト`: ソースが複数プロジェクトに属する場合だけ指定します。
4. 設定はWorkspace設定へ保存されます。User設定には書きません。

## Quick Check

機能設計中に関数単位の動作確認を軽く反復したい場合は、エディタ右クリックまたはコマンドパレットから `UnitTestRunner: Quick Check Current Function` / `UnitTestRunner: Quick Check Selected Function` を実行します。

Quick Check は `analyze-function` を軽量 profile で呼び出し、`--finalize-dossier` を付けません。既定では `design` profile を使い、解析結果とテスト設計までを生成します。結果は `<outputRoot>/_quick/<source>_<function>_<hash>/reports/quick_summary.md` に整理されます。

`quick_summary.md` には、関数のグローバル read/write 数、外部呼び出し候補、分岐候補、カバレッジ観点、スタブ候補、diagnostics、主要レポートへのパスが短くまとまります。

レビュー前の正式確認へ進む場合は `UnitTestRunner: Full Gate for Current Function` を実行します。このコマンドは通常の出力workspaceで `--finalize-dossier` 付き解析を実行し、現行の dossier / review workflow をファイナルゲートとして使います。

Quick Check 用の主な設定:

```json
{
  "unitTestRunner.quickProfile": "design",
  "unitTestRunner.quickOutputRoot": "",
  "unitTestRunner.quickAutoOpenSummary": true
}
```

`quickProfile` は `design`、`harness`、`build-dry-run` から選べます。`build-dry-run` は build workspace / build probe dry-run までで、生成テストの実行は行いません。

## 関数解析

1. 対象の `.c` または `.cpp` ファイルを開きます。
2. 関数本文にカーソルを置くか、関数名を選択します。
3. エディタ右クリックから `UnitTestRunner: Analyze Current Function` または `UnitTestRunner: Analyze Selected Function` を実行します。
4. 解析後は `Workflow` パネルの強調表示に従って、dossier確認、レビュー項目確認、テスト設計生成、build probe、テスト実行、エビデンス確認へ進みます。

## Workflowパネル

パネルは上から下へ工程順に表示します。現在実行すべき工程は `現在の推奨` として強調されます。

パネルからレポートを開いた場合、対象ファイルを保存すると次工程へ進みます。編集不要の場合や保存検知できない場合は、`保存済みとして確定` を押します。

`Run Build Probe` と `Run Tests` は、既定で確認ダイアログを表示します。生成されたビルド手順やテストの実行を明示的に承認してから進めます。

## 主な設定

通常はパネルから設定します。手動でWorkspace設定を書く場合は以下の形です。

```json
{
  "unitTestRunner.sourceRoot": "D:/work/product",
  "unitTestRunner.dswPath": "D:/work/product/Product.dsw",
  "unitTestRunner.outputRoot": "D:/work/unit_test_workspace",
  "unitTestRunner.defaultConfiguration": "Win32 Debug",
  "unitTestRunner.defaultProject": "Control"
}
```

同梱CLIを使う場合、`unitTestRunner.cliPath` は設定不要です。外部CLIを使う場合だけ絶対パスを指定します。

```json
{
  "unitTestRunner.cliPath": "D:/tools/unitTestRunner/unit-test-runner.exe"
}
```

## トラブルシュート

| 症状 | 確認すること |
|---|---|
| Workflowパネルが表示されない | Activity Bar の `Unit Test Runner` を開き、拡張が有効か確認します。 |
| ビューのデータ提供者が未登録と表示される | VSIX更新直後の再読み込み不足の可能性があります。`Developer: Reload Window` またはVS Code再起動を行います。 |
| Quick Check summary が開かない | `UnitTestRunner: Open Quick Summary` を実行し、直近workspaceの `reports/quick_summary.md` が生成されているか確認します。 |
| 設定確認から進まない | `.dsw` と `outputRoot` が未設定でないか確認します。 |
| 生成物が本番ツリー内に出る | `outputRoot` / `quickOutputRoot` を `sourceRoot` の外側へ変更します。 |
| 関数名が解決されない | 関数名を選択して `Analyze Selected Function` または `Quick Check Selected Function` を実行します。 |
| CLIが見つからない | CLI同梱VSIXを使うか、外部CLIの絶対パスを `cliPath` に設定します。 |

詳細な利用手順はリポジトリの `docs/vscode_usage_guide.md` を参照してください。

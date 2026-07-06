# unitTestRunner VS Code利用手順書

作成日: 2026-07-06
対象版数: v0.1

## 1. 前提

本手順は、Windows上のVS Codeから `unitTestRunner` を利用し、VC6/C90プロジェクト内の指定関数についてdossierとレビュー成果物を生成するための手順である。

通常はCLI同梱VSIXを使う。VSIXに `bin/win32-x64/unit-test-runner.exe` が含まれている場合、利用者が `unit-test-runner.exe` の配置場所を個別に管理する必要はない。

必要なもの:

- VS Code
- `unit-test-runner-vscode-0.1.0.vsix`
- 対象VC6/C90プロジェクトのソースツリー
- 対象プロジェクトの `.dsw`
- 生成物を書き出す外部ワークスペース

## 2. VSIXをインストールする

PowerShellで以下を実行する。

```powershell
code --install-extension .\dist\unit-test-runner-vscode-0.1.0.vsix
```

インストール後、VS Codeを開き直す。コマンドパレットで `UnitTestRunner:` が候補に出ること、Activity Barに `Unit Test Runner` が表示されることを確認する。

## 3. 対象プロジェクトを開く

VS Codeで対象Cプロジェクトのルートフォルダを開く。通常は `.dsw` があるプロジェクトルート、またはその上位の製品ソースルートを開く。

生成物は本番ソースツリーに出さない。`outputRoot` には、対象プロジェクト外の作業ディレクトリを指定する。

例:

```text
D:\work\product              # sourceRoot
D:\work\product\Product.dsw  # dswPath
D:\work\unit_test_workspace  # outputRoot
```

## 4. Workflowパネルで設定する

Activity Barの `Unit Test Runner` を開き、`Workflow` パネル上部の `設定` で必要なパスを指定する。各項目はファイル/フォルダ選択、または `パスを入力` で貼り付け入力できる。

設定はWorkspace設定へ保存される。対象プロジェクトごとの `.code-workspace` またはフォルダ設定に残り、User設定には書かない。

設定する項目:

| 項目 | 内容 |
|---|---|
| プロジェクトルート | 本番ソースを読むルートフォルダ。未設定時は、VS Codeで開いた先頭workspace folder、単一フォルダを開いた場合はそのTOPフォルダを使う。 |
| VC6 .dsw | 対象プロジェクトの `.dsw` ファイル。 |
| 出力ルート | 生成物を書き出す外部フォルダ。本番ソースツリー外を指定する。 |
| 既定構成 | 例: `Win32 Debug`。 |
| 既定プロジェクト | ソースが複数プロジェクトに属する場合だけ指定する。 |
| CLI実行ファイル | 通常は設定しない。外部CLIを使う場合だけexeを指定する。 |

手動でWorkspace設定を書く場合は以下の形にする。

```json
{
  "unitTestRunner.sourceRoot": "D:/work/product",
  "unitTestRunner.dswPath": "D:/work/product/Product.dsw",
  "unitTestRunner.outputRoot": "D:/work/unit_test_workspace",
  "unitTestRunner.defaultConfiguration": "Win32 Debug",
  "unitTestRunner.defaultProject": "Control",
  "unitTestRunner.finalizeDossierAfterAnalyze": true,
  "unitTestRunner.useJsonOutput": true
}
```

CLI同梱VSIXを使う場合、`unitTestRunner.cliPath` は設定しない。パネルでも `既定値に戻す` を選ぶ。同梱CLIではなく外部に配置したCLIを使う場合だけ、以下のように絶対パスで指定する。

```json
{
  "unitTestRunner.cliPath": "D:/tools/unitTestRunner/unit-test-runner.exe"
}
```

旧設定名の `unitTestRunner.workspaceRoot` と `unitTestRunner.projectName` は互換用である。新規設定では `unitTestRunner.sourceRoot` と `unitTestRunner.defaultProject` を使う。

## 5. サイドパネルで工程を確認する

Activity Barの `Unit Test Runner` を開き、`Workflow` パネルを表示する。

パネル上部には現在の設定状態が表示される。未設定の必須項目がある場合は `設定確認` が現在の推奨工程になる。設定が揃うと、次の推奨工程は `関数解析` へ進む。

設定の下には、上から下へ以下の工程が表示される。

1. 設定確認
2. 関数解析
3. `function_dossier.md` 確認
4. `review_checklist.md` / `unresolved_items.md` / `next_actions.md` 確認
5. テスト設計生成
6. `test_case_design.csv` 確認
7. build probe dry-run
8. `build_probe_report.md` 確認
9. build probe実行
10. 生成テスト実行
11. エビデンス準備
12. 実行結果・エビデンス確認

現在実行すべき工程は `現在の推奨` として強調される。完了済み工程は `完了`、未到達工程は `未実施` と表示される。

## 6. 関数dossierを生成する

1. 対象の `.c` ファイルをVS Codeで開く。
2. 対象関数名を選択するか、関数本文内にカーソルを置く。
3. エディタ上で右クリックし、`UnitTestRunner: Analyze Current Function` または `UnitTestRunner: Analyze Selected Function` を実行する。
4. または、`Workflow` パネルの `現在関数を解析` / `選択関数を解析` ボタンを押す。
5. `unitTestRunner.finalizeDossierAfterAnalyze` が `true` の場合、解析後にレビュー用dossierまで確定される。
6. `unitTestRunner.autoOpenDossier` が `true` の場合、`function_dossier.md` が自動で開く。

代表的な出力先:

```text
<outputRoot>/<functionName>/
  input/request.json
  extracted/
  generated/
  reports/function_dossier.json
  reports/function_dossier.md
  reports/test_case_design.csv
  reports/review_checklist.md
  reports/unresolved_items.md
  reports/next_actions.md
```

## 7. 生成物を確認する

基本操作は `Workflow` パネルから行う。対象ファイルを開くボタンを押すと、パネルはそのファイルを保存待ちとして記録する。

ファイルを編集して保存すると、自動で次工程へ進む。編集不要の場合、または保存イベントを拾えない場合は、パネルの `保存済みとして確定` を押して次工程へ進める。

コマンドパレットから直接開く場合は以下を使う。

| 操作 | コマンド |
|---|---|
| function dossierを開く | `UnitTestRunner: Open Function Dossier` |
| review checklistを開く | `UnitTestRunner: Open Review Checklist` |
| next actionsを開く | `UnitTestRunner: Open Next Actions` |
| 生成workspaceをOSで開く | `UnitTestRunner: Open Output Workspace` |
| 最後に実行したCLIコマンドをコピーする | `UnitTestRunner: Copy Last CLI Command` |

`Copy Last CLI Command` は、VS Code上の実行内容をCLIで再現したい場合や、レビュー記録へ貼る場合に使う。

## 8. レビュー・テスト設計を更新する

解析済みworkspaceに対して、`Workflow` パネルの強調表示に従って以下を実行する。

| 目的 | コマンド |
|---|---|
| dossierを再確定する | `UnitTestRunner: Finalize Dossier` |
| テスト設計を生成する | `UnitTestRunner: Generate Test Design` |
| 変更後の関数を再解析する | `UnitTestRunner: Reanalyze Current Function` |
| 変更影響レポートを開く | `UnitTestRunner: Open Change Impact Report` |
| 回帰選定CSVを開く | `UnitTestRunner: Open Regression Selection` |

再解析は、前回の `reports/function_dossier.json` と `reports/test_case_design.json` を参照し、既存テスト設計の再利用候補や追加確認項目を整理する。

## 9. build probeとテスト実行

build/test系は生成ファイルや生成バイナリを扱うため、通常の解析より注意が必要である。

`Workflow` パネルでは、dry-run、report確認、実行、テスト、エビデンス準備の順にボタンが表示される。`Run Build Probe` と `Run Tests` は、既定で確認ダイアログを表示する。

| 目的 | コマンド | 確認 |
|---|---|---|
| build probeのdry-run | `UnitTestRunner: Build Probe Dry Run` | 実ビルドしない |
| build probeを実行 | `UnitTestRunner: Run Build Probe` | 確認ダイアログあり |
| 生成テストを実行 | `UnitTestRunner: Run Tests` | 確認ダイアログあり |
| エビデンスを準備 | `UnitTestRunner: Prepare Evidence` | 実行済みログやmanifestを整理 |

`Run Build Probe` と `Run Tests` は、設定により確認ダイアログを表示する。既定では確認が必要である。

## 10. 複数関数回帰スイート

仕様追加や仕様変更で複数関数を触る場合は、`スイート` パネルで関数workspaceを登録しておく。

| 目的 | コマンド |
|---|---|
| 現在関数をmanifestへ登録 | `UnitTestRunner: 現在関数をスイートに登録` |
| manifestを開く | `UnitTestRunner: スイートを開く` |
| チェックした関数だけ実行 | `UnitTestRunner: 選択したスイートテストを実行` |
| タグで実行 | `UnitTestRunner: タグ指定でスイートテストを実行` |
| 登録済み全件をGREEN判定 | `UnitTestRunner: スイート全件GREEN確認` |
| 実行レポートを開く | `UnitTestRunner: スイート実行レポートを開く` |

スイートの正本は `suite_manifest.json` である。未設定時は `unitTestRunner.outputRoot\suites\default\suite_manifest.json` を使う。標準RUNは選択またはタグ指定で行い、全件GREEN確認は明示コマンドだけで実行する。

CLIで再現する場合:

```powershell
py -m unit_test_runner --json suite-register --suite D:\work\unit_test_workspace\suites\default\suite_manifest.json --workspace D:\work\unit_test_workspace\Control_Update --tags regression,selected
py -m unit_test_runner --json suite-run --suite D:\work\unit_test_workspace\suites\default\suite_manifest.json --tag selected --run
py -m unit_test_runner --json suite-run --suite D:\work\unit_test_workspace\suites\default\suite_manifest.json --all --run --require-green
```

## 11. よくある設定例

### 11.1 CLI同梱VSIXを使う標準設定

```json
{
  "unitTestRunner.sourceRoot": "D:/work/product",
  "unitTestRunner.dswPath": "D:/work/product/Product.dsw",
  "unitTestRunner.outputRoot": "D:/work/unit_test_workspace",
  "unitTestRunner.suiteManifestPath": "D:/work/unit_test_workspace/suites/default/suite_manifest.json",
  "unitTestRunner.defaultConfiguration": "Win32 Debug",
  "unitTestRunner.defaultProject": "Control"
}
```

### 11.2 外部CLIを明示する設定

```json
{
  "unitTestRunner.cliPath": "D:/tools/unitTestRunner/unit-test-runner.exe",
  "unitTestRunner.sourceRoot": "D:/work/product",
  "unitTestRunner.dswPath": "D:/work/product/Product.dsw",
  "unitTestRunner.outputRoot": "D:/work/unit_test_workspace",
  "unitTestRunner.defaultConfiguration": "Win32 Debug"
}
```

### 10.3 build/test実行前に確認を維持する設定

```json
{
  "unitTestRunner.runBuildProbeRequiresConfirmation": true,
  "unitTestRunner.runTestsRequiresConfirmation": true
}
```

## 11. トラブルシュート

| 症状 | 確認内容 | 対処 |
|---|---|---|
| `UnitTestRunner:` コマンドが出ない | VSIXがインストール済みか | `code --install-extension ...` 後にVS Codeを再起動する |
| `Workflow` パネルが出ない | Activity Barの `Unit Test Runner` または拡張の有効状態 | VS Codeを再起動し、`Unit Test Runner` ビューを開く |
| `ビューのデータ提供者が登録されていません` と表示される | VSIX更新後に拡張hostが古い状態の可能性 | `Developer: Reload Window` またはVS Code再起動を行う |
| CLIが見つからない | VSIXに同梱exeが含まれるか、`cliPath` が誤っていないか | CLI同梱VSIXを作り直す。外部CLIを使う場合は絶対パスを設定する |
| `sourceRoot` が空というエラー | VS Codeで開いたフォルダと設定 | フォルダを開き直すか、パネルの `プロジェクトルート` で明示する |
| `.dsw` が見つからない | `unitTestRunner.dswPath` | パネルの `VC6 .dsw` で `.dsw` を選択する |
| 生成物が本番ツリー内に出る | `outputRoot` | パネルの `出力ルート` で `sourceRoot` の外側に変更する |
| 関数名が解決されない | 選択範囲またはカーソル位置 | 関数名を選択して `Analyze Selected Function` を実行する |
| レポートが開けない | 最後に解析したworkspace | `Open Output Workspace` で出力先を確認し、必要なら再解析する |
| 次工程へ進まない | 対象ファイルの保存または確定状態 | ファイルを保存するか、`保存済みとして確定` を押す |

## 12. 運用上の注意

- 本番ソースツリーへ生成物を置かない。
- `function_dossier.json` をレビューと後続コマンドの基準成果物として扱う。
- 期待値やスタブ動作は自動確定しない。`review_required` や `TBD` は人間が確認する。
- build/test実行系は、dry-runと実行を分けて扱う。

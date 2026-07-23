# unitTestRunner

`unitTestRunner` は、Visual C++ 6.0 / C90 で開発された既存Cプロジェクトに対して、関数単位の単体テスト準備情報を生成するためのツールです。

このリポジトリは [関数単位 VC6/C90 単体テスト支援ツール 企画・設計書](docs/function_level_vc6_unit_test_codex_design.md) の v0.1 範囲を実装しています。初期ゴールは完全な実行可能テストハーネスを自動生成することではありません。VC6プロジェクト情報と指定関数の解析結果を、本番ソースツリーの外側に、レビュー可能なJSON、Markdown、CSV成果物として出力します。

## 主要方針

- 本番リポジトリは読み取り専用入力として扱い、生成物は外部ワークスペースへ出力する
- モジュール単位ではなく、まず指定関数の dossier 生成を安定させる
- Python CLI core を中心に置き、VS Code拡張はCLIを呼び出す薄いadapterに限定する
- VC6/C90、Shift-JIS/CP932、古い `.dsw` / `.dsp` を通常ケースとして扱う
- AIや自動生成は候補作成に使い、最終判断はビルド、ログ、人間レビュー、エビデンスに置く

詳細は以下を参照してください。

- [基本設計書](docs/basic_design.md)
- [詳細設計書](docs/detailed_design.md)
- [テスト仕様書](docs/test_specification.md)
- [配布用バイナリ作成手順書](docs/distribution_binary_build_guide.md)
- [VS Code利用手順書](docs/vscode_usage_guide.md)
- [テスト入力編集GUI 利用手順](docs/test_input_editor.md)
- [v0.1スモークサンプル](docs/v0.1_smoke_sample.md)
- [VC6 DSW/DSPパース実機スモーク](docs/vc6_dsw_dsp_parse_smoke.md)

## 開発と検証

Python側の単体テストとCLIスモークを実行します。最初に、テスト用の追加依存関係を含めてeditable installします。

```powershell
py -m pip install -e ".[test]"
$env:PYTHONPATH = (Resolve-Path .\src).Path
$modules = Get-ChildItem -LiteralPath .\tests -Filter 'test_*.py' -File |
  Sort-Object Name |
  ForEach-Object { 'tests.' + $_.BaseName }
if ($modules.Count -eq 0) {
  throw 'isolated Python test discovery returned no modules'
}
$failed = @()
foreach ($module in $modules) {
  & py -m unittest $module -v
  if ($LASTEXITCODE -ne 0) { $failed += $module }
}
if ($failed.Count -ne 0) {
  throw ('isolated Python failures: ' + ($failed -join ', '))
}
```

インストールせずにチェックアウトからCLIを起動する場合は、`src` を `PYTHONPATH` に追加します。

```powershell
$env:PYTHONPATH = "$PWD\src"
py -m unit_test_runner --help
```

editable install または配布用バイナリ化後のコンソール入口は次の名前です。

```powershell
unit-test-runner --help
```

VS Code adapter は `vscode/extension` 配下で検証します。

```powershell
Push-Location vscode\extension
npm ci
npm.cmd test
Pop-Location
```

## 基本スモーク

小さなVC6風fixtureは `tests/fixtures/vc6_project` にあります。以下は `Control_Update` を対象に、プロジェクト発見、ソース所属判定、関数解析、build probe dry-run、テスト設計生成までを確認する流れです。

```powershell
$env:PYTHONPATH = "$PWD\src"
$fixture = "$PWD\tests\fixtures\vc6_project"
$out = "$env:TEMP\unitTestRunner-smoke\Control_Update"

py -m unit_test_runner discover-projects --workspace $fixture --dsw "$fixture\Product.dsw" --out "$env:TEMP\unitTestRunner-projects.json"
py -m unit_test_runner map-source --workspace $fixture --dsw "$fixture\Product.dsw" --source src\control.c
py -m unit_test_runner list-functions --source "$fixture\src\control.c"
py -m unit_test_runner analyze-function --workspace $fixture --dsw "$fixture\Product.dsw" --source src\control.c --function Control_Update --configuration "Win32 Debug" --project Control --out $out
py -m unit_test_runner build-probe --dossier "$out\reports\function_dossier.json" --dry-run
py -m unit_test_runner generate-test-design --dossier "$out\reports\function_dossier.json"
```

DSW/DSPパースだけを実機で確認し、JSON/Markdown成果物を残す場合は、以下のスモーク環境を使います。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_vc6_parse_smoke.ps1
```

詳細と実プロジェクトへの差し替え例は [VC6 DSW/DSPパース実機スモーク](docs/vc6_dsw_dsp_parse_smoke.md) を参照してください。

レビュー用に確定済みdossierを作る場合は `--finalize-dossier` を付けます。

```powershell
py -m unit_test_runner --json analyze-function --workspace $fixture --dsw "$fixture\Product.dsw" --source src\control.c --function Control_Update --configuration "Win32 Debug" --project Control --out $out --finalize-dossier
py -m unit_test_runner --json finalize-dossier --workspace $out
py -m unit_test_runner --json prepare-review --dossier "$out\reports\function_dossier.json"
py -m unit_test_runner --json run-tests --workspace $out --dry-run
py -m unit_test_runner --json prepare-evidence --workspace $out
```

主要な出力は以下です。

- `$out\input\request.json`
- `$out\extracted\`
- `$out\generated\`
- `$out\reports\function_dossier.json`
- `$out\reports\function_dossier.md`
- `$out\reports\test_spec.json`（canonical正本）
- `$out\reports\test_spec.md`（レビュー表示）
- `$out\reports\test_spec.csv`（一覧表示）
- `$out\reports\test_case_design.csv`
- `$out\generated\build\Makefile`
- `$out\reports\build_probe.log`
- `$out\reports\dossier_manifest.json`
- `$out\reports\traceability_matrix.csv`
- `$out\reports\review_checklist.md`
- `$out\reports\unresolved_items.md`
- `$out\reports\next_actions.md`

`function_dossier.json` は通常解析後もレビュー確定後も公開dossier成果物です。確定後も `target`、`project_membership`、`build_context`、`function`、`test_design`、`diagnostics` を維持し、`artifact_index`、`traceability`、`review_items`、`unresolved_items`、`next_actions`、`readiness` などのレビュー用情報を追加します。


## 依存関係ポリシーと衝突回避スタブ

関数解析では、テスト対象関数から各呼び出し先への関係を `reports/dependency_policy.json` と `reports/dependency_policy.md` に出力します。呼び出し先ごとの既定方針は次の3種類です。

- `real`: 実在する呼び出し先のC実装をテストworkspaceへ追加して実行する
- `stub`: 実関数と異なる生成シンボルを使い、戻り値や呼び出し回数をテスト側で制御する
- `auto`: 共有グローバル、ポインタ引数、副作用、実装の所在、機能境界の証拠から `real` / `stub` を解決する

`configured_mode` は利用者が指定した方針、`resolved_mode` は解析後の実効方針です。`auto` で安全に決定できない場合は `review_required` となり、勝手にリンク構成を決めません。明示的に変更する場合は、`dependency_policy.json` の対象エントリを編集してから Quick Check または関数解析を再実行し、`resolved_mode` と生成物を更新します。

```json
{
  "callee": "Helper_Update",
  "configured_mode": "real",
  "resolved_mode": "real"
}
```

通常は関係ごとの既定方針を継承します。特定のテストケースだけ切り替える場合は、canonical `test_spec.json` の `dependency_overrides` をテスト入力編集GUIから更新します。旧 `test_case_design.json` は後方互換の読み取りaliasです。

```json
{
  "test_case_id": "TC_ErrorPath",
  "dependency_overrides": [
    {
      "callee": "Helper_Update",
      "mode": "stub",
      "rationale": "異常戻り値を再現するため"
    }
  ]
}
```

生成コードは製品シンボルと同名のスタブを定義しません。抽出した対象Cの検証済み直接呼び出しだけを `Utr_Dep_<関数名>` へ書き換え、ディスパッチャが `real` または `Utr_Stub_<関数名>_Invoke` を選びます。本番ソースは変更しません。関数マクロ、関数ポインタ、構造体メンバ経由の呼び出し、関数アドレス利用は自動書き換えせず `review_required` にします。

外部グローバルはworkspace単位で `real` / `fixture` / `auto` を解決します。実定義が一意なら生成側で重複定義せず、宣言しかない場合だけ宣言互換のfixtureを1つ生成します。テストケース単位では結合先を切り替えず、同じオブジェクトの初期値・期待値だけを変更します。

CLIでハーネスだけを再生成する場合、`--dependency-policy` は任意です。省略時は `call_report.json` と同じ `reports` フォルダの `dependency_policy.json` を自動で読みます。

```powershell
py -m unit_test_runner --json generate-harness-skeleton `
  --function-signature "$out\reports\function_signature.json" `
  --global-access "$out\reports\global_access.json" `
  --call-report "$out\reports\call_report.json" `
  --test-spec "$out\reports\test_spec.json" `
  --dependency-policy "$out\reports\dependency_policy.json" `
  --out $out --overwrite
```

## 未確定テスト入力をGUIで反映する

`TBD_VALID_VALUE` などが残る場合、JSONを直接編集せずWorkflowパネルの `未確定項目を入力（N件）` を使用します。候補値を選んだ後もC式を自由編集でき、項目ごとに `確認済み` を明示します。部分保存が可能で、revisionまたはsubject fingerprintが変わった場合は下書きを保持したまま競合解決へ進みます。

CLIで確認する場合は次を使用します。

```powershell
py -m unit_test_runner --json get-test-input-form --workspace $out
py -m unit_test_runner --json apply-test-input-form --workspace $out --input $changes --expected-revision 3
```

詳細は [テスト入力編集GUI 利用手順](docs/test_input_editor.md) を参照してください。

## 実用fixture

より密な解析確認には `tests/fixtures/vc6_practical_project` を使います。`DeviceControl_Update` の周辺に、externグローバル、file-scope static、関数ポインタ、構造体メンバ、配列、function-like macro、複数関数の呼び出し木を含めています。

```powershell
$env:PYTHONPATH = "$PWD\src"
$fixture = "$PWD\tests\fixtures\vc6_practical_project"
$out = "$env:TEMP\unitTestRunner-practical\DeviceControl_Update"

py -m unit_test_runner map-source --workspace $fixture --dsw "$fixture\Product.dsw" --source src\device_control.c
py -m unit_test_runner analyze-function --workspace $fixture --dsw "$fixture\Product.dsw" --source src\device_control.c --function DeviceControl_Update --configuration "DeviceControl - Win32 Debug" --project DeviceControl --out $out
py -m unit_test_runner build-probe --dossier "$out\reports\function_dossier.json" --dry-run
```

## VS Code Thin Adapter

`vscode/extension` 配下のTypeScript拡張はCLIを呼び出すadapterです。C解析、レポート生成、dossier確定のロジックは持ちません。

VS Code上からの操作手順は [VS Code利用手順書](docs/vscode_usage_guide.md) にまとめています。

利用時は、Activity Bar の `Unit Test Runner` から `Workflow` パネルを開きます。パネル上部の `設定` で、プロジェクトルート、`.dsw`、出力ルート、既定構成、既定プロジェクト、必要に応じて外部CLIを設定できます。ファイル/フォルダ選択に加えて、`パスを入力` から貼り付け入力できます。設定はWorkspace設定へ保存され、User設定には書きません。

`unitTestRunner.sourceRoot` が未設定の場合は、VS Codeで開いた先頭workspace folderをプロジェクトルートとして使います。単一フォルダを開いた場合は、そのTOPフォルダが既定のプロジェクトルートです。

最初の解析は対象Cファイル上の右クリックメニュー、またはパネルの `現在関数を解析` / `選択関数を解析` から開始できます。以降はパネルが `function_dossier.md`、レビュー項目、テスト設計、build probe、テスト実行、エビデンス確認の順に現在の推奨工程を強調します。
テスト設計後は `未確定項目を入力（N件）` から専用タブを開き、入力値・事前状態・スタブ設定・期待値を入力します。値の入力と項目の `確認済み` は別操作で、`保存して反映` により変更した項目だけをcanonical `reports/test_spec.json` へ保存します。

パネルから開いたレポートは保存検知で次工程へ進みます。編集不要の場合は、パネルの `保存済みとして確定` で次のアクションへ進めます。

### テスト実行がBLOCKEDになった場合

`run-tests --run` が終了コード `35`（`blocked`）になった場合、直接の阻害項目をまとめた `reports/test_execution_blockers.md` がVS Codeで自動表示されます。Workflowには `実行ブロック項目を開く（N件）` と、安定したaction codeに基づく最初の推奨操作が残ります。

履歴の正本は `runs/<run_id>/test_execution_blockers.json` と `.md`、最新表示用は `reports/test_execution_blockers.json` と `.md` です。後続の実テスト実行が `blocked` 以外になった場合、最新表示用だけが削除され、履歴は残ります。`run-tests --plan` はブロッカー状態を生成・削除しません。通常のassertion失敗は `test_execution_report` で確認し、ブロッカーレポートには混在させません。レポート公開に失敗しても終了コード35は維持され、未検証ファイルの自動表示は行いません。

複数関数の回帰確認は `スイート` パネルで管理します。各関数workspaceを明示的に `suite_manifest.json` へ登録し、タグまたはチェック選択した関数だけをまとめて実行できます。全件確認が必要な場合は `スイート全件GREEN確認` を明示実行します。未設定時のmanifestは `unitTestRunner.outputRoot/suites/default/suite_manifest.json` です。

通常はパネルから設定します。手動でWorkspace設定を書く場合の代表例は以下です。

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

VSIXに `bin/win32-x64/unit-test-runner.exe` が同梱されている場合、`unitTestRunner.cliPath` は通常設定不要です。外部CLIを使う場合だけ、`unitTestRunner.cliPath` に絶対パスを指定します。

`unitTestRunner.workspaceRoot` と `unitTestRunner.projectName` は互換用の旧設定名です。新規設定では `unitTestRunner.sourceRoot` と `unitTestRunner.defaultProject` を使います。

サイドパネルからも呼び出す既存コマンドは以下です。

- `UnitTestRunner: Analyze Current Function`
- `UnitTestRunner: Analyze Selected Function`
- `UnitTestRunner: Reanalyze Current Function`
- `UnitTestRunner: Finalize Dossier`
- `UnitTestRunner: Open Function Dossier`
- `UnitTestRunner: Open Review Checklist`
- `UnitTestRunner: Open Next Actions`
- `UnitTestRunner: Open Change Impact Report`
- `UnitTestRunner: Open Regression Selection`
- `UnitTestRunner: Generate Test Design`
- `UnitTestRunner: 未確定テスト項目を入力`
- `UnitTestRunner: Build Probe Dry Run`
- `UnitTestRunner: Run Build Probe`
- `UnitTestRunner: Run Tests`
- `UnitTestRunner: Prepare Evidence`
- `UnitTestRunner: Register Current Function In Suite`
- `UnitTestRunner: Open Suite`
- `UnitTestRunner: Run Selected Suite Tests`
- `UnitTestRunner: Run Suite By Tag`
- `UnitTestRunner: Run All Suite Tests Require Green`
- `UnitTestRunner: Open Suite Run Report`
- `UnitTestRunner: Open Output Workspace`
- `UnitTestRunner: Copy Last CLI Command`
- `UnitTestRunner: Open Last Function Dossier`

adapterは既定でJSON出力を使い、`unitTestRunner.finalizeDossierAfterAnalyze` が `true` の場合は解析時に `--finalize-dossier` を渡します。

CLIだけでスイートを扱う場合は以下の形で実行します。

```powershell
$suite = "$env:TEMP\unitTestRunner-suite\default\suite_manifest.json"
py -m unit_test_runner --json suite-register --suite $suite --workspace $out --tags regression,selected
py -m unit_test_runner --json suite-list --suite $suite --tag selected
py -m unit_test_runner --json suite-run --suite $suite --tag selected --dry-run
py -m unit_test_runner --json suite-run --suite $suite --all --run --require-green
```

## 配布

初回配布対象はWindows向けの `unit-test-runner.exe` と VS Code拡張のVSIXです。作成手順は [配布用バイナリ作成手順書](docs/distribution_binary_build_guide.md) を参照してください。

## 対象外

v0.1では、完全なハーネス自動生成、実行カバレッジ計測、リアルタイム性検証、疑似割込、疑似時間、本番ハードウェアI/O再現は対象外です。これらはPhase 2以降の拡張候補です。

## エンコーディング方針

VC6プロジェクトファイルと対象Cソースは、レガシーWindows入力として扱います。読み取り側は `utf-8-sig`、`cp932`、`shift_jis` を受け入れます。Shift-JIS/CP932コメントは例外ではなく通常ケースです。抽出したソースとヘッダはbyte-for-byteでコピーします。

将来のmock、stub、runnerなどC系生成物は、VC6ワークフローで扱いやすいようにCP932かつCRLFで出力します。JSONとMarkdownレポートは、別要件がない限りUTF-8で扱います。

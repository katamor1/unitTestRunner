# Unit Test Runner

Visual C++ 6.0 / C90 の既存Cプロジェクトで、**関数単位の単体テスト準備**を支援する VS Code 拡張です。

普段使っている VS Code から対象関数を選び、`unit-test-runner` CLI を呼び出して、関数解析、テスト設計、レビュー用 dossier、build probe、実行エビデンスの確認へ進めます。

この拡張は **Thin Adapter** です。DSW/DSP解析、Cソース解析、テスト設計生成、build probe、エビデンス生成の本体処理は Python 製の `unit-test-runner` CLI が担当します。VS Code側は、設定、関数選択、CLI起動、結果表示、レポート閲覧、安全確認だけを行います。

現行の関数識別契約はC識別子を対象としており、C++のオーバーロード、メンバー関数、テンプレート、マングル名には対応していません。そのため、エディター上のコマンド表示対象は `.c` ファイルに限定しています。

---

## 何ができるか

- 現在開いている `.c` ファイルから関数を選び、関数単位解析を開始できます。
- VC6 `.dsw` / `.dsp` の所属情報、define、include、PCH関連情報をCLIへ渡せます。
- `function_dossier.md`、`review_checklist.md`、`unresolved_items.md`、`next_actions.md` をVS Codeからすぐ開けます。
- Quick Check で、正式レビュー前に軽量な解析・テスト設計確認を反復できます。
- Full Gate で、通常workspaceに正式なdossierとレビュー成果物を生成できます。
- build probe dry-run、build probe実行、生成テスト実行、エビデンス準備を明示操作で実行できます。
- ソース修正後の再解析、変更影響レポート、回帰テスト選定CSVを開けます。
- 複数関数の回帰確認用に、関数workspaceをスイートmanifestへ登録できます。

---

## 大事な安全方針

- **本番ソースは自動編集しません。**
- **本番 `.dsw` / `.dsp` は変更しません。**
- 生成物は `outputRoot` 配下に出します。`outputRoot` は本番ソースツリーの外側を指定してください。
- build probe実行と生成テスト実行は、既定で確認ダイアログを表示します。
- CLI、build probe、生成テストがタイムアウトした場合は、起動した子孫プロセスを含むプロセスツリー全体を終了します。
- `TBD` や `review_required` が残る期待値・スタブ動作は、拡張やCLIが自動承認しません。

---

## インストール後に最初にやること

1. VS Codeで対象Cプロジェクトのルートフォルダを開きます。
2. Activity Bar の **Unit Test Runner** を開きます。
3. **Workflow** パネル上部の **設定** で、以下を指定します。

| 項目 | 内容 |
|---|---|
| プロジェクトルート | 本番ソースを読み取るルート。未設定時は先頭workspace folderを使います。 |
| VC6 `.dsw` | 対象プロジェクトの `.dsw` ファイル。 |
| 出力ルート | dossier、生成コード、ログ、エビデンスの出力先。本番ソースツリー外を推奨します。 |
| 既定構成 | 例: `Win32 Debug`。 |
| 既定プロジェクト | 同じsourceが複数projectに属する場合だけ指定します。 |
| CLI実行ファイル | 通常は未設定で構いません。外部CLIを使う場合だけ絶対パスを指定します。 |

設定はWorkspace設定へ保存されます。User設定には書きません。

---

## 最短フロー: Quick Check

「いま触っている関数の単体テスト観点を軽く見たい」場合は Quick Check を使います。

1. 対象の `.c` ファイルを開きます。
2. 関数本文にカーソルを置くか、関数名を選択します。
3. 右クリックまたはコマンドパレットから、次のいずれかを実行します。
   - `UnitTestRunner: Quick Check Current Function`
   - `UnitTestRunner: Quick Check Selected Function`
4. 成功すると `quick_summary.md` が開きます。

Quick Check は軽量profileで `analyze-function` を呼び出します。既定の `design` profile では、解析結果とテスト設計までを生成し、正式な `function_dossier` finalization は行いません。

出力例:

```text
<outputRoot>/_quick/<source>_<function>_<hash>/
  reports/
    quick_summary.md
    function_signature.json
    global_access.json
    call_report.json
    coverage_design.json
    test_case_design.csv
```

Quick Check用の主な設定:

```json
{
  "unitTestRunner.quickProfile": "design",
  "unitTestRunner.quickOutputRoot": "",
  "unitTestRunner.quickAutoOpenSummary": true
}
```

`quickProfile` は次から選べます。

| profile | 内容 |
|---|---|
| `design` | 解析とテスト設計まで。通常はこちら。 |
| `harness` | ハーネス雛形生成まで確認。 |
| `build-dry-run` | build workspace / build probe dry-runまで。生成テスト実行はしません。 |

Quick Checkの解析結果には `reports/dependency_policy.md` / `dependency_policy.json` も含まれます。呼び出し先ごとの既定値は `real` / `stub` / `auto` です。`configured_mode` を変更した場合はQuick Checkまたは関数解析を再実行します。特定ケースだけ切り替える場合は、`test_case_design.json` の `dependency_overrides` で `inherit` / `real` / `stub` を指定してから、ハーネス生成とビルドを再実行してください。マクロ、関数ポインタ、メンバ経由呼び出し、関数アドレス利用は自動書き換えせずレビュー対象になります。

---

## 正式フロー: Full Gate / Function Dossier

レビュー用の正式成果物へ進む場合は Full Gate を使います。

1. 対象関数にカーソルを置くか、関数名を選択します。
2. `UnitTestRunner: Full Gate for Current Function` を実行します。
3. 通常workspaceに `--finalize-dossier` 付きで解析を行います。
4. `function_dossier.md`、`review_checklist.md`、`unresolved_items.md`、`next_actions.md` を確認します。

代表的な出力:

```text
<outputRoot>/<functionName>/
  input/
    request.json
  extracted/
  generated/
  logs/
  reports/
    function_dossier.json
    function_dossier.md
    review_checklist.md
    unresolved_items.md
    next_actions.md
    traceability_matrix.csv
    test_case_design.csv
```

`function_dossier.md` がレビューの入口です。詳細JSONやCSVは、必要に応じてdossierから辿ります。

---

## Workflowパネル

Activity Bar の **Unit Test Runner** から **Workflow** パネルを開けます。

Workflowパネルは `簡易` と `詳細` を切り替えられます。両表示で状態は `完了`、`次の操作`、`未実施` に統一されています。

工程番号は見出しだけに表示され、ボタンは `ビルドを実行` のような操作名を表示します。完了済みの実行操作は `Quick Checkを再実行`、`ビルドを再実行`、`テストを再実行` のように変わります。レポートやファイルを開く操作は、状態にかかわらず `〜を開く` のままです。

簡易表示では、次の4ステップを中心に表示します。

1. `Quick Check`
2. `テストソース確認`
3. `ビルド`
4. `テスト実行`

正式レビューや証跡確認で全工程を見る場合は、パネル上部の `詳細`、または簡易表示内の `詳細パネルを表示` で切り替えます。

レポートを開いて内容を確認したら、ファイルを保存すると次工程へ進みます。未完了のレビュー工程で編集不要の場合や保存検知できない場合は、`保存済みとして確定` を押します。完了済み工程では確定ボタンを表示しません。

設定欄を手動で開閉した状態は、設定項目の更新でパネルが再描画されても維持されます。複数項目を続けて変更するときに、項目ごとに設定欄を開き直す必要はありません。

---

## よく使うコマンド

| コマンド | 用途 |
|---|---|
| `UnitTestRunner: Quick Check Current Function` | カーソル位置の関数を軽量解析します。 |
| `UnitTestRunner: Quick Check Selected Function` | 選択した関数名を軽量解析します。 |
| `UnitTestRunner: Quick Summaryを開く` | 直近の `quick_summary.md` を開きます。 |
| `UnitTestRunner: Full Gate for Current Function` | 正式dossier生成へ進みます。 |
| `UnitTestRunner: 現在関数を解析` | 通常の関数解析を実行します。 |
| `UnitTestRunner: 選択関数を解析` | 選択した関数名で通常解析します。 |
| `UnitTestRunner: 現在関数を再解析` | ソース修正後、既存テスト設計の再利用可否を確認します。 |
| `UnitTestRunner: 変更影響レポートを開く` | `change_impact_report.md` を開きます。 |
| `UnitTestRunner: 回帰テスト選定を開く` | `regression_selection.csv` を開きます。 |
| `UnitTestRunner: テスト設計を生成` | `test_case_design.csv` などを生成します。 |
| `UnitTestRunner: ハーネスを生成` | スタブ・ハーネス雛形を生成します。 |
| `UnitTestRunner: ビルドプローブをdry-run` | Makefileやbuild commandを生成し、実ビルドは行いません。 |
| `UnitTestRunner: ビルドプローブを実行` | 生成workspaceでbuild probeを実行します。確認あり。 |
| `UnitTestRunner: テストを実行` | 生成テストを実行します。確認あり。 |
| `UnitTestRunner: エビデンスを準備` | 実行結果、ログ、manifestを整理します。 |
| `UnitTestRunner: 最後のCLIコマンドをコピー` | VS Codeから実行したCLIを再現用にコピーします。 |

---

## 再解析と回帰テスト選定

単体テストNG後にソースを修正した場合、既存テストケースを捨てずに再利用したいことがあります。

その場合は、対象関数を開いて次を実行します。

```text
UnitTestRunner: 現在関数を再解析
```

再解析では、現在のソースと依存関係を読み直し、前回のdossierやテスト設計と比較します。

主な出力:

```text
reports/change_impact_report.md
reports/test_case_reconciliation_report.md
reports/regression_selection.csv
```

分類例:

| 分類 | 意味 |
|---|---|
| `reusable` | 既存テストをそのまま使える可能性が高い。 |
| `reusable_with_review` | 使えそうだが確認が必要。 |
| `needs_update` | 入力値、期待値、stub設定などの更新が必要。 |
| `obsolete` | 対応する条件やcoverage itemが消えた。 |
| `new_required` | 新しい分岐や依存に対するテスト追加が必要。 |

---

## 複数関数回帰スイート

複数関数をまとめて回帰確認したい場合は、**スイート** パネルを使います。

| 操作 | コマンド |
|---|---|
| 現在関数をmanifestへ登録 | `UnitTestRunner: 現在関数をスイートに登録` |
| manifestを開く | `UnitTestRunner: スイートを開く` |
| ダッシュボードを開く | `UnitTestRunner: スイートダッシュボードを開く` |
| 選択した関数だけ実行 | `UnitTestRunner: 選択したスイートテストを実行` |
| タグで実行 | `UnitTestRunner: タグ指定でスイートテストを実行` |
| 登録済み全件をGREEN判定 | `UnitTestRunner: スイート全件GREEN確認` |
| 実行レポートを開く | `UnitTestRunner: スイート実行レポートを開く` |

スイートの正本は `suite_manifest.json` です。未設定時は次を使います。

```text
<outputRoot>/suites/default/suite_manifest.json
```

---

## 主な設定

通常は Workflow パネルから設定できます。手動で Workspace 設定を書く場合は以下の形です。

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

CLI同梱VSIXを使う場合、`unitTestRunner.cliPath` は通常設定不要です。外部CLIを使う場合だけ絶対パスを指定します。

```json
{
  "unitTestRunner.cliPath": "D:/tools/unitTestRunner/unit-test-runner.exe"
}
```

VC6 build probe を実行する場合、`nmake` / `cl` がPATHにない環境では `VCVARS32.BAT` を指定します。

```json
{
  "unitTestRunner.vcvarsPath": "C:/Program Files/Microsoft Visual Studio/VC98/Bin/VCVARS32.BAT"
}
```

build/test実行前の確認を維持する設定:

```json
{
  "unitTestRunner.runBuildProbeRequiresConfirmation": true,
  "unitTestRunner.runTestsRequiresConfirmation": true
}
```

---

## 生成物の考え方

この拡張で作る成果物は、レビューと再実行のための作業成果物です。

| 成果物 | 役割 |
|---|---|
| `function_dossier.md` | 関数単位レビューの入口。 |
| `review_checklist.md` | 人間が確認する観点。 |
| `unresolved_items.md` | 未解決事項。期待値、stub、setup、buildなど。 |
| `next_actions.md` | 次にやるべき作業。 |
| `test_case_design.csv` | テスト設計表。Excel等でレビュー可能。 |
| `build_probe_report.md` | build probeの結果と不足情報。 |
| `test_execution_report.md` | 生成テスト実行結果。 |
| `evidence_package.md` | ログ、結果、manifestをまとめた証跡入口。 |

---

## トラブルシュート

| 症状 | 確認すること | 対処 |
|---|---|---|
| `UnitTestRunner:` コマンドが出ない | VSIXが有効か | VS Codeを再起動、または `Developer: Reload Window` を実行します。 |
| Workflowパネルが表示されない | Activity Barの `Unit Test Runner` | 拡張が有効か確認し、ビューを開きます。 |
| `ビューのデータ提供者が登録されていません` と表示される | VSIX更新直後の拡張host | `Developer: Reload Window` またはVS Code再起動を行います。 |
| CLIが見つからない | 同梱exeまたは `cliPath` | CLI同梱VSIXを使うか、外部CLIの絶対パスを設定します。 |
| `sourceRoot` が空というエラー | 開いているフォルダと設定 | フォルダを開き直すか、Workflowパネルでプロジェクトルートを指定します。 |
| `.dsw` が見つからない | `unitTestRunner.dswPath` | Workflowパネルで対象 `.dsw` を選択します。 |
| 関数名が解決されない | カーソル位置または選択範囲 | 関数名を選択して `Quick Check Selected Function` または `Analyze Selected Function` を実行します。 |
| 生成物が本番ツリー内に出る | `outputRoot` / `quickOutputRoot` | `sourceRoot` の外側へ変更します。 |
| Quick Summaryが開かない | 直近Quick Check workspace | `Open Output Workspace` で `reports/quick_summary.md` を確認します。 |
| build probeが環境なしになる | VC6環境 | `vcvarsPath` に `VCVARS32.BAT` を指定します。 |
| 次工程へ進まない | レポート保存状態 | ファイルを保存するか、Workflowパネルで `保存済みとして確定` を押します。 |

---

## 現時点の範囲外

v0.1では、以下は対象外または後続フェーズです。

- 本番アプリケーション全体の実行
- 実機ハードウェアI/O再現
- 割込・疑似時間・32ms制約の本格検証
- 実測カバレッジ instrumentation
- 期待結果やスタブ動作の自動承認
- 本番リポジトリへのテストファイル自動追加

---

## 詳細ドキュメント

より詳しい手順は、リポジトリ内の次の文書を参照してください。

- `docs/vscode_usage_guide.md`
- `docs/vscode_quick_check_usage.md`
- `docs/function_level_vc6_unit_test_codex_design.md`

# unitTestRunner 基本設計書

作成日: 2026-07-05  
対象版数: v0.1  
対象リポジトリ: `unitTestRunner`

## 1. 目的

`unitTestRunner` は、Visual C++ 6.0 / C90 で開発された既存Cプロジェクトに対し、関数単位の単体テスト開始に必要な情報を収集し、レビュー可能なdossierとして出力するツールである。

初期版では、完全な実行可能ハーネスの自動生成ではなく、以下を安定して実行することを目的とする。

- `.dsw` / `.dsp` から対象ソースの所属プロジェクトとビルド文脈を特定する
- 指定関数のシグネチャ、副作用、呼び出し、分岐、境界値候補を抽出する
- テストケース設計、stub候補、build probe、レビュー項目を生成する
- 生成物を本番ソースツリーの外部ワークスペースにまとめる
- VS CodeからはCLIを呼び出す薄いadapterとして利用できるようにする

## 2. 基本方針

### 2.1 dossier-first

公開成果物の中心は `reports/function_dossier.json` とする。`analyze-function` の通常出力でも、`--finalize-dossier` または `finalize-dossier` 後でも、このファイルを後続コマンドの安定した入力にする。

`function_dossier.json` は最低限、以下の契約フィールドを維持する。

- `schema_version`
- `target`
- `project_membership`
- `build_context`
- `function`
- `test_design`
- `diagnostics`

レビュー確定後は、上記に加えて `artifact_index`、`traceability`、`review_items`、`unresolved_items`、`next_actions`、`readiness` などを追加する。

### 2.2 本番リポジトリ非侵襲

対象Cプロジェクトは読み取り専用入力として扱う。抽出ソース、生成ハーネス、build用ファイル、ログ、レポートは `--out` で指定した外部ワークスペースに出力する。

この方針により、本番リポジトリへテスト用ファイル、追加include、生成stub、作業ログを混入させない。

### 2.3 Python CLI core

中核処理はPython CLIに集約する。理由は以下である。

- Windows上のファイル解析、JSON/CSV/Markdown生成を実装しやすい
- 単体テストで段階的に検証しやすい
- VS Code、バッチ、CI、手動CLIから同じ機能を利用できる
- 将来的な単体exe化が容易である

公開CLI入口は以下である。

```powershell
py -m unit_test_runner --help
unit-test-runner --help
```

### 2.4 VS Code thin adapter

VS Code拡張は `vscode/extension` 配下のTypeScript実装とし、CLI呼び出し、設定読取、対象関数解決、レポートを開く操作に責務を限定する。

拡張内にDSW/DSP解析、C解析、dossier生成、レポート生成ロジックは持たない。

### 2.5 VC6/C90/CP932制約

対象プロジェクトはレガシーWindows資産として扱う。

- `.dsw` / `.dsp` とCソースは `utf-8-sig`、`cp932`、`shift_jis` を受け入れる
- 抽出したソースとヘッダはbyte-for-byteでコピーする
- 生成するC系成果物はC90互換を優先する
- VC6で扱いやすいように、C系生成物はCP932とCRLFを基本にする
- JSONとMarkdownレポートはUTF-8を基本にする

## 3. 全体構成

```text
User / VS Code
  -> VS Code Thin Adapter
  -> unit-test-runner CLI
       -> VC6 Project Discovery
       -> C Function Analyzer
       -> Test Design Support
       -> Harness / Build Workspace Generator
       -> Execution / Evidence
       -> Dossier Finalizer / Review Workflow
       -> Reanalysis / Regression Selection
```

## 4. 主要コンポーネント

| コンポーネント | 主な責務 | 主な成果物 |
|---|---|---|
| CLI | コマンド解析、入出力検証、JSON/通常出力、終了コード制御 | CLIResult、標準出力、ログ |
| VC6 Project Discovery | `.dsw` / `.dsp` 解析、構成、define、include、所属判定 | `project_membership.md`, `build_context.json` |
| C Function Analyzer | 関数位置、シグネチャ、グローバル、副作用、呼び出し、分岐解析 | `function_dossier.json`, analyzer reports |
| Test Design Support | 境界値、同値クラス、coverage item、テストケース設計案 | `test_case_design.csv`, `coverage_design.md` |
| Harness / Build | C90雛形、stub候補、Makefile、build probe | `generated/`, `build_probe.log` |
| Execution / Evidence | 明示実行、dry-run、結果解析、エビデンスmanifest | `test_execution_report`, `evidence_manifest.json` |
| Dossier Review | artifact index、traceability、review checklist、next actions | `review_checklist.md`, `traceability_matrix.csv` |
| Reanalysis | 前回dossierとの差分、テストケース再利用、回帰選定 | change impact / regression reports |
| VS Code Adapter | CLI起動、対象関数解決、成果物を開く、確認ダイアログ | VS Code command / setting |

## 5. CLIコマンド

現行の公開コマンドは以下である。

```text
doctor
discover-projects
map-source
list-functions
analyze-function
reanalyze-function
generate-harness-skeleton
build-probe
analyze-build-errors
complete-build
run-tests
prepare-evidence
finalize-dossier
prepare-review
generate-test-design
reconcile-test-cases
select-regression-tests
```

`analyze-function` は指定関数のdossierを生成する中心コマンドである。レビュー用成果物まで同時に生成する場合は `--finalize-dossier` を付ける。テスト実行を伴う操作は、`run-tests` または明示的な `--phase execution --run-tests` に限定する。

## 6. 外部ワークスペース構成

代表的な出力構成は以下である。

```text
<out>/
  input/
    request.json
  extracted/
    src/
    include/
  generated/
    build/
    harness/
    stubs/
    tests/
  logs/
  reports/
    function_dossier.json
    function_dossier.md
    test_case_design.csv
    dossier_manifest.json
    traceability_matrix.csv
    review_checklist.md
    unresolved_items.md
    next_actions.md
```

## 7. Phase 1対象外

v0.1では以下を対象外とする。

- 完全な実行可能ハーネスの自動完成
- 実行カバレッジ計測
- リアルタイム性検証
- 32ms制約検証
- 疑似時間、疑似割込
- 実機ハードウェアI/O再現
- 本番リポジトリへのテストファイル追加
- GUI単体アプリの提供

## 8. 受け入れ基準

- `py -m unit_test_runner --help` で全公開CLIコマンドを確認できる
- `analyze-function` が `reports/function_dossier.json` を生成する
- `--finalize-dossier` 後も `function_dossier.json` を後続コマンドに渡せる
- `build-probe --dossier ... --dry-run` が生成workspaceに対して実行計画を出せる
- `generate-test-design --dossier ...` がdossierからテスト設計を生成できる
- VS Code adapterはCLI呼び出しに限定され、parserやreport generatorを持たない


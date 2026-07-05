# unitTestRunner 詳細設計書

作成日: 2026-07-05  
対象版数: v0.1

## 1. 概要

本書は、現行コードベースと `docs/implementation` 配下のStep計画を基に、`unitTestRunner` の主要サブシステムの責務、入力、出力、処理概要を整理する。

実装コードの公開API、CLI引数、JSON schema、VS Code設定名は本書では変更しない。

## 2. CLI層

### 2.1 責務

CLI層は `src/unit_test_runner/cli` に配置する。

- グローバルオプションとサブコマンドの定義
- 入力パスの存在確認
- `CLIResult` への正規化
- `--json` 指定時の機械可読出力
- 入力エラー、実行エラー、予期しない例外の終了コード制御

### 2.2 主要入力

- `--workspace`: 対象VC6ソースツリーまたは生成済み外部ワークスペース
- `--dsw`: VC6 workspaceファイル
- `--source`: 対象Cソース
- `--function`: 対象関数名
- `--configuration`: VC6構成名
- `--project`: 対象プロジェクト名
- `--out`: 生成先外部ワークスペース
- `--dossier`: `reports/function_dossier.json`

### 2.3 出力

通常モードでは人間向けメッセージ、JSONモードではCLI payloadを標準出力へ出す。ファイル成果物は各コマンドの責務に応じて外部ワークスペースへ出力する。

## 3. VC6 Project Discovery

### 3.1 DSW解析

`.dsw` からプロジェクト一覧、`.dsp` パス、依存関係を抽出する。VC6固有の `Project:` 行、`Package=<...>`、dependency block を許容する。

主な成果物:

- discovered project一覧
- project dependency
- warning / diagnostic

### 3.2 DSP解析

`.dsp` から構成、source membership、define、include directory、compiler option、PCH関連指定を抽出する。

主な成果物:

- source file set
- build context
- configuration candidates
- include / define / compiler option

### 3.3 source-to-project mapper

対象 `--source` がどの `.dsp` に含まれるかを判定する。複数候補がある場合は、候補を保持し、`--project` と `--configuration` で明示選択できるようにする。

## 4. C Function Analyzer

### 4.1 Source Reader / Masker

Cソースを読み込み、コメント、文字列、プリプロセッサ行を解析しやすい形に正規化する。完全なCコンパイラではなく、関数単位dossier生成に必要な軽量解析を目的とする。

### 4.2 Function Locator

対象関数名から定義位置、本文範囲、行番号、関数外形を特定する。誤判定しやすいmacroやコメント内文字列はmaskerの結果を使って避ける。

### 4.3 Signature Extractor

戻り値、関数名、引数、ポインタ、配列、calling convention候補を抽出する。C90/VC6向けの宣言形を優先し、判断困難な要素はwarningまたはconfidenceとして残す。

### 4.4 Global Access Analyzer

対象関数本文から、参照・更新するグローバル変数、file-scope static、extern候補、引数経由の副作用候補を抽出する。

### 4.5 Call Analyzer

対象関数が呼び出す外部関数、static関数、callback、function-like macro候補、戻り値利用、引数を抽出する。stub候補の入力にもなる。

### 4.6 Branch / Condition Analyzer

`if`、`else`、`switch`、`case`、loop、return経路などからcoverage itemを作る。期待値は断定せず、レビュー対象として保持する。

## 5. Test Design Support

### 5.1 Boundary / Equivalence Candidate

条件式、比較演算、NULL判定、配列添字、enum風定数、macro定数などから境界値候補と同値クラス候補を生成する。

### 5.2 Test Case Design

関数シグネチャ、グローバルアクセス、呼び出し、分岐、境界値候補を統合し、レビュー可能なテストケース設計を生成する。

主な出力:

- `reports/test_case_design.csv`
- test case design JSON
- coverageとの対応情報
- `review_required` / `TBD` / confidence / warning

## 6. Harness / Build Workspace

### 6.1 Harness Skeleton

関数シグネチャ、グローバル、副作用、stub候補、テスト設計から、C90/VC6向けのharness skeletonを生成する。完全なテスト期待値を自動確定せず、人間レビュー前提の雛形に留める。

### 6.2 Build Workspace

抽出ソース、生成ファイル、include、Makefile、build scriptを外部ワークスペースに配置する。

主な出力:

- `generated/build/Makefile`
- `generated/harness/`
- `generated/stubs/`
- `reports/build_workspace_report.json`

### 6.3 Build Probe

`build-probe` はVC6/nmake/cl.exeでのビルド試行またはdry-runを行う。`--dry-run` では実行せず、コマンド計画、入力、ログ出力先を確認できるようにする。

## 7. Build Completion

`analyze-build-errors` と `complete-build` は、build logからinclude不足、未解決symbol、PCH問題、stub不足などを分類し、安全に補完可能な範囲だけを生成workspace内へ適用する。

本番ソースツリーには補完を適用しない。

## 8. Execution / Evidence

### 8.1 Test Execution

`run-tests` は生成済みworkspaceの実行対象を解決し、明示指示がある場合のみテストバイナリを起動する。`--dry-run` では実行計画とエビデンス雛形を作る。

### 8.2 Evidence Preparation

`prepare-evidence` は生成済みworkspaceからログ、レポート、manifest、hash情報を再収集し、レビュー可能なエビデンスを作る。

代表成果物:

- `test_execution_report.json`
- `test_execution_report.md`
- `test_result.csv`
- `evidence_manifest.json`
- `evidence_package.md`

## 9. Dossier Finalization / Review Workflow

### 9.1 Finalize

`finalize-dossier` は生成workspaceの成果物を収集し、`reports/function_dossier.json` をレビュー用に確定する。

追加される代表情報:

- artifact index
- traceability
- unresolved items
- next actions
- readiness
- review checklist

### 9.2 Prepare Review

`prepare-review` は確定済みdossierからレビュー関連成果物を再生成する。VS Code adapterや手動レビューから繰り返し利用できる。

## 10. Reanalysis / Regression Selection

`reanalyze-function` は前回dossierや前回テストケース設計と現行解析結果を比較し、差分と再利用可能なテストケースを整理する。

関連コマンド:

- `reanalyze-function`
- `reconcile-test-cases`
- `select-regression-tests`

主な成果物:

- change impact report
- test case reconciliation report
- regression selection

## 11. VS Code Adapter

### 11.1 責務

VS Code adapterは以下に限定する。

- workspace設定の読み取り
- 現在関数または選択関数の推定
- CLIコマンドラインの構築
- CLI実行とタイムアウト制御
- JSON出力からレポートパスを解決
- 生成レポートをエディタで開く
- build/test実行系の確認ダイアログ

### 11.2 代表設定

```json
{
  "unitTestRunner.cliPath": "unit-test-runner",
  "unitTestRunner.sourceRoot": "D:/work/product",
  "unitTestRunner.dswPath": "D:/work/product/Product.dsw",
  "unitTestRunner.outputRoot": "D:/work/unit_test_workspace",
  "unitTestRunner.defaultConfiguration": "Win32 Debug",
  "unitTestRunner.defaultProject": "Control",
  "unitTestRunner.finalizeDossierAfterAnalyze": true,
  "unitTestRunner.useJsonOutput": true
}
```

`unitTestRunner.workspaceRoot` と `unitTestRunner.projectName` は互換用の旧名である。

## 12. エラー処理と安全性

- 入力不足や不正パスはCLI入力エラーとして扱う
- 解析不能なC構文は例外で止めず、warningやlow confidenceとしてdossierに残す
- build/testの実行系は明示オプションまたはVS Code確認を必要とする
- 生成物は外部workspaceに限定する
- stale artifactや読み取り不能JSONは、payload解析と独立して診断する

## 13. 継続更新方針

機能追加時は、以下を同時に確認する。

- CLI helpとREADMEのコマンド一覧
- `docs/basic_design.md` と `docs/detailed_design.md`
- `docs/test_specification.md`
- VS Code `package.json` の設定・コマンド
- fixture smoke手順


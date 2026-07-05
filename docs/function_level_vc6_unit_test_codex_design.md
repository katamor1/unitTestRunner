# 関数単位 VC6/C90 単体テスト支援ツール 企画・設計書

作成日: 2026-07-04  
対象リポジトリ: `katamor1/unitTestRunner`  
製造担当想定: CODEX  
版数: v0.1

---

## 1. 目的

本設計書は、C90 / Visual C++ 6.0 で開発されている既存アプリケーションに対して、まずは **関数単位** の単体テスト支援を開始するための企画・設計を定義する。

前提として、初期フェーズではリアルタイム性、ハードウェア割込制御、32ms 時間遵守制約には関与しない。
本番実行環境のリアルタイム挙動を再現するのではなく、ユーザーが指定した `.c` ファイル内の特定関数について、単体テストを開始するために必要な情報収集、ビルド構成抽出、テスト設計支援を行う。

初期ゴールは、以下である。

- ユーザーが `.c` ファイル内の関数を指定できる
- その `.c` ファイルが、どの VC6 プロジェクト `.dsw` / `.dsp` に所属するかを明らかにできる
- 対象プロジェクトの define、include ディレクトリ、構成情報を収集できる
- 関数単位テストに必要なファイル構成を選定できる
- 指定関数の引数、戻り値、参照・更新するグローバル変数、外部呼び出し、分岐条件を収集できる
- 分岐・条件網羅、境界値、同値クラスのテスト設計に使える情報を出力できる
- 上記成果を確認した後に、モジュール単位への拡張計画を判断できる

---

## 2. 方針変更点

前回計画からの明確な変更点は以下とする。

| 項目 | 前回寄りの考え方 | 本設計での考え方 |
|---|---|---|
| 初期対象 | モジュール単位 | 関数単位 |
| リアルタイム性 | 32ms 制約の分離も初期検討対象 | 初期フェーズでは扱わない |
| ハードウェア割込 | 疑似割込・疑似時間の検討あり | 初期フェーズでは扱わない |
| テスト環境 | 外部ワークスペースでモジュールテスト生成 | 外部ワークスペースで関数単位テストの情報収集と最小駆動 |
| 入口 | manifest 指定中心 | VS Code 上の関数選択、または CLI 指定 |
| 主成果 | テストハーネス生成 | 関数単位テスト開始に必要な dossier 生成 |
| 拡張判断 | モジュールテスト前提 | 関数単位の成果確認後にモジュール拡張判断 |

---

## 3. スコープ

### 3.1 Phase 1 の対象範囲

Phase 1 では、以下を対象にする。

1. VC6 プロジェクト情報の解析
   - `.dsw` から `.dsp` の一覧と依存関係を取得する
   - `.dsp` から構成、ソースファイル一覧、define、include ディレクトリ、コンパイルオプションを取得する
   - 対象 `.c` ファイルが所属するプロジェクトと構成候補を明らかにする

2. 関数指定
   - VS Code 上でユーザーが関数を選択する
   - または CLI で `.c` ファイルと関数名を指定する
   - 変更・追加された関数を候補として提示する

3. ビルド構成選定
   - 対象 `.c` のコンパイルに必要な include / define を収集する
   - 対象 `.c` と関連ヘッダを外部ワークスペースへ抽出する
   - 関数単位テストに必要な最小ファイル構成候補を生成する
   - VC6 / nmake / cl.exe でのビルド試行に必要な情報を出力する

4. 関数情報収集
   - 関数シグネチャ
   - 引数
   - 戻り値
   - ローカル変数概要
   - 参照するグローバル変数
   - 更新するグローバル変数
   - 呼び出す外部関数
   - static 関数呼び出し
   - マクロ参照
   - 分岐条件
   - switch / case
   - ループ条件
   - return 経路

5. テスト設計支援情報の生成
   - 分岐網羅候補
   - 条件網羅候補
   - 境界値候補
   - 同値クラス候補
   - 入力制約候補
   - グローバル変数初期値候補
   - スタブ化候補
   - テストケース設計案

### 3.2 Phase 1 では対象外とする範囲

Phase 1 では、以下を対象外とする。

- リアルタイム性の検証
- 32ms 時間遵守制約への対策
- 疑似時間の実装
- 疑似割込の実装
- 本番機ハードウェア I/O の再現
- モジュール全体の統合テスト
- 実機接続テスト
- カバレッジ計測ツールとの完全統合
- 本番リポジトリへのテストファイル追加

ただし、将来の Phase で扱えるように、設計上の拡張余地は残す。

---

## 4. ユーザー体験

### 4.1 理想 UX

ユーザーは普段利用している VS Code 上で、以下の流れで単体テスト支援を開始できる。

1. VS Code で対象 `.c` ファイルを開く
2. 変更または追加した関数を選択する
3. コマンドパレットまたは右クリックから `UnitTestRunner: Start Function Unit Test` を実行する
4. ツールが `.dsw` / `.dsp` を解析する
5. 対象関数が所属する VC6 プロジェクトと構成候補が表示される
6. ユーザーが構成を選択する
7. 外部ワークスペースに解析結果とテスト準備ファイルが生成される
8. Markdown レポートと JSON dossier が開かれる
9. 必要に応じてテストケース設計案を編集する
10. 最小テストハーネス生成とビルド試行へ進む

### 4.2 MVP UX

VS Code 拡張機能を最初から作り込むと開発範囲が大きくなるため、MVP は **CLI コア + VS Code タスク/薄い拡張** とする。

MVP の入口:

```bat
unit-test-runner.exe analyze-function ^
  --workspace D:\work\product ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Win32 Debug" ^
  --out D:\work\unit_test_workspace
```

VS Code からは、以下のいずれかで起動する。

- `tasks.json` 経由
- 右クリック拡張から CLI を呼び出す薄い VS Code extension
- コマンドパレットから CLI を呼び出す薄い VS Code extension

### 4.3 スタンドアロンアプリの位置づけ

VS Code 拡張が難しい場合、スタンドアロンアプリを用意する。
ただし、初期設計では CLI コアを必ず中心に置く。

理由:

- CODEX が製造しやすい
- テストしやすい
- VS Code / GUI / CI / バッチ実行のどれからでも利用できる
- 将来の拡張が容易

---

## 5. 全体アーキテクチャ

```text
[User / VS Code]
      |
      | function selection
      v
[VS Code Thin Adapter]
      |
      | CLI invocation
      v
[unit-test-runner CLI]
      |
      +-- Project Discovery
      |     +-- DSW parser
      |     +-- DSP parser
      |     +-- source-to-project mapper
      |
      +-- Build Context Collector
      |     +-- configuration selector
      |     +-- defines collector
      |     +-- include dirs collector
      |     +-- compiler option collector
      |     +-- source file set selector
      |
      +-- C Function Analyzer
      |     +-- lexical scanner
      |     +-- function locator
      |     +-- signature extractor
      |     +-- global access analyzer
      |     +-- call analyzer
      |     +-- branch/condition analyzer
      |
      +-- Test Design Support
      |     +-- coverage item generator
      |     +-- boundary/equivalence candidate generator
      |     +-- stub candidate generator
      |     +-- AI prompt pack generator
      |
      +-- Workspace Generator
      |     +-- extracted files
      |     +-- generated reports
      |     +-- build scripts
      |     +-- optional harness skeleton
      |
      +-- Evidence / Reports
            +-- function_dossier.json
            +-- function_dossier.md
            +-- project_membership.md
            +-- build_context.json
            +-- coverage_design.md
            +-- test_case_design.csv
```

---

## 6. 成果物

### 6.1 主要成果物

Phase 1 の主成果物は `function_dossier` とする。
これは、指定関数の単体テストを設計・生成・レビューするための情報パッケージである。

出力例:

```text
workspace/
  Control_Update/
    input/
      request.json
    extracted/
      src/
      include/
    generated/
      build/
      harness_skeleton/
    reports/
      function_dossier.json
      function_dossier.md
      project_membership.md
      build_context.json
      source_file_set.md
      global_access_report.md
      call_report.md
      branch_condition_report.md
      coverage_design.md
      boundary_equivalence_candidates.md
      stub_candidates.md
      test_case_design.csv
      build_probe.log
```

### 6.2 function_dossier.json

`function_dossier.json` は機械処理向けの中核ファイルである。

```json
{
  "schema_version": "0.1",
  "target": {
    "source": "src/control.c",
    "function": "Control_Update",
    "configuration": "Win32 Debug"
  },
  "project_membership": [
    {
      "dsw": "Product.dsw",
      "dsp": "Control.dsp",
      "project_name": "Control",
      "configurations": ["Win32 Debug", "Win32 Release"]
    }
  ],
  "build_context": {
    "defines": ["WIN32", "_DEBUG"],
    "include_dirs": ["include", "src", "platform/include"],
    "compiler_options": ["/nologo", "/W3", "/GX"],
    "precompiled_header": {
      "enabled": false,
      "header": null
    }
  },
  "function": {
    "name": "Control_Update",
    "return_type": "int",
    "parameters": [
      {
        "name": "mode",
        "type": "int"
      },
      {
        "name": "sensor_value",
        "type": "int"
      }
    ],
    "globals_read": ["g_control_state"],
    "globals_written": ["g_error_code"],
    "external_calls": ["ReadSensor", "WriteOutput"],
    "branches": [],
    "returns": []
  },
  "test_design": {
    "branch_coverage_items": [],
    "condition_coverage_items": [],
    "boundary_value_candidates": [],
    "equivalence_class_candidates": [],
    "stub_candidates": []
  }
}
```

### 6.3 Markdown レポート

ユーザーがレビューする主要レポートは `function_dossier.md` とする。

内容:

- 対象関数
- 所属 VC6 プロジェクト
- 使用構成
- define 一覧
- include ディレクトリ一覧
- 抽出ファイル一覧
- 関数シグネチャ
- 入力
- 出力
- 参照グローバル
- 更新グローバル
- 外部呼び出し
- 分岐条件
- 境界値候補
- 同値クラス候補
- スタブ候補
- テストケース設計案
- 未解決事項

---

## 7. VC6 プロジェクト解析設計

### 7.1 DSW 解析

`.dsw` から以下を取得する。

- workspace 名
- 含まれる `.dsp` ファイル
- プロジェクト名
- プロジェクト間依存関係
- 相対パス解決に必要な基準ディレクトリ

DSW 解析の目的は、対象 `.c` がどのプロジェクト候補に属するかを調べるためである。

### 7.2 DSP 解析

`.dsp` から以下を取得する。

- プロジェクト名
- 構成名
- ソースファイル一覧
- ヘッダファイル一覧
- `# ADD CPP` 行
- `# ADD BASE CPP` 行
- `/D` define
- `/I` include ディレクトリ
- `/FI` forced include
- `/Yu` precompiled header 使用
- `/Yc` precompiled header 作成
- `/Fo` object 出力
- `/Fd` program database 出力
- `/ML` `/MT` `/MD` などのランタイム指定
- custom build step の有無

Phase 1 では、完全な VC6 再現ではなく、対象 `.c` のコンパイルに効く情報の収集を優先する。

### 7.3 対象 .c の所属判定

同じ `.c` ファイルが複数 `.dsp` に含まれる可能性があるため、所属は単数前提にしない。

判定結果例:

```text
src/control.c
  - Product.dsw / Control.dsp / Win32 Debug
  - Product.dsw / Control.dsp / Win32 Release
  - Product.dsw / FactoryTest.dsp / Win32 Debug
```

複数候補がある場合、ユーザーに選択させる。
CLI では `--configuration` と `--project` を指定できるようにする。

### 7.4 include / define 収集

収集した include / define は、以下の用途に使う。

- 解析時の条件コンパイル解釈
- ビルド試行
- ユーザーレビュー
- テストハーネス生成
- CODEX への製造・修正コンテキスト

注意点:

- `.dsp` 内の相対パスは `.dsp` 所在ディレクトリ基準で解決する
- `$(VAR)` 形式のマクロは Phase 1 では既知変数だけ展開し、不明変数は unresolved として残す
- include ディレクトリが存在しない場合も即エラーにせず、警告として記録する
- 構成ごとの差分を保持する

---

## 8. ビルドが通るファイル構成の選定

### 8.1 基本方針

関数単位テストでは、対象関数だけを抜き出すのではなく、まず対象関数を含む `.c` ファイルを中心に構成する。

理由:

- static 関数、file scope 変数、マクロ依存を壊しにくい
- VC6 / C90 の古い書き方に対して安全
- 本番コードへの変更が不要
- 解析とビルド失敗から不足を反復的に補える

### 8.2 ファイル構成選定の段階

段階 1: 対象 `.c` + include されるヘッダ

- 対象 `.c`
- 直接 include ヘッダ
- include ヘッダからさらに参照されるヘッダ
- forced include
- precompiled header が必要な場合のヘッダ

段階 2: コンパイル成功に必要な補助ファイル

- 型定義ヘッダ
- マクロ定義ヘッダ
- extern 宣言ヘッダ
- 構成依存ヘッダ

段階 3: リンク成功に必要な実体またはスタブ

- 対象関数が呼び出す外部関数
- 対象 `.c` 内で必要な外部変数
- ライブラリ関数以外の未解決シンボル
- 自動生成スタブ候補

Phase 1 では、段階 1 と段階 2 を優先する。
段階 3 は、未解決シンボル一覧とスタブ候補の生成までを必須とし、スタブの完全自動生成は Phase 2 以降で強化する。

### 8.3 ビルドプローブ

`build_probe` は、実際のテスト実行ではなく、対象関数を駆動するための準備状況を確認するためのビルド試行である。

出力:

- `build_probe.log`
- include 不足一覧
- define 不足候補
- 未解決外部参照一覧
- PCH 関連エラー
- VC6 非互換な生成コード検出

---

## 9. C 関数解析設計

### 9.1 解析方針

Phase 1 では、完全な C コンパイラフロントエンドを作らない。
VC6 時代のソースコードに対して壊れにくい、実用的な軽量解析を行う。

解析の基本方針:

- コメントと文字列リテラルを除去またはマスクする
- プリプロセッサ行を保持する
- 波括弧の対応で関数範囲を特定する
- 関数候補の直前トークンから戻り値と引数を抽出する
- ローカル宣言とグローバル宣言を粗く区別する
- 呼び出し式を候補抽出する
- 代入式から書き込み候補を抽出する
- 条件式から分岐・境界候補を抽出する

### 9.2 関数ロケータ

入力:

- `.c` ファイルパス
- 関数名
- include / define 情報

出力:

- 関数開始行
- 関数終了行
- 関数本文
- シグネチャ
- static / extern の有無
- 条件コンパイル内にあるかどうか

エラー例:

- 関数が見つからない
- 同名関数候補が複数ある
- マクロで関数定義されており解析不能
- 波括弧対応が崩れている

### 9.3 引数・戻り値解析

収集する情報:

- 戻り値型
- 引数名
- 引数型
- ポインタかどうか
- 配列風引数かどうか
- const の有無
- 構造体型かどうか
- 関数ポインタらしき引数かどうか

テスト設計への利用:

- 入力値候補の生成
- 境界値候補の生成
- NULL 候補の生成
- 出力引数候補の識別
- 事前条件の抽出

### 9.4 グローバル変数アクセス解析

収集する情報:

- 参照グローバル変数
- 更新グローバル変数
- file scope static 変数
- extern 変数
- 配列アクセス
- 構造体メンバアクセス
- ポインタ経由アクセス候補

判定方針:

- 関数内ローカル宣言にない識別子をグローバル候補にする
- `.c` ファイル上部の file scope 宣言を候補にする
- ヘッダ内 extern 宣言を候補にする
- 代入左辺に出たものを write 候補にする
- 代入右辺、条件式、引数に出たものを read 候補にする
- ポインタ経由の副作用は conservative に `unknown side effect` として扱う

### 9.5 外部呼び出し解析

収集する情報:

- 呼び出し関数名
- 呼び出し行
- 引数式
- 戻り値利用の有無
- 対象 `.c` 内に定義があるか
- static 関数か
- 外部関数か
- 標準ライブラリ関数らしいか
- スタブ候補か

テスト設計への利用:

- スタブ候補
- 呼び出し回数期待値
- 異常戻り値パターン
- 副作用確認

### 9.6 分岐・条件解析

収集対象:

- `if`
- `else if`
- `switch`
- `case`
- `default`
- `for`
- `while`
- `do while`
- 三項演算子
- `&&`
- `||`
- 比較演算子
- 範囲チェックらしき条件
- NULL チェックらしき条件
- enum / macro 値比較

出力するカバレッジ設計情報:

- 分岐網羅項目
- 条件網羅項目
- 複合条件の真偽候補
- 到達すべき return 経路
- switch case 網羅項目
- ループ 0 回 / 1 回 / 複数回候補

Phase 1 のカバレッジは、実測カバレッジではなく **設計カバレッジ** とする。
実行時のカバレッジ計測は Phase 2 以降の検討事項とする。

---

## 10. 境界値・同値クラス候補生成

### 10.1 境界値候補

境界値候補は以下から生成する。

- 引数型
- 比較条件
- `switch case` 値
- 配列添字
- 定数マクロ
- return 値判定
- NULL チェック
- 上限・下限を示す名前の識別子

例:

```c
if (sensor_value >= SENSOR_MIN && sensor_value <= SENSOR_MAX)
```

この場合の候補:

- `SENSOR_MIN - 1`
- `SENSOR_MIN`
- `SENSOR_MIN + 1`
- `SENSOR_MAX - 1`
- `SENSOR_MAX`
- `SENSOR_MAX + 1`

### 10.2 同値クラス候補

同値クラス候補は以下の分類で生成する。

- 正常範囲
- 下限未満
- 上限超過
- 0
- 正数
- 負数
- NULL
- 非 NULL
- 有効 enum 値
- 無効 enum 値
- 空配列相当
- 最大件数
- 最大件数超過

### 10.3 ユーザー確認前提

自動生成した境界値・同値クラスは、仕様そのものではない。
必ずユーザー確認前提の候補として扱う。

レポートでは、候補に以下の分類を付ける。

- confidence: high / medium / low
- source: parameter_type / comparison / macro / switch / array_index / naming_hint
- review_required: true / false

---

## 11. テストケース設計生成

### 11.1 生成方針

テストケースは、最初から完全な自動生成を狙わない。
Phase 1 では、ユーザーが編集できる設計案を作る。

出力形式:

- Markdown
- CSV
- JSON

### 11.2 テストケース項目

```text
TC ID
対象関数
観点
前提条件
引数入力
グローバル初期値
スタブ設定
実行手順
期待戻り値
期待グローバル値
期待外部呼び出し
カバレッジ項目
判定方法
レビュー状態
```

### 11.3 生成例

```csv
id,function,purpose,input,expected,coverage,review
TC_Control_Update_001,Control_Update,正常範囲の入力で成功する,mode=MODE_AUTO; sensor=SENSOR_MIN,return=OK,BR-001,required
TC_Control_Update_002,Control_Update,下限未満の入力でエラーになる,mode=MODE_AUTO; sensor=SENSOR_MIN-1,return=ERROR,BR-002,required
```

---

## 12. AI / CODEX 活用設計

### 12.1 CODEX の役割

CODEX は、本リポジトリ `unitTestRunner` の製造担当として扱う。
CODEX には、実装タスクを小さく分割して渡す。

CODEX に期待する作業:

- CLI コマンド実装
- DSW / DSP パーサ実装
- 関数ロケータ実装
- レポート生成実装
- JSON Schema 実装
- テンプレート生成実装
- 単体テスト実装
- サンプル VC6 プロジェクトの追加
- VS Code 薄いアダプタ実装

CODEX に任せない判断:

- 本番ソースの仕様判断
- 期待値の最終決定
- 安全性・リアルタイム性の妥当性判断
- 実機動作保証

### 12.2 AI への入力制限

AI へ渡す情報は、原則として `function_dossier.json` の範囲に制限する。

初期段階では、以下を優先する。

- 関数名
- シグネチャ
- 引数情報
- 戻り値型
- 分岐条件の要約
- グローバル変数名
- 外部呼び出し名
- define / include の要約
- ビルドエラー要約

本番ソース全文の送信は前提にしない。

### 12.3 AI 出力

AI に生成させるもの:

- テスト観点候補
- 境界値候補の説明
- 同値クラス候補の説明
- スタブ方針案
- テストケース設計案
- レビュー観点

AI 出力は、以下のゲートを通す。

- JSON Schema 検証
- ユーザーレビュー
- ビルド確認
- テスト実行確認

---

## 13. CLI 設計

### 13.1 コマンド一覧

```bat
unit-test-runner.exe discover-projects --workspace D:\work\product --out reports\projects.json

unit-test-runner.exe map-source ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c

unit-test-runner.exe analyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Win32 Debug" ^
  --out D:\work\unit_test_workspace\Control_Update

unit-test-runner.exe build-probe ^
  --dossier D:\work\unit_test_workspace\Control_Update\reports\function_dossier.json

unit-test-runner.exe generate-test-design ^
  --dossier D:\work\unit_test_workspace\Control_Update\reports\function_dossier.json
```

### 13.2 analyze-function の処理

1. 入力チェック
2. `.dsw` 読み込み
3. `.dsp` 一覧取得
4. 各 `.dsp` を解析
5. 対象 `.c` の所属候補を抽出
6. 構成を確定
7. define / include / compiler option を収集
8. 対象 `.c` とヘッダを抽出
9. 関数範囲を特定
10. シグネチャを抽出
11. グローバルアクセス候補を抽出
12. 外部呼び出し候補を抽出
13. 分岐・条件を抽出
14. 境界値・同値クラス候補を生成
15. スタブ候補を生成
16. `function_dossier.json` を出力
17. Markdown / CSV レポートを出力

### 13.3 終了コード

| 終了コード | 意味 |
|---:|---|
| 0 | 成功 |
| 1 | 入力不正 |
| 2 | `.dsw` / `.dsp` 解析失敗 |
| 3 | 対象 `.c` の所属不明 |
| 4 | 構成未確定 |
| 5 | 関数が見つからない |
| 6 | 関数解析に警告あり |
| 7 | ビルドプローブ失敗 |
| 10 | 内部エラー |

---

## 14. VS Code 連携設計

### 14.1 基本方針

VS Code 連携は、CLI を呼び出す薄い層とする。
解析ロジックや生成ロジックは CLI 側に集約する。

### 14.2 機能候補

- コマンドパレット
  - `UnitTestRunner: Analyze Current Function`
  - `UnitTestRunner: Analyze Selected Function`
  - `UnitTestRunner: Open Last Function Dossier`

- エディタ右クリック
  - 選択中の関数を解析

- CodeLens
  - 関数定義上に `Analyze Unit Test` を表示

- 変更関数検出
  - Git diff から変更行を取得
  - 変更行を含む関数を候補表示

- 設定
  - `unitTestRunner.dswPath`
  - `unitTestRunner.workspaceRoot`
  - `unitTestRunner.outputRoot`
  - `unitTestRunner.defaultConfiguration`
  - `unitTestRunner.cliPath`

### 14.3 VS Code 連携の MVP

MVP では、以下だけでもよい。

- 現在開いているファイルパスを CLI に渡す
- カーソル位置または選択文字列から関数名を推定する
- `.dsw` パスと出力先は settings.json から取得する
- CLI 実行結果の Markdown レポートを開く

---

## 15. スタンドアロンアプリ設計

VS Code 連携が運用上難しい場合に備え、スタンドアロンアプリも選択肢とする。

ただし、スタンドアロンアプリも CLI コアを内部で呼び出す。

画面候補:

- ワークスペース選択
- `.dsw` 選択
- `.c` ファイル選択
- 関数一覧表示
- 構成選択
- 解析実行
- レポート表示
- テストケース設計案表示

優先度は VS Code 連携より低い。

---

## 16. 実装技術方針

### 16.1 推奨構成

初期実装は、以下の構成を推奨する。

```text
unitTestRunner/
  docs/
  src/
    unit_test_runner/
      cli/
      vc6/
      c_analyzer/
      dossier/
      reports/
      workspace/
      utils/
  tests/
    fixtures/
      vc6_projects/
      c_sources/
    unit/
  vscode/
    extension/
  schemas/
  templates/
```

### 16.2 実装言語

CLI コアの実装言語は、現時点では Python を第一候補とする。

理由:

- テキスト解析とレポート生成が容易
- CODEX が実装しやすい
- 単体テストを整備しやすい
- Windows 上で導入しやすい
- 将来的に exe 化しやすい

ただし、運用上 Python 導入が難しい場合は、C# または単体 exe 化を検討する。

### 16.3 VC6 生成物の制約

ツール本体は Python でもよいが、生成する C テストコードは VC6 / C90 互換とする。

生成 C コードで避けるもの:

- C99 以降の構文
- 変数宣言の途中配置
- `stdint.h`
- `stdbool.h`
- `inline`
- 可変長配列
- C++ コメント前提の出力
- `snprintf` 前提

---

## 17. CODEX 向け製造タスク分解

### Task 1: プロジェクト骨格作成

成果物:

- Python パッケージ構成
- CLI エントリポイント
- ログ出力
- 設定ファイル読み込み
- 基本 README
- 単体テスト実行手順

完了条件:

- `unit-test-runner --help` が動作する
- テストが 1 件以上通る

### Task 2: DSW パーサ

成果物:

- `.dsw` から `.dsp` 参照を抽出する処理
- プロジェクト名抽出
- プロジェクト依存関係抽出
- fixture と単体テスト

完了条件:

- サンプル `.dsw` から project list を JSON 出力できる

### Task 3: DSP パーサ

成果物:

- 構成一覧抽出
- source file list 抽出
- `# ADD CPP` 抽出
- `/D` `/I` `/FI` `/Yu` `/Yc` 抽出
- fixture と単体テスト

完了条件:

- サンプル `.dsp` から build context を JSON 出力できる

### Task 4: source-to-project mapper

成果物:

- 対象 `.c` が所属する `.dsp` 候補抽出
- 複数候補時のレポート
- CLI `map-source`

完了条件:

- 指定 `.c` について所属候補を表示できる

### Task 5: 関数ロケータ

成果物:

- コメント / 文字列マスク
- 関数定義候補抽出
- 波括弧対応による関数範囲抽出
- CLI から関数一覧表示

完了条件:

- サンプル C ファイルから関数一覧と行範囲を抽出できる

### Task 6: 関数シグネチャ解析

成果物:

- 戻り値型抽出
- 引数名 / 型抽出
- static 判定
- pointer / array / const の簡易判定

完了条件:

- 代表的な C90 関数定義のシグネチャを JSON 化できる

### Task 7: グローバルアクセス解析

成果物:

- file scope 変数候補抽出
- extern 変数候補抽出
- read / write 候補抽出
- unknown side effect 表示

完了条件:

- 指定関数の globals_read / globals_written 候補を出力できる

### Task 8: 外部呼び出し解析

成果物:

- 呼び出し式候補抽出
- 内部定義 / 外部定義の粗判定
- 標準ライブラリ候補除外
- stub_candidates 出力

完了条件:

- 指定関数の external_calls を出力できる

### Task 9: 分岐・条件解析

成果物:

- if / switch / loop 抽出
- 条件式抽出
- return 経路抽出
- coverage item ID 生成

完了条件:

- branch_condition_report.md を生成できる

### Task 10: 境界値・同値クラス候補生成

成果物:

- 比較演算子から境界値候補生成
- NULL チェック候補生成
- switch case 値候補生成
- parameter type から基本候補生成

完了条件:

- boundary_equivalence_candidates.md を生成できる

### Task 11: function_dossier 出力

成果物:

- JSON Schema
- `function_dossier.json`
- `function_dossier.md`
- CSV 設計案

完了条件:

- `analyze-function` で一式のレポートが生成される

### Task 12: build-probe

成果物:

- VC6 cl.exe 呼び出しテンプレート
- nmake 用 Makefile 生成
- include 不足検出
- 未解決シンボル抽出
- build_probe.log

完了条件:

- サンプルプロジェクトでビルドプローブを実行できる

### Task 13: VS Code 薄いアダプタ

成果物:

- VS Code extension 雛形
- settings 読み込み
- 現在ファイルと選択関数の取得
- CLI 実行
- レポートを開く

完了条件:

- VS Code から `analyze-function` を起動し、生成 Markdown を開ける

---

## 18. 受け入れ基準

Phase 1 の受け入れ基準は以下とする。

1. 本番リポジトリにテスト用ファイルを追加しない
2. `.dsw` / `.dsp` から対象 `.c` の所属プロジェクトを判定できる
3. 構成別の define / include ディレクトリを抽出できる
4. 対象 `.c` 内の指定関数を特定できる
5. 関数シグネチャを抽出できる
6. 参照・更新するグローバル変数候補を出力できる
7. 外部呼び出し候補を出力できる
8. 分岐・条件候補を出力できる
9. 境界値・同値クラス候補を出力できる
10. スタブ候補を出力できる
11. `function_dossier.json` と `function_dossier.md` を生成できる
12. VS Code または CLI から解析を開始できる
13. CODEX が次タスクを実装できる粒度の issue / task に分解されている

---

## 19. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| DSP 記述の揺れ | VC6 プロジェクトファイルの書式が案件ごとに異なる | fixture を増やし、未知行は保持して警告にする |
| 同じ .c が複数プロジェクトに所属 | define / include が異なり解析結果が変わる | 複数候補を表示しユーザー選択にする |
| PCH 依存 | `stdafx.h` や `/Yu` により単独コンパイルできない | PCH 情報を dossier に記録し、build-probe で警告する |
| マクロが複雑 | 関数定義や条件がマクロで隠れる | Phase 1 は候補抽出に留め、解析不能箇所を明示する |
| グローバル解析の誤判定 | ポインタやマクロ経由の読み書きが判定しにくい | confidence を付与し、unknown side effect として保守的に扱う |
| VS Code 拡張が先に肥大化 | UI 実装に時間がかかる | CLI コアを優先し、VS Code は薄いアダプタにする |
| AI の期待値誤生成 | 仕様にない期待値を作る | AI 出力はレビュー候補扱いにし、レビュー必須とする |
| いきなりモジュール単位に広げすぎる | 巨大モジュールで破綻する | Phase 1 は関数単位の dossier 生成に限定する |

---

## 20. Phase 2 以降の拡張候補

Phase 1 の成果を確認した後、以下を検討する。

### Phase 2: 関数単位テストハーネス生成

- C90 互換ミニテストランナー
- スタブ雛形生成
- グローバル初期化コード生成
- テストケース CSV から C テスト生成
- VC6 ビルド実行

### Phase 3: 設計カバレッジから実行カバレッジへ

- 分岐通過ログの埋め込み
- 条件評価ログの埋め込み
- return 経路ログ
- テストケースとカバレッジ項目の対応表

### Phase 4: モジュール単位への拡張

- 関数 dossier の集合化
- モジュール内関数依存グラフ
- モジュール単位のスタブ方針
- 巨大モジュール分割支援
- モジュールレベルのテスト計画生成

### Phase 5: リアルタイム性・ハードウェア依存への拡張

- 疑似時間
- 疑似割込
- ハードウェア I/O スタブ
- 32ms 制約からの分離
- 実機試験との役割分担整理

---

## 21. 初回リリースの定義

初回リリース `v0.1` は、テスト実行よりも **関数単位テストの準備情報を正確に集めること** を重視する。

`v0.1` に含めるもの:

- CLI skeleton
- DSW parser
- DSP parser
- source-to-project mapper
- function locator
- signature extractor
- build context collector
- global access candidate analyzer
- call candidate analyzer
- branch / condition candidate analyzer
- boundary / equivalence candidate generator
- function dossier generator
- Markdown / JSON / CSV report generator
- fixtures and unit tests

`v0.1` に含めないもの:

- 完全な自動テスト生成
- 完全なスタブ生成
- 実測カバレッジ計測
- リアルタイム制御対応
- ハードウェア割込対応
- モジュール単位テスト

---

## 22. まとめ

本計画では、最初のフェーズを **関数単位の単体テスト支援** に限定する。

巨大なモジュールを最初から対象にせず、ユーザーが VS Code 上で変更・追加した関数を選び、そこから `.dsw` / `.dsp` に基づく所属プロジェクト、define、include、ビルド構成、関数入出力、グローバル変数、外部呼び出し、分岐条件、境界値、同値クラス候補を収集する。

この段階では、実行可能なテストハーネスの完成よりも、単体テスト設計と自動生成に必要な dossier を安定して作れることを優先する。

CODEX は、本設計書のタスク分解に従って製造を進める。
Phase 1 の成果を確認した後、関数単位テストハーネス生成、実行カバレッジ、モジュール単位、リアルタイム性・ハードウェア依存対応へ段階的に拡張する。

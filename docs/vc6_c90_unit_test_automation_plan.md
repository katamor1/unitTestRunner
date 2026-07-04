# C90/VC6 リアルタイム制御アプリ向け 単体・モジュールテスト自動化計画書

作成日: 2026-07-04  
対象: C90 / Microsoft Visual C++ 6.0 で開発されているリアルタイム制御アプリケーション  
状態: Draft v0.1

---

## 1. 背景

対象アプリケーションは、本番機ではハードウェア割込制御を用いたリアルタイム制御を行っている。
一方、開発環境でアプリケーション全体を実行すると、32ms 経過時点で時間遵守違反となり、プログラムが停止する。

また、本番リポジトリには規約上、以下を持ち込めない。

- テスト専用ファイル
- テスト専用ヘッダ
- テスト専用コンパイルスイッチ
- 本番用途では不要なモック、スタブ、テストハーネス

そのため現状では、単体テストやモジュールテストを行うたびに、以下を手作業で行っている。

- テスト対象に必要な `.c` / `.h` ファイルの抽出
- 依存ヘッダ、マクロ、グローバル変数の調査
- ハードウェア依存部、割込依存部、時刻依存部のモック化・スタブ化
- VC6 でのビルド確認
- テストケース設計
- 実行ログ、ビルドログ、期待値確認結果などのエビデンス作成

この計画では、上記作業を本番リポジトリの外側で半自動化し、AI も補助的に使う。

---

## 2. 基本方針

### 2.1 本番リポジトリ非侵襲

本番リポジトリは読み取り専用入力として扱う。
テスト用ファイル、テスト用コンパイルスイッチ、生成物は本番リポジトリに置かない。

テスト実行時は、外部の作業ディレクトリに以下を生成する。

- 抽出済みソースツリー
- テストハーネス
- モック・スタブ
- VC6 / nmake 用ビルド定義
- テストケース
- 実行ログ
- エビデンス

### 2.2 VC6 / C90 優先

生成する C コードは、原則として C90 互換とする。

避けるもの:

- C99 以降の構文
- `stdint.h` 前提の型
- 変数宣言を文の途中に置く書き方
- `for (int i = 0; ... )` 形式
- `inline`
- 可変長配列
- `snprintf` 前提
- C++ 専用構文

### 2.3 32ms 制約からの分離

開発環境で全体アプリを起動しない。
単体・モジュール単位で、以下を差し替える。

- 時刻取得
- タイマ
- 割込通知
- I/O ポートアクセス
- ハードウェア状態取得
- OS / ドライバ呼び出し
- 本番用ウォッチドッグ、時間遵守監視

本番実行のリアルタイム性を再現するのではなく、ロジックを決定的に検証できる疑似環境を作る。

### 2.4 AI は生成係、判定はビルドと人間

AI は以下を補助する。

- 依存関係の要約
- テスト観点の抽出
- 境界値、異常値、状態遷移の候補出し
- スタブ仕様の草案作成
- テストケース表のドラフト作成
- エビデンス雛形の生成

ただし、AI の出力はそのまま正としない。
必ず以下のゲートを通す。

- スキーマ検証
- VC6 ビルド
- テスト実行
- レビュー
- エビデンス確認

---

## 3. 目標

### 3.1 短期目標

1 モジュールを指定すると、外部ワークスペースに単体テスト用プロジェクトを生成できる状態にする。

最低限、以下を生成する。

- 対象ソースと必要ヘッダの抽出結果
- 依存関係一覧
- 未解決シンボル一覧
- スタブ候補一覧
- C90 互換のテストランナー
- VC6 / nmake 用ビルドファイル
- ビルドログ
- 実行ログ
- テストケース設計ドラフト

### 3.2 中期目標

ビルドエラー、リンクエラー、未解決外部参照を解析し、スタブ生成を反復できる状態にする。

目指す流れ:

1. テスト対象モジュールを指定
2. 依存ファイルを抽出
3. ビルドを試行
4. 未解決シンボルを抽出
5. スタブ雛形を生成
6. 再ビルド
7. テストケースを生成・補正
8. 実行ログとエビデンスを出力

### 3.3 長期目標

頻繁にテストするモジュールについて、以下を再利用できるようにする。

- スタブカタログ
- モック仕様
- テストケーステンプレート
- ビルドプロファイル
- モジュール別テスト設定
- エビデンス出力テンプレート

---

## 4. 想定アーキテクチャ

```text
[本番リポジトリ: read only]
        |
        v
[unitTestRunner]
        |
        +-- ソース解析
        |     +-- include 解析
        |     +-- 関数プロトタイプ抽出
        |     +-- グローバル変数抽出
        |     +-- 未解決依存の検出
        |
        +-- テストワークスペース生成
        |     +-- 抽出ソース
        |     +-- 抽出ヘッダ
        |     +-- スタブ
        |     +-- モック
        |     +-- テストランナー
        |     +-- nmake / VC6 用定義
        |
        +-- AI 補助
        |     +-- テスト観点生成
        |     +-- スタブ仕様案生成
        |     +-- テストケース表生成
        |     +-- レビュー観点生成
        |
        +-- ビルド・実行
        |     +-- cl.exe
        |     +-- link.exe
        |     +-- nmake
        |
        +-- エビデンス生成
              +-- build.log
              +-- test.log
              +-- result.csv
              +-- test_spec.md
              +-- dependency_report.md
```

---

## 5. 主要コンポーネント案

### 5.1 モジュール抽出器

役割:

- テスト対象 `.c` ファイルを起点に include を解析する
- 必要なヘッダを外部ワークスペースへコピーする
- 本番リポジトリ内の相対パスを保持する
- 抽出元ファイル、抽出先ファイル、ハッシュ値を記録する

出力例:

```text
workspace/
  extracted/
    src/...
    include/...
  reports/
    extraction_report.md
    dependency_graph.json
```

### 5.2 依存解析器

役割:

- include 関係の一覧化
- 関数定義と関数宣言の抽出
- 外部参照の候補抽出
- グローバル変数の読み書き候補抽出
- ハードウェア依存 API の候補抽出

実装方針:

- 最初は完全な C パーサではなく、実用的な字句解析と正規表現ベースで開始する
- VC6 独自拡張や古いヘッダで壊れにくいことを優先する
- 解析精度が足りない箇所だけ手動アノテーションを許容する

### 5.3 スタブ生成器

役割:

- 未解決シンボルから C90 互換のスタブ雛形を生成する
- 呼び出し回数、引数、戻り値を記録できるようにする
- テストケースごとに戻り値や副作用を差し替えられるようにする

生成コード方針:

- C90 互換
- 動的メモリ確保に依存しない
- 例外、RTTI、テンプレートを使わない
- テストケース開始時に状態をリセットできる

スタブ例:

```c
/* generated stub: do not edit by hand */

static int stub_GetTimerTick_return_value;
static int stub_GetTimerTick_call_count;

void Stub_GetTimerTick_SetReturn(int value)
{
    stub_GetTimerTick_return_value = value;
}

void Stub_GetTimerTick_Reset(void)
{
    stub_GetTimerTick_return_value = 0;
    stub_GetTimerTick_call_count = 0;
}

int GetTimerTick(void)
{
    stub_GetTimerTick_call_count++;
    return stub_GetTimerTick_return_value;
}
```

### 5.4 疑似時間・疑似割込アダプタ

32ms の時間遵守違反を回避するため、実時間ではなくテスト制御可能な疑似時間を使う。

必要機能:

- 現在時刻を任意に進める
- タイマ満了を明示的に発火させる
- 割込発生をテストケースから指示する
- ウォッチドッグや時間遵守監視を無効化ではなく、スタブとして観測可能にする

方針:

- 本番コードは変更しない
- 外部ワークスペースでリンク時に差し替える
- 直接参照が強い場合は、抽出コピー側に限定して wrapper を使う

### 5.5 テストランナー

初期段階では、VC6 で確実に動く最小テストランナーを自前生成する。

理由:

- 古いコンパイラで外部フレームワークがそのまま通るとは限らない
- C90 制約を厳密に守りやすい
- 生成物を読みやすくできる
- エビデンス形式を現場ルールに合わせやすい

最小機能:

- `ASSERT_EQ_INT`
- `ASSERT_TRUE`
- `ASSERT_FALSE`
- `ASSERT_MEM_EQ`
- テスト件数、成功、失敗の集計
- 失敗箇所のファイル名、行番号出力
- CSV / テキストログ出力

### 5.6 AI 補助エンジン

AI にはソース全体を丸投げしない。
まずツール側で安全な要約情報を作り、AI に渡す。

AI へ渡す情報の例:

```json
{
  "module": "control.c",
  "functions": [
    {
      "name": "Control_Update",
      "return_type": "int",
      "parameters": ["int mode", "int sensor"],
      "globals_read": ["g_state"],
      "globals_written": ["g_error"],
      "external_calls": ["GetTimerTick", "ReadSensor", "WritePort"]
    }
  ],
  "constraints": {
    "compiler": "VC6",
    "language": "C90",
    "no_production_repo_changes": true
  }
}
```

AI 出力は JSON Schema で制約する。

```json
{
  "test_cases": [
    {
      "id": "TC_CONTROL_001",
      "target_function": "Control_Update",
      "purpose": "正常系の状態更新を確認する",
      "preconditions": [],
      "inputs": [],
      "stub_settings": [],
      "expected_results": [],
      "evidence_items": []
    }
  ]
}
```

---

## 6. ツール候補

### 6.1 MVP 推奨: 自前ミニハーネス

最初は自前ミニハーネスを推奨する。

理由:

- VC6 / C90 互換を制御しやすい
- 本番規約に合わせやすい
- 生成コードをレビューしやすい
- スタブ、疑似時間、疑似割込を現場都合で作り込める

### 6.2 Unity

Unity は C 向けのユニットテストフレームワークで、組込みツールチェーンを意識した構成になっている。
コアが小さく、既存ビルドへ組み込みやすいため、VC6 互換性を確認できれば有力候補になる。

使いどころ:

- 自前 assert を置き換えたい場合
- テスト記法を標準化したい場合
- 将来的に他環境でも同じテストを回したい場合

確認事項:

- 対象バージョンが VC6 でコンパイル可能か
- 生成・利用するヘッダが C90 の範囲に収まるか
- 本番リポジトリではなく unitTestRunner 側に vendoring できるか

### 6.3 Ceedling / CMock

Ceedling は C プロジェクト向けのビルド・テスト支援ツールで、Unity と CMock を組み合わせて使える。
モック生成やレポート生成の考え方は参考になる。

ただし、VC6 / C90 / Windows レガシー環境では、そのまま採用する前に検証が必要。

使いどころ:

- モダンなホスト環境での参考実装
- CMock 的なモック生成仕様の参考
- レポート出力やプロジェクト構成の参考

### 6.4 CppUTest

CppUTest は C/C++ 向けのユニットテスト・モックフレームワークである。
C++ ビルドを前提にできる箇所では候補になるが、VC6 互換性と C90 制約を考えると、初期 MVP の主軸にはしない。

使いどころ:

- VC6 C++ としてのビルドが許容されるサブセット
- モダン環境での比較検証
- モック API 設計の参考

---

## 7. 実装フェーズ

### Phase 0: 調査・制約整理

成果物:

- VC6 ビルドコマンドの整理
- include パス一覧
- コンパイル定義一覧
- 本番リポジトリで禁止されている変更の明文化
- ハードウェア依存 API 一覧
- 時刻・割込・ウォッチドッグ関連 API 一覧
- 最初に対象にする代表モジュール一覧

完了条件:

- 本番リポジトリに変更を入れずに、外部ワークスペースで対象モジュールのコンパイル試行ができる

### Phase 1: 抽出とビルドの MVP

成果物:

- モジュール指定用 manifest
- ソース・ヘッダ抽出処理
- VC6 / nmake ビルドファイル生成
- build.log 出力
- dependency_report.md 出力

完了条件:

- 代表モジュール 1 つについて、外部ワークスペースでビルドが実行される
- 失敗した場合も、未解決シンボルや include 不足がレポートされる

### Phase 2: スタブ生成と疑似時間

成果物:

- 未解決シンボルからのスタブ雛形生成
- スタブ戻り値設定 API
- 呼び出し回数記録
- 疑似時間 API
- 疑似割込 API
- テストケースごとの reset 処理

完了条件:

- 32ms の実時間制約に依存せず、テストケース側から時間・割込相当イベントを進められる

### Phase 3: テストケース設計支援

成果物:

- 依存関係要約 JSON
- AI 入力用プロンプトテンプレート
- AI 出力 JSON Schema
- テストケース Markdown / CSV 生成
- レビュー用チェックリスト

完了条件:

- AI が出したテストケース案を、スキーマ検証後に人間がレビューできる
- レビュー後のテストケースをハーネスへ反映できる

### Phase 4: エビデンス生成

成果物:

- build.log
- test.log
- result.csv
- test_spec.md
- stub_report.md
- dependency_report.md
- 実行環境情報
- 抽出元ファイルのハッシュ一覧

完了条件:

- テスト実行結果と入力条件を、後から追跡できる形式で残せる

### Phase 5: 継続実行・運用化

成果物:

- モジュール別 manifest の蓄積
- スタブカタログ
- テストケーステンプレート
- 自動実行スクリプト
- ローカルまたは self-hosted runner での実行手順

完了条件:

- よく使うモジュールは、コマンド一つで抽出、ビルド、実行、エビデンス生成まで再実行できる

---

## 8. manifest 案

初期は JSON 形式を推奨する。
YAML は読みやすいが、ツール側の依存ライブラリが増えるため、最初は標準ライブラリだけで扱いやすい JSON を優先する。

```json
{
  "profile": "vc6-c90",
  "source_root": "D:/work/production_repo",
  "workspace_root": "D:/work/unit_test_workspace",
  "target": {
    "name": "control_module",
    "sources": [
      "src/control.c"
    ],
    "public_headers": [
      "include/control.h"
    ]
  },
  "include_dirs": [
    "include",
    "src",
    "platform/include"
  ],
  "defines": [
    "WIN32",
    "_MBCS"
  ],
  "stub_policy": {
    "auto_generate_unresolved_symbols": true,
    "hardware_api_list": "profiles/hardware_apis.txt",
    "time_api_list": "profiles/time_apis.txt"
  },
  "evidence": {
    "output_format": ["text", "csv", "markdown"],
    "record_source_hash": true
  }
}
```

---

## 9. コマンド案

```bat
unit-test-runner.exe analyze manifests/control_module.json
unit-test-runner.exe generate manifests/control_module.json
unit-test-runner.exe build manifests/control_module.json
unit-test-runner.exe run manifests/control_module.json
unit-test-runner.exe evidence manifests/control_module.json
```

統合コマンド:

```bat
unit-test-runner.exe all manifests/control_module.json
```

---

## 10. 生成ディレクトリ案

```text
workspace/
  control_module/
    extracted/
      src/
      include/
    generated/
      runner/
      stubs/
      mocks/
      build/
    reports/
      dependency_report.md
      unresolved_symbols.txt
      stub_report.md
      test_spec.md
      result.csv
      build.log
      test.log
    temp/
```

---

## 11. AI 活用ポイント

### 11.1 依存関係の説明生成

入力:

- 関数一覧
- 外部呼び出し一覧
- グローバル変数一覧
- include グラフ

出力:

- テストしやすい関数
- モックが必要な関数
- 副作用が強い箇所
- 注意すべき状態変数

### 11.2 テスト観点生成

AI に作らせる候補:

- 正常系
- 境界値
- 異常値
- 状態遷移
- タイムアウト
- 割込順序
- センサ値異常
- I/O 失敗
- グローバル状態の初期化漏れ

### 11.3 スタブ仕様案生成

AI に作らせる候補:

- 戻り値パターン
- 呼び出し回数期待値
- 引数検証
- 疑似時間の進め方
- 割込発生順序

### 11.4 エビデンス雛形生成

AI に作らせる候補:

- テスト目的
- 前提条件
- 入力条件
- 期待結果
- 実行結果
- 判定
- 備考

---

## 12. セキュリティ・機密対策

AI 活用時は、以下の運用を原則とする。

- 本番ソースコード全文を外部 AI に送らない
- 送信する場合は、組織の承認を得る
- まずは関数シグネチャ、依存関係、コメント除去済み要約を使う
- 機密名、顧客名、装置名、型番をマスクできるようにする
- AI 出力はすべてローカルで検証する
- AI 出力を本番リポジトリへ直接反映しない

---

## 13. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| VC6 非互換 | 生成コードや外部フレームワークが VC6 で通らない | 自前ミニハーネスを MVP にする。C90 生成規約を持つ |
| include 解析漏れ | マクロや条件コンパイルで必要ファイルが変わる | manifest で include path / define を明示する。ビルドログから不足を反映する |
| static 関数が直接テストできない | ファイル内関数が外から見えない | 原則は公開関数経由。必要時のみ抽出コピー側で expose 方針を選択する |
| グローバル状態が残る | テスト間で結果が汚染される | reset 関数、初期化スナップショット、テストごとの再リンクを検討する |
| ハード依存が深い | I/O や割込がロジック内に直接書かれている | リンク時差し替え、wrapper、スタブカタログで分離する |
| AI の誤生成 | 存在しない API や誤った期待値を出す | JSON Schema、ビルド、実行、レビューを必須ゲートにする |
| エビデンス不足 | 後から再現できない | 入力 manifest、抽出ファイル hash、ビルドログ、実行ログを保存する |

---

## 14. 受け入れ基準

MVP の受け入れ基準:

- 本番リポジトリに変更を入れない
- 外部ワークスペースにテスト環境を生成できる
- VC6 / nmake でビルドを起動できる
- ビルド失敗時に原因候補をレポートできる
- 未解決シンボルからスタブ雛形を生成できる
- 1 つ以上のテストケースを実行できる
- build.log / test.log / result.csv を出力できる
- 抽出元ファイルと生成物の対応を追跡できる

---

## 15. unitTestRunner リポジトリ構成案

```text
unitTestRunner/
  docs/
    vc6_c90_unit_test_automation_plan.md
  src/
    analyzer/
    generator/
    builder/
    evidence/
  templates/
    vc6_c90/
      runner.c.tpl
      assert.h.tpl
      stub.c.tpl
      makefile.tpl
  profiles/
    vc6-c90.json
    hardware_apis.txt
    time_apis.txt
  manifests/
    samples/
  samples/
    minimal_c90_project/
  tests/
    selftest/
```

---

## 16. 初期プロトタイプの実装順

1. manifest 読み込み
2. 対象 `.c` ファイルのコピー
3. include path / define の反映
4. nmake 用 Makefile 生成
5. cl.exe ビルド実行
6. build.log 保存
7. LNK2001 などの未解決外部参照抽出
8. スタブ雛形生成
9. 最小テストランナー生成
10. test.log / result.csv 出力
11. dependency_report.md 出力
12. AI 用 dependency_digest.json 出力
13. AI から test_spec.json を受け取る処理
14. test_spec.md 生成

---

## 17. 参考情報

- Unity: C 向けユニットテストフレームワーク。組込みツールチェーンを意識した構成。
- Ceedling: C プロジェクト向けのビルド・テスト支援ツール。Unity と CMock を組み合わせる思想が参考になる。
- CppUTest: C/C++ 向けユニットテスト・モックフレームワーク。
- OpenAI Structured Outputs: AI 出力を JSON Schema に従わせる設計に利用できる。

---

## 18. まとめ

この計画の中心は、本番リポジトリを変更せずに、外部ワークスペースで単体・モジュールテスト環境を生成することである。

最初から大きなテストフレームワークを導入するよりも、VC6 / C90 / 本番規約 / 32ms 制約に合わせた小さな生成ツールを先に作る。
その上で、Unity、Ceedling、CMock、CppUTest などの考え方を必要に応じて取り込む。

AI は、テスト設計とモック設計の作業量を減らすために使う。
ただし、AI を判定者にせず、ビルド・実行・レビュー・エビデンスで必ず検証する。

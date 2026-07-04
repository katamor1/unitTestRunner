# unitTestRunner 計画レビュー: 現状評価と今後の展望

作成日: 2026-07-04  
状態: Draft v0.1  
対象リポジトリ: `katamor1/unitTestRunner`  
対象文書: `docs/implementation/step02` から `step16` まで、および関連ADR・設計書

---

## 1. 概要

ここまでの計画では、C90 / VC6 で開発されている既存アプリケーションに対して、まず **関数単位** の単体テスト支援を成立させるための段階的なロードマップを定義した。

初期方針として、以下を一貫して守る構成になっている。

- 本番リポジトリを変更しない
- テスト用ファイル、スタブ、ハーネス、生成物は外部ワークスペースへ出す
- モジュール単位ではなく、まず関数単位から始める
- 初期フェーズではリアルタイム性、32ms制約、疑似割込、疑似時間へ踏み込まない
- VC6 / C90 互換を重視する
- AIやCODEXは製造・設計補助に使うが、最終判定はビルド、ログ、レビュー、エビデンスに置く

計画は、以下の大きな流れに整理できる。

```text
VC6プロジェクト解析
  -> Cソース解析
  -> 関数インターフェース解析
  -> 副作用・呼び出し・分岐解析
  -> 境界値・同値クラス候補生成
  -> テストケース草案生成
  -> スタブ・ハーネス雛形生成
  -> ビルドワークスペース生成
  -> ビルドエラー補完
  -> テスト実行・エビデンス準備
```

この構成は、いきなり巨大モジュール全体をテストしようとせず、関数単位の dossier を積み上げ、後からモジュール単位へ拡張するための土台として妥当である。

---

## 2. ここまでに定義した計画の到達点

### 2.1 計画済みステップ

| Step | 名称 | 主な成果 |
|---:|---|---|
| 01 | Python package skeleton | 実装基盤。ADRで前提化済み |
| 02 | CLI Entry Point | `unit-test-runner` の入口、終了コード、JSON出力、stubコマンド |
| 03 | DSW Parser | `.dsw` から `.dsp`、プロジェクト、依存関係を発見 |
| 04 | DSP Parser | `.dsp` からsource membership、define、include、build contextを取得 |
| 05 | C Source Lexer / Masker | コメント・文字列・プリプロセッサを安全に扱う前処理 |
| 06 | Function Locator | 指定関数の定義位置、本文範囲、header範囲を特定 |
| 07 | Signature Extractor | 戻り値、引数、ポインタ、配列、calling convention等を抽出 |
| 08 | Global Access Analyzer | グローバル、file static、extern、引数副作用候補を抽出 |
| 09 | Call Analyzer | 呼び出し先、引数、戻り値利用、スタブ候補を抽出 |
| 10 | Branch / Condition Analyzer | 分岐、条件、loop、switch、return経路の設計カバレッジ生成 |
| 11 | Boundary / Equivalence Candidate Generator | 境界値、同値クラス、NULL、状態、スタブ戻り値候補を生成 |
| 12 | Test Case Draft Generator | レビュー可能なテストケース草案をJSON/Markdown/CSVで生成 |
| 13 | Stub / Harness Skeleton Generator | C90/VC6向けスタブ・ハーネス・テスト関数雛形を生成 |
| 14 | Build Workspace / Build Probe Generator | 外部workspace、Makefile、build probe、ログ診断を生成 |
| 15 | Build Error Analyzer / Stub Completion Loop | include不足、未解決symbol、PCH問題の補完計画と限定適用 |
| 16 | Test Execution / Evidence Preparation | 明示実行、結果解析、CSV、エビデンスmanifestを生成 |

Step 01 は明示的な個別計画書ではなく、ADR-0001でCODEX製造順の先頭として定義されている。Step 02以降は個別の実装計画として文書化済みである。

### 2.2 生成される成果物の全体像

最終的な関数単位ワークスペースでは、概ね以下の成果物が揃う想定である。

```text
workspace/<function>/
  extracted/
    src/
    include/
  generated/
    include/
    harness/
    stubs/
    tests/
  build/
    Makefile
    build.bat
    clean.bat
  obj/
  bin/
  logs/
    build.log
    compile.log
    link.log
    test_execution.log
  reports/
    source_digest.json
    function_location.json
    function_signature.json
    global_access.json
    call_report.json
    coverage_design.json
    boundary_equivalence_candidates.json
    test_case_draft.json
    harness_skeleton_report.json
    build_workspace_report.json
    build_probe_report.json
    build_completion_plan.json
    test_execution_report.json
    test_result.csv
    evidence_manifest.json
    evidence_package.md
```

この成果物構成は、単体テストの自動生成そのものだけでなく、**なぜそのテストが必要なのか、どの入力・状態・スタブ条件に由来するのか、どこまで実行できたのか** を追跡できる点が強い。

---

## 3. 現状評価

### 3.1 総合評価

現状の計画は、かなり堅実である。

特に良い点は、最初から「テストを完全自動生成して一発で通す」ことを狙っていない点である。VC6 / C90 / 本番リポジトリ非侵襲 / 古いプロジェクトファイル / PCH / 巨大モジュール / static関数 / グローバル状態 / 未解決シンボルという難所を考えると、いきなり万能ツールを作るのは危険である。

今回の計画は、以下のように段階を分けている。

1. まずプロジェクト構造を把握する
2. 次に関数を安全に見つける
3. 関数の入出力・副作用・呼び出し・分岐を候補として整理する
4. テスト設計候補を作る
5. C90互換の雛形を作る
6. ビルドし、ログから補完する
7. 実行とエビデンスへ進む

この順序は、レガシーCプロジェクト向けの現実的な自動化として筋が良い。

### 3.2 強み

#### 3.2.1 本番リポジトリ非侵襲が一貫している

すべての段階で、本番リポジトリを読み取り専用入力として扱う方針が維持されている。

これは、規約上テスト用ファイルやコンパイルスイッチを本番リポジトリへ持ち込めないという制約に対して、最も重要な設計判断である。

#### 3.2.2 関数単位から始める判断が妥当

モジュール単位では巨大な `.c` ファイルや依存関係が障害になりやすい。

そのため、まず対象 `.c` と関数名を指定し、`.dsw` / `.dsp` による所属判定、build context、関数範囲、シグネチャ、グローバル、呼び出し、分岐、テスト観点へ進む構成は妥当である。

#### 3.2.3 解析結果を段階的な中間成果物にしている

`source_digest`、`function_location`、`function_signature`、`global_access`、`call_report`、`coverage_design`、`boundary_equivalence_candidates`、`test_case_draft` のように、中間成果物が明確に分かれている。

これにより、以下が可能になる。

- 各Stepを単体テストしやすい
- CODEXへ小さな製造タスクとして渡しやすい
- 解析誤りの原因を追いやすい
- 後続Stepを差し替えやすい
- AIに渡す情報を限定しやすい

#### 3.2.4 VC6 / C90への配慮が早い段階から入っている

生成コードではC99以降の構文、`stdint.h`、`stdbool.h`、途中変数宣言、`for (int i...)`、`inline`、可変長配列などを避ける方針が明記されている。

この制約は、実装後に気づくと手戻りが大きい。Step 13より前から制約として置けているのは良い。

#### 3.2.5 ビルド失敗を前提にした設計になっている

Step 14 / 15 で、include不足、PCH問題、未解決symbol、VC6非互換生成コードを構造化し、反復補完する計画になっている。

レガシーCのテスト抽出では、初回ビルドが通らないことのほうが普通である。失敗を異常ではなく情報源として扱う設計はかなり重要である。

#### 3.2.6 期待結果を勝手に確定しない

Step 12 / 16 では、期待戻り値や期待グローバル値を `TBD` / `review_required` / `inconclusive` として扱う。

これは非常に重要である。ソース解析だけで仕様上の期待値を断定すると、もっともらしいが間違ったテストを量産する危険がある。期待値をレビュー対象として残す方針は安全である。

### 3.3 弱み・注意点

#### 3.3.1 計画がかなり大きくなっている

Step 02からStep 16までで、対象範囲はCLI、VC6 project parser、C lexer、関数解析、テスト設計、コード生成、ビルド、補完、実行、エビデンスまで広がっている。

全体としては妥当だが、最初から全Stepを実装しようとすると重すぎる。

まずは、明確な MVP を切る必要がある。

#### 3.3.2 C解析の精度リスクが高い

Step 05からStep 10は、Cソースの軽量解析に強く依存する。

以下は誤判定しやすい。

- 複雑なmacro
- typedef-likeな型
- 関数ポインタ
- K&R style
- 条件コンパイル
- static関数
- PCH前提のソース
- local/global shadowing
- 複雑なポインタ副作用

計画では `confidence` と `warning` を持つ設計になっているため対策はあるが、実装では「高精度に見せすぎない」ことが重要である。

#### 3.3.3 Step 13以降は環境依存が強い

VC6 / nmake / cl.exe / link.exe / PCH / Windows path / cp932 / 既存include構成など、環境依存要素が大きい。

Step 14以降は、ユニットテストだけでは検証しきれない。実際のVC6環境またはそれに近いfixture環境で、段階的な実証が必要である。

#### 3.3.4 テストケース草案と実行可能テストの間にレビュー工程が必要

Step 12ではテストケース草案を生成し、Step 13ではハーネス雛形へ変換する。

ただし、期待値が未確定のまま実行可能コードへ進むと、placeholderで通るだけのテストになり得る。

そのため、Step 12とStep 13の間、またはStep 16の結果レビュー時に、必ず人間レビューのゲートを設けるべきである。

#### 3.3.5 VS Code連携は後回しでよい

当初の理想UXとしてVS Codeから関数選択して開始する形が挙がっていた。

ただし、ここまでの計画を見る限り、まずCLIコアを安定させるほうが重要である。VS Code拡張は薄いadapterとして後から載せるのがよい。

---

## 4. MVPとして切り出すべき範囲

全16Stepを一気に実装するのではなく、MVPを3段階に分けることを推奨する。

### 4.1 MVP-1: VC6プロジェクト構造と関数特定

対象Step:

- Step 02: CLI Entry Point
- Step 03: DSW Parser
- Step 04: DSP Parser
- Step 05: C Source Lexer / Masker
- Step 06: Function Locator
- Step 07: Signature Extractor

MVP-1のゴール:

```text
指定した .c と関数名について、
どのVC6プロジェクトに属し、
どのdefine/includeでビルドされ、
関数がどこにあり、
どんな戻り値・引数を持つかをreportできる。
```

成果物:

- `build_context.json`
- `source_digest.json`
- `function_location.json`
- `function_signature.json`
- Markdown report

このMVPだけでも、現状の手作業で行っている「関数をテスト対象として切り出す前の調査」をかなり削減できる。

### 4.2 MVP-2: テスト設計支援

対象Step:

- Step 08: Global Access Analyzer
- Step 09: Call Analyzer
- Step 10: Branch / Condition Analyzer
- Step 11: Boundary / Equivalence Candidate Generator
- Step 12: Test Case Draft Generator

MVP-2のゴール:

```text
指定関数について、
参照・更新する状態、
外部依存、
分岐・条件・return経路、
境界値・同値クラス候補、
テストケース草案を出せる。
```

成果物:

- `global_access.json`
- `call_report.json`
- `coverage_design.json`
- `boundary_equivalence_candidates.json`
- `test_case_draft.json/md/csv`

この段階で、テストケース設計のたたき台とレビュー表が作れる。

### 4.3 MVP-3: 雛形生成とビルドプローブ

対象Step:

- Step 13: Stub / Harness Skeleton Generator
- Step 14: Build Workspace / Build Probe Generator
- Step 15: Build Error Analyzer / Stub Completion Loop

MVP-3のゴール:

```text
テストケース草案からC90/VC6向け雛形を生成し、
外部workspaceでビルド試行し、
不足includeや未解決symbolを構造化して次の補完へ回せる。
```

成果物:

- generated stubs
- generated harness
- generated test skeleton
- `build_workspace_report.json`
- `build_probe_report.json`
- `build_completion_plan.json`

ここまで来ると、単なる設計支援ではなく、ビルド確認まで含むテスト準備ツールになる。

### 4.4 MVP-4: 実行とエビデンス

対象Step:

- Step 16: Test Execution / Evidence Preparation
- Step 17予定: Function Dossier Finalizer / Review Workflow

MVP-4のゴール:

```text
ビルド済みの関数単位テストを明示実行し、
結果とログと未解決事項を証跡としてまとめる。
```

成果物:

- `test_execution_report.json/md`
- `test_result.csv`
- `evidence_manifest.json`
- `evidence_package.md`
- final `function_dossier`

---

## 5. 今後の展望

### 5.1 Step 17: Function Dossier Finalizer / Review Workflow

次に計画すべきStepは、Step 17である。

Step 17では、Step 04からStep 16までの成果物を統合し、最終的な `function_dossier` を生成する。

想定成果物:

- `function_dossier.json`
- `function_dossier.md`
- `review_checklist.md`
- `unresolved_items.md`
- `next_actions.md`
- `traceability_matrix.csv`

主な役割:

- 関数の所属プロジェクト、build context、関数位置、シグネチャをまとめる
- グローバルアクセス、呼び出し、分岐、境界値、テストケース草案を一望できるようにする
- 生成ハーネス、ビルド結果、実行結果、エビデンスを紐付ける
- 未解決事項をレビュー項目に変換する
- 次に必要な手作業、仕様確認、スタブ補正、期待値確定を明確化する

このStepにより、ツールの成果物が単なるJSON群ではなく、レビュー可能な1つの成果物になる。

### 5.2 Step 18: VS Code Thin Adapter

CLIコアがMVP-1またはMVP-2まで安定した段階で、VS Code連携を追加するのがよい。

候補機能:

- 現在開いている `.c` ファイルから関数一覧を取得
- カーソル位置の関数を推定
- `UnitTestRunner: Analyze Current Function`
- `UnitTestRunner: Open Function Dossier`
- `UnitTestRunner: Generate Test Draft`
- `UnitTestRunner: Open Workspace Reports`

重要なのは、VS Code拡張は解析ロジックを持たないことである。

VS CodeはあくまでCLIを呼び出す薄いadapterにし、解析・生成・レポートはPython CLIに集約する。

### 5.3 Step 19: モジュール単位への拡張検討

関数単位のdossierが十分に溜まった後、モジュール単位への拡張を検討する。

モジュール拡張で扱うべきこと:

- 関数dossierの集合化
- モジュール内関数依存グラフ
- static関数群の関係
- 共通スタブの再利用
- モジュール単位のglobal状態初期化
- 複数関数をまたぐテスト観点
- 巨大モジュールの分割支援

ただし、モジュール単位は依存が急に増えるため、関数単位で実績が出るまで急がないほうがよい。

### 5.4 Step 20: リアルタイム性・疑似時間・疑似割込への拡張

初期フェーズではリアルタイム性を扱わない方針だった。

将来的に扱う場合は、関数単位・モジュール単位のロジック検証が安定してから、以下を検討する。

- 疑似時間API
- 疑似タイマ
- 疑似割込イベント
- ウォッチドッグ・時間遵守監視の観測用stub
- 32ms制約を実時間ではなく論理時間で検証する仕組み
- 実機試験とホスト単体テストの責務分担

ここは最も難しい領域なので、最初のMVPには入れない判断を継続するのがよい。

### 5.5 AI活用の拡張

AIは、以下に使うのが適している。

- function dossier の要約
- テスト観点のレビュー支援
- 未解決事項の分類
- スタブ方針の説明文生成
- テストケース草案の自然言語化
- レビュー観点チェックリスト生成
- 仕様書がある場合の期待値候補の照合

一方で、以下はAIに任せすぎないほうがよい。

- 期待結果の確定
- 安全性・リアルタイム性の妥当性判断
- 本番コードの修正
- 生成コードの無審査適用
- ビルド失敗の強引な自動修正

AI出力は、必ずJSON Schema、ビルド、テスト、レビュー、エビデンスのゲートを通すべきである。

---

## 6. 実装優先順位

### 6.1 最優先

1. Step 02 CLI基盤
2. Step 03 DSW Parser
3. Step 04 DSP Parser
4. Step 05 C Source Lexer / Masker
5. Step 06 Function Locator
6. Step 07 Signature Extractor

この6ステップで、まず「対象関数を発見して、関数インターフェースを整理する」ことを成功させる。

### 6.2 次点

7. Step 08 Global Access Analyzer
8. Step 09 Call Analyzer
9. Step 10 Branch / Condition Analyzer
10. Step 11 Boundary / Equivalence Candidate Generator
11. Step 12 Test Case Draft Generator

この段階で、手作業のテスト設計工数を減らす。

### 6.3 その後

12. Step 13 Stub / Harness Skeleton Generator
13. Step 14 Build Workspace / Build Probe Generator
14. Step 15 Build Error Analyzer / Stub Completion Loop

この段階で、設計支援からビルド可能な雛形生成へ進む。

### 6.4 最後

15. Step 16 Test Execution / Evidence Preparation
16. Step 17 Function Dossier Finalizer / Review Workflow
17. VS Code Thin Adapter
18. モジュール単位拡張
19. リアルタイム性・疑似時間・疑似割込拡張

---

## 7. 直近の推奨アクション

### 7.1 Step 02からStep 07までをMVP-1として実装する

まずは、以下をコマンド1つで出せる状態にする。

```bat
unit-test-runner analyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Control - Win32 Debug" ^
  --out D:\work\unit_test_workspace\Control_Update
```

MVP-1の成功条件:

- `.dsw` / `.dsp` から所属プロジェクトを判定できる
- define / include / PCH情報を取得できる
- 指定関数の位置を特定できる
- 戻り値・引数を抽出できる
- `function_signature.md` まで出せる

この時点で、現場の「テスト対象関数の調査」工数を削減できる。

### 7.2 Fixtureを先に厚くする

実装前に、以下のfixtureを用意するべきである。

- minimal DSW/DSP
- Debug/Release構成DSP
- include/define/PCHを含むDSP
- simple C function
- static function
- multiline signature
- pointer parameter
- old K&R style
- cp932コメント
- macroを含む条件コンパイル

fixtureが弱いと、CODEXがもっともらしいparserを作っても現場コードに耐えられない。

### 7.3 解析精度を数値化する

各Stepの成果物には `confidence` と `warnings` がある。

これを使って、MVP-1時点から以下のような簡易品質指標を出すとよい。

```text
function found: yes/no
signature parsed: high/medium/low
warnings: count
unknown tokens: count
inactive/unknown conditional regions: count
```

これにより、「この関数は自動化に向いている」「この関数は手動レビューが多い」という判断ができる。

### 7.4 早い段階で実プロジェクト1つに当てる

サンプルfixtureだけで進めると、VC6プロジェクトファイルの揺れやPCH依存に後から苦しむ。

MVP-1が動いた時点で、実プロジェクトの小さめの `.c` と単純な関数に当てるべきである。

おすすめ対象:

- ハードウェアI/Oを直接触らない関数
- 引数と戻り値が単純な関数
- global依存が少ない関数
- staticでない関数
- 分岐が数個ある関数

### 7.5 Step 12以降はレビュー運用を先に決める

テストケース草案、スタブ雛形、期待値placeholderが出始めると、人間レビューが必要になる。

そのため、以下の運用を先に決めたほうがよい。

- `review_required` を誰が見るか
- `TBD_EXPECTED_*` をどの資料で確定するか
- file staticのsetup困難をどう扱うか
- スタブ戻り値は仕様書ベースか、現行動作ベースか
- エビデンスとして必要な粒度はどこまでか

---

## 8. 成功指標

### 8.1 短期指標

MVP-1で見る指標:

- 指定関数の発見成功率
- `.dsw` / `.dsp` 解析成功率
- build context 抽出成功率
- signature 抽出成功率
- warning件数
- 1関数あたりの調査時間削減量

### 8.2 中期指標

MVP-2で見る指標:

- global access候補の有用率
- call_reportのstub候補妥当率
- coverage_designのレビュー採用率
- boundary/equivalence候補の採用率
- test_case_draftのレビュー修正量
- テスト設計表作成時間の削減量

### 8.3 長期指標

MVP-3以降で見る指標:

- harness skeleton生成成功率
- 初回build probe到達率
- build completion loopによる未解決symbol削減率
- 実行可能テスト生成率
- evidence package生成率
- 手作業スタブ作成時間の削減量

---

## 9. 最終評価

ここまでの計画は、単なる「テスト自動生成ツール」ではなく、レガシーVC6/C90プロジェクトに対して、関数単位テストを進めるための **解析・設計・生成・ビルド・証跡化パイプライン** として整理されている。

評価としては、次の通りである。

| 観点 | 評価 | コメント |
|---|---|---|
| 方針の妥当性 | 高い | 本番非侵襲、関数単位開始、VC6/C90重視が一貫している |
| 実装可能性 | 中〜高 | Python CLI中心で分割されており実装しやすいが、C解析は難所 |
| MVP切り出し | 要整理 | 全16Stepは大きい。MVP-1から段階実装すべき |
| 現場適合性 | 高い | 手作業の抽出、依存調査、テスト設計、エビデンス作成に直接効く |
| リスク管理 | 中〜高 | warning/confidence/review_required方針は良い。fixture強化が必須 |
| AI活用余地 | 高い | dossier要約、観点生成、レビュー支援に向いている |
| 自動化しすぎリスク | 管理可能 | 期待値確定や本番修正を避ける方針が明確 |

結論として、現状の計画は十分に前へ進める価値がある。

ただし、次に必要なのはさらなる計画追加ではなく、**MVP-1の実装着手** である。
特に、CLI、DSW/DSP解析、C Source Masker、Function Locator、Signature Extractorまでを小さく実装し、実プロジェクトの単純な関数で検証するのが最も効果的である。

---

## 10. 推奨ロードマップ

```text
Phase A: 実装基盤
  - Step 02
  - package skeleton
  - CLI / JSON / logging / tests

Phase B: VC6 project解析
  - Step 03
  - Step 04
  - DSW/DSP fixture整備

Phase C: 関数特定MVP
  - Step 05
  - Step 06
  - Step 07
  - 実関数でsignature reportまで出す

Phase D: テスト設計支援
  - Step 08
  - Step 09
  - Step 10
  - Step 11
  - Step 12

Phase E: 雛形生成とビルド
  - Step 13
  - Step 14
  - Step 15

Phase F: 実行と証跡
  - Step 16
  - Step 17

Phase G: 利便性・拡張
  - VS Code Thin Adapter
  - モジュール単位拡張
  - 疑似時間・疑似割込
```

この順序で進めることで、途中段階でも価値を出しながら、最終的な関数単位テスト自動化へ段階的に近づけられる。

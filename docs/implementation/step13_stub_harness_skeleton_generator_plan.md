# Step 13: Stub / Harness Skeleton Generator 実装計画

作成日: 2026-07-04  
状態: Draft v0.1  
対象リポジトリ: `katamor1/unitTestRunner`  
製造担当想定: CODEX  
前提文書:

- `docs/adr/0001-cli-layer-language-selection.md`
- `docs/implementation/step02_cli_entry_point_plan.md`
- `docs/implementation/step03_dsw_parser_plan.md`
- `docs/implementation/step04_dsp_parser_plan.md`
- `docs/implementation/step05_c_source_lexer_masker_plan.md`
- `docs/implementation/step06_function_locator_plan.md`
- `docs/implementation/step07_signature_extractor_plan.md`
- `docs/implementation/step08_global_access_analyzer_plan.md`
- `docs/implementation/step09_call_analyzer_plan.md`
- `docs/implementation/step10_branch_condition_analyzer_plan.md`
- `docs/implementation/step11_boundary_equivalence_candidate_generator_plan.md`
- `docs/implementation/step12_test_case_draft_generator_plan.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第13ステップとして **Stub / Harness Skeleton Generator** を実装するための計画である。

Step 12 では、Step 04 から Step 11 までの解析結果を統合し、レビュー可能な `test_case_draft` を生成する計画を定義した。
Step 13 では、Step 09 の `stub_candidates` と Step 12 の `test_case_draft` を使い、VC6 / C90 互換を意識した **スタブ雛形、テストランナー雛形、テストケース関数雛形、生成物一覧レポート** を外部ワークスペースへ生成する。

Step 13 は、実行可能なテスト環境の完成ではない。
この段階では、VC6でビルド可能に近づけるためのCコード雛形を生成するが、ビルド実行、リンクエラー解析、未解決シンボルの反復補完は Step 14 以降で扱う。

Step 13 の主な責務は以下である。

- `test_case_draft` から C90 互換のテストケース関数雛形を生成する
- `call_report.stub_candidates` からスタブ関数雛形を生成する
- スタブの戻り値設定、呼び出し回数記録、引数記録、reset API の雛形を生成する
- 期待観測placeholderをassert placeholderへ変換する
- 最小テストランナー雛形を生成する
- 対象関数呼び出しのwrapper雛形を生成する
- 生成CコードでVC6/C90非互換構文を避ける
- 本番リポジトリではなく外部ワークスペース配下にのみ生成する
- `harness_skeleton_report.json` / Markdown を生成する
- Step 14 の Build Workspace / Build Probe Generator に渡せる生成物情報を整理する

---

## 2. 目的

Step 13 の目的は、レビュー済みまたはレビュー前のテストケース草案を、VC6 / C90 でビルド検証へ進められる **Cコード雛形群** に変換することである。

具体的には、以下を実現する。

- `test_case_draft.json` から `test_*.c` のテストケース関数雛形を生成できる
- 外部依存関数ごとに `stub_*.c` / `stub_*.h` の雛形を生成できる
- スタブごとに戻り値設定APIを生成できる
- スタブごとに呼び出し回数取得APIを生成できる
- 必要に応じて引数記録用の領域を生成できる
- テストケース開始時のreset処理を生成できる
- `ASSERT_EQ_INT`、`ASSERT_TRUE`、`ASSERT_FALSE`、`ASSERT_PTR_NULL` などの最小assert雛形を生成できる
- 期待値未確定箇所は `TBD_EXPECTED_*` としてコンパイル上は安全なplaceholderにできる
- 期待値未確定、file static setup困難、スタブ未確定などをwarningとして保持できる
- 生成物一覧、生成元test case、関連stub candidateを追跡できる
- `harness_skeleton_report.json` / `harness_skeleton_report.md` を出力できる
- `analyze-function` を Step 13 時点で「テストケース草案 + スタブ/ハーネス雛形生成」まで進められる

---

## 3. スコープ

### 3.1 実装対象

Step 13 で実装するもの:

1. Harness model
   - harness generation request
   - generated file metadata
   - stub skeleton spec
   - test case skeleton spec
   - assertion placeholder
   - build hint
   - warning

2. Stub skeleton generator
   - external function stub雛形
   - return value control API
   - call count API
   - argument capture API
   - side effect placeholder
   - reset API
   - header/source分割

3. Test runner skeleton generator
   - minimal assert macro
   - test registration table
   - test execution loop
   - result count
   - stdout text output
   - C90 compatible code style

4. Test case skeleton generator
   - `test_case_draft` から test function生成
   - input assignment comment / code placeholder
   - state setup comment / code placeholder
   - stub setup call placeholder
   - target function call placeholder
   - expected observation assert placeholder

5. Target invocation generator
   - 関数シグネチャから呼び出し式を生成
   - 戻り値あり / void戻り値の差分対応
   - pointer / array引数のfixture placeholder

6. Generated artifact layout
   - `generated/harness`
   - `generated/stubs`
   - `generated/tests`
   - `generated/include`
   - `reports`

7. Reports
   - `harness_skeleton_report.json`
   - `harness_skeleton_report.md`
   - generated file list
   - unresolved placeholder list

8. CLI 接続
   - `analyze-function` を harness skeleton生成まで進める
   - 新規または後続拡張コマンド `generate-harness-skeleton` を検討する
   - status `partial` または `harness_skeleton_generated` を返す
   - Step 14 の Build Workspace / Build Probe Generator が必要である旨を message に含める

9. Tests
   - simple stub
   - return value stub
   - void stub
   - pointer argument capture
   - call count
   - test case skeleton
   - unknown expected placeholder
   - C90 syntax guard
   - generated report

### 3.2 対象外

Step 13 では以下を対象外とする。

- VC6 / nmake / cl.exe の実行
- 実際のビルド成功確認
- リンクエラー解析
- 未解決シンボルの自動反復補完
- 実行可能なテストバイナリの生成確認
- 期待結果の最終確定
- スタブ動作仕様の完全確定
- ハードウェアI/Oの実動作再現
- 疑似時間・疑似割込の実装
- 本番リポジトリへの生成物追加
- 本番ソースの変更
- 外部テストフレームワークの導入確定

Step 13 では、あくまでビルド検証へ進むためのC90/VC6向け雛形生成に限定する。

---

## 4. 入力と出力

### 4.1 入力

主入力:

- Step 04 の `build_context`
- Step 07 の `function_signature`
- Step 08 の `global_access`
- Step 09 の `call_report`
- Step 12 の `test_case_draft`
- 生成先workspace path

入力イメージ:

```json
{
  "source": "D:/work/product/src/control.c",
  "function": "Control_Update",
  "build_context": "reports/build_context.json",
  "function_signature": "reports/function_signature.json",
  "global_access": "reports/global_access.json",
  "call_report": "reports/call_report.json",
  "test_case_draft": "reports/test_case_draft.json",
  "output_root": "D:/work/unit_test_workspace/Control_Update"
}
```

### 4.2 出力

Step 13 の主要出力は `generated` 配下のCコード雛形と `harness_skeleton_report` である。

```text
workspace/
  Control_Update/
    generated/
      include/
        utr_assert.h
        utr_runner.h
        utr_stub_registry.h
      harness/
        utr_assert.c
        utr_runner.c
        target_invocation.c
        target_invocation.h
      stubs/
        stub_ReadSensor.c
        stub_ReadSensor.h
        stub_WritePort.c
        stub_WritePort.h
      tests/
        test_Control_Update.c
        test_Control_Update_cases.h
    reports/
      test_case_draft.json
      harness_skeleton_report.json
      harness_skeleton_report.md
```

`harness_skeleton_report.json` は Step 14 以降の入力になる。

---

## 5. C90 / VC6 生成コード制約

### 5.1 必須制約

生成するCコードは、VC6 / C90互換を優先する。

避けるもの:

- C99以降の構文
- 変数宣言の途中配置
- `for (int i = 0; ... )`
- `stdint.h`
- `stdbool.h`
- `inline`
- 可変長配列
- 指定初期化子
- 複合リテラル
- `snprintf` 前提
- C++専用構文
- `//` コメントのみへの依存

方針:

- 変数宣言はブロック先頭にまとめる
- `int` / `char` / `void *` などVC6で扱いやすい型を優先する
- bool相当は `int` と `0/1` を使う
- コメントは原則 `/* ... */` にする
- 生成コードには `TBD` と `review required` コメントを明示する

### 5.2 placeholder方針

期待値やfixtureが未確定の箇所は、コンパイル可能性を優先してplaceholderを置く。

例:

```c
#define TBD_EXPECTED_RETURN_INT (0)
#define TBD_VALID_INT_VALUE (0)
#define TBD_VALID_PTR_VALUE (0)
```

ただし、pointerの非NULL候補など、安易に `0` を入れると意味が変わるものはwarningを出し、fixture生成を後続Stepへ委ねる。

---

## 6. データモデル設計

### 6.1 HarnessGenerationRequest

```python
@dataclass
class HarnessGenerationRequest:
    output_root: Path
    build_context: BuildContext
    function_signature: FunctionSignature
    global_access: GlobalAccessReport
    call_report: CallReport
    test_case_draft: TestCaseDraftReport
    generation_policy: HarnessGenerationPolicy
```

役割:

- Stub / Harness Skeleton Generator の入力条件をまとめる
- CLI / internal usecase の境界を明確にする

### 6.2 HarnessGenerationPolicy

```python
@dataclass
class HarnessGenerationPolicy:
    c_dialect: str
    compiler_profile: str
    generate_stub_headers: bool
    generate_argument_capture: bool
    generate_call_count_assertions: bool
    generate_placeholder_assertions: bool
    fail_on_unresolved_expected: bool
    overwrite_existing: bool
```

既定方針:

- `c_dialect = "c90"`
- `compiler_profile = "vc6"`
- `generate_stub_headers = true`
- `generate_argument_capture = true`
- `generate_call_count_assertions = true`
- `generate_placeholder_assertions = true`
- `fail_on_unresolved_expected = false`
- `overwrite_existing = false`

### 6.3 HarnessSkeletonReport

```python
@dataclass
class HarnessSkeletonReport:
    source_path: Path
    function_name: str
    status: str
    output_root: Path
    generated_files: list[GeneratedFile]
    stub_skeletons: list[StubSkeleton]
    test_skeletons: list[TestSkeleton]
    unresolved_placeholders: list[UnresolvedPlaceholder]
    build_hints: list[BuildHint]
    warnings: list[HarnessGenerationWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `generated` | 雛形生成が完了した |
| `partial` | 一部未解決があるが主要雛形を生成した |
| `blocked` | 必須情報不足で生成できない |
| `skipped` | 既存ファイル保護などで生成しなかった |

### 6.4 GeneratedFile

```python
@dataclass
class GeneratedFile:
    path: Path
    file_kind: str
    generated_from: list[str]
    sha256: str | None
    overwrite: bool
    review_required: bool
```

`file_kind` 候補:

- `assert_header`
- `assert_source`
- `runner_header`
- `runner_source`
- `stub_header`
- `stub_source`
- `test_source`
- `target_invocation_header`
- `target_invocation_source`
- `manifest`
- `report`

### 6.5 StubSkeleton

```python
@dataclass
class StubSkeleton:
    stub_name: str
    original_function_name: str
    return_type_raw: str | None
    parameters: list[StubParameter]
    source_file: Path
    header_file: Path | None
    capabilities: list[str]
    related_call_ids: list[str]
    related_test_case_ids: list[str]
    warnings: list[HarnessGenerationWarning]
```

`capabilities` 候補:

- `return_value_control`
- `call_count`
- `argument_capture`
- `side_effect_placeholder`
- `reset`

### 6.6 StubParameter

```python
@dataclass
class StubParameter:
    index: int
    name: str
    type_raw: str
    capture_strategy: str
    review_required: bool
```

`capture_strategy` 候補:

- `copy_value`
- `copy_pointer_value_only`
- `not_captured`
- `complex_manual`

### 6.7 TestSkeleton

```python
@dataclass
class TestSkeleton:
    test_case_id: str
    function_name: str
    source_file: Path
    generated_function_name: str
    related_coverage_ids: list[str]
    related_stub_names: list[str]
    placeholder_count: int
    review_required: bool
```

### 6.8 UnresolvedPlaceholder

```python
@dataclass
class UnresolvedPlaceholder:
    placeholder_id: str
    placeholder_kind: str
    name: str
    related_test_case_id: str | None
    related_stub_name: str | None
    reason: str
    suggested_action: str
```

`placeholder_kind` 候補:

- `expected_return`
- `expected_global`
- `expected_parameter_side_effect`
- `valid_pointer_fixture`
- `file_static_setup`
- `stub_side_effect`
- `complex_argument_capture`
- `unknown_type`

### 6.9 BuildHint

```python
@dataclass
class BuildHint:
    hint_id: str
    hint_kind: str
    message: str
    related_file: Path | None
    severity: str
```

`hint_kind` 候補:

- `include_path_required`
- `target_source_required`
- `stub_source_required`
- `pch_may_be_required`
- `manual_fixture_required`
- `unresolved_symbol_expected`
- `vc6_c90_constraint`

### 6.10 HarnessGenerationWarning

```python
@dataclass
class HarnessGenerationWarning:
    code: str
    message: str
    related_file: Path | None = None
    related_test_case_id: str | None = None
    related_stub_name: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `expected_value_placeholder_generated` | 期待値placeholderを生成した |
| `stub_required_but_behavior_unknown` | スタブ動作仕様が未確定 |
| `complex_parameter_not_captured` | 複雑な引数を記録しない |
| `pointer_fixture_required` | pointer fixtureが必要 |
| `file_static_setup_not_direct` | file staticを直接設定できない可能性 |
| `unsupported_return_type` | 戻り値型の自動stubが難しい |
| `unknown_parameter_type` | 引数型が不明 |
| `existing_file_not_overwritten` | 既存ファイルを上書きしなかった |
| `c90_syntax_guard_applied` | C90互換のため生成を調整した |

---

## 7. 生成設計

### 7.1 基本アルゴリズム

処理フロー:

```text
generate_harness_skeleton(request)
  1. test_case_draft を読み込む
  2. call_report.stub_candidates を読み込む
  3. function_signature からtarget invocation情報を作る
  4. 出力ディレクトリを作成する
  5. assert header/source を生成する
  6. runner header/source を生成する
  7. stub candidateごとに stub header/source を生成する
  8. test_caseごとに test function雛形を生成する
  9. target invocation wrapper雛形を生成する
 10. unresolved placeholder / build hint を集約する
 11. harness_skeleton_report.json / md を生成する
```

### 7.2 stub source生成

外部関数候補 `ReadSensor` の例:

```c
/* generated stub skeleton: review required */

#include "stub_ReadSensor.h"

static int stub_ReadSensor_return_value;
static int stub_ReadSensor_call_count;
static int stub_ReadSensor_arg0_last;

void Stub_ReadSensor_Reset(void)
{
    stub_ReadSensor_return_value = 0;
    stub_ReadSensor_call_count = 0;
    stub_ReadSensor_arg0_last = 0;
}

void Stub_ReadSensor_SetReturn(int value)
{
    stub_ReadSensor_return_value = value;
}

int Stub_ReadSensor_GetCallCount(void)
{
    return stub_ReadSensor_call_count;
}

int Stub_ReadSensor_GetArg0Last(void)
{
    return stub_ReadSensor_arg0_last;
}

int ReadSensor(int mode)
{
    stub_ReadSensor_call_count++;
    stub_ReadSensor_arg0_last = mode;
    return stub_ReadSensor_return_value;
}
```

方針:

- 戻り値型が `int` / scalarらしい場合はreturn value controlを生成する
- `void` 戻り値はreturn value controlを生成しない
- pointer戻り値は `void *` ではなくraw typeに基づくplaceholderを検討する。ただし不明ならwarningを出す
- 複雑なstruct戻り値はunsupported warningを出し、manual placeholderにする
- 引数記録はscalar優先
- pointer引数はポインタ値のみ記録し、指す先のdeep copyはしない
- function pointer引数は記録しないか `complex_manual` とする

### 7.3 stub header生成

```c
#ifndef UTR_STUB_READSENSOR_H
#define UTR_STUB_READSENSOR_H

void Stub_ReadSensor_Reset(void);
void Stub_ReadSensor_SetReturn(int value);
int Stub_ReadSensor_GetCallCount(void);
int Stub_ReadSensor_GetArg0Last(void);

#endif
```

方針:

- include guardは大文字snake caseで生成する
- C++互換の `extern "C"` は初期では生成しない。必要なら後続で検討する
- VC6/C90対象なので過剰な属性やinlineは使わない

### 7.4 assert header/source生成

初期assert候補:

```c
#define UTR_ASSERT_TRUE(expr) Utr_AssertTrue((expr), __FILE__, __LINE__, #expr)
#define UTR_ASSERT_FALSE(expr) Utr_AssertFalse((expr), __FILE__, __LINE__, #expr)
#define UTR_ASSERT_EQ_INT(expected, actual) Utr_AssertEqInt((expected), (actual), __FILE__, __LINE__, #actual)
#define UTR_ASSERT_PTR_NULL(actual) Utr_AssertPtrNull((actual), __FILE__, __LINE__, #actual)
```

方針:

- `#expr` stringificationはC90でも利用可能なプリプロセッサ機能として扱う
- assert失敗は件数を増やし、runnerが最後に集計する
- 例外やlongjmpは使わない
- 最小実装ではstdout出力と失敗件数カウントだけにする

### 7.5 test case source生成

`test_case_draft` から生成する例:

```c
/* generated test skeleton: review required */

#include "utr_assert.h"
#include "utr_runner.h"
#include "target_invocation.h"
#include "stub_CheckLimit.h"

static void Test_TC_Control_Update_001(void)
{
    int mode;
    int sensor;
    int actual_return;

    Stub_CheckLimit_Reset();

    mode = MODE_AUTO;
    sensor = SENSOR_MIN;
    Stub_CheckLimit_SetReturn(1);

    actual_return = Target_Invoke_Control_Update(mode, sensor);

    UTR_ASSERT_EQ_INT(TBD_EXPECTED_RETURN_INT, actual_return);
    UTR_ASSERT_TRUE(Stub_CheckLimit_GetCallCount() >= 0);
}
```

方針:

- 期待値未確定は `TBD_EXPECTED_RETURN_INT` を使う
- `TBD` placeholderには必ずwarningを出す
- pointer fixtureが必要な引数は `TBD_VALID_PTR_VALUE` などを使い、manual setup commentを生成する
- file static setupが必要な場合はコード化せずcommentとwarningを生成する
- state setup可能そうなglobal/externは代入placeholderを生成する

### 7.6 target invocation生成

対象関数呼び出しを1箇所に集約する。

例:

```c
#ifndef TARGET_INVOCATION_H
#define TARGET_INVOCATION_H

int Target_Invoke_Control_Update(int mode, int sensor);

#endif
```

```c
#include "target_invocation.h"
#include "control.h"

int Target_Invoke_Control_Update(int mode, int sensor)
{
    return Control_Update(mode, sensor);
}
```

方針:

- 対象関数がstaticの場合、直接リンクできない可能性があるためwarningを出す
- static関数をテストする場合のexpose方針はStep 14以降で検討する
- ヘッダincludeが不明な場合はplaceholder includeを生成する

### 7.7 runner生成

最小runner例:

```c
#include "utr_runner.h"

int main(void)
{
    Utr_RunAllTests();
    return Utr_GetFailureCount() == 0 ? 0 : 1;
}
```

方針:

- test registrationは手動または自動生成配列にする
- 関数ポインタ配列はC90でも利用可能
- 大規模になる場合はtest registryを分割する

### 7.8 manifest生成

Step 14に渡すため、生成物manifestを出す。

```json
{
  "schema_version": "0.1",
  "generated_files": [
    "generated/include/utr_assert.h",
    "generated/harness/utr_assert.c",
    "generated/stubs/stub_ReadSensor.c",
    "generated/tests/test_Control_Update.c"
  ],
  "target_function": "Control_Update",
  "requires_target_source": true,
  "requires_stubs": ["ReadSensor", "WritePort"],
  "unresolved_placeholders": []
}
```

---

## 8. CLI 接続設計

### 8.1 analyze-function の Step 13 接続

Step 13 では、`analyze-function` をスタブ・ハーネス雛形生成まで進める。

入力例:

```bat
unit-test-runner analyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Control - Win32 Debug" ^
  --out D:\work\unit_test_workspace\Control_Update
```

処理:

1. Step 04 の source membership / build_context を取得する
2. Step 05 の source_digest / masked_source を生成または読み込む
3. Step 06 の function_location を生成または読み込む
4. Step 07 の function_signature を生成または読み込む
5. Step 08 の global_access を生成または読み込む
6. Step 09 の call_report を生成または読み込む
7. Step 10 の coverage_design を生成または読み込む
8. Step 11 の boundary_equivalence_candidates を生成または読み込む
9. Step 12 の test_case_draft を生成または読み込む
10. Step 13 の Stub / Harness Skeleton Generator を実行する
11. `generated` 配下にCコード雛形を生成する
12. `harness_skeleton_report.json` を生成する
13. `harness_skeleton_report.md` を生成する
14. Step 14 の Build Workspace / Build Probe Generator が必要であることを message に含める
15. 抽出に成功した場合、status `partial` または `harness_skeleton_generated` を返す

### 8.2 generate-harness-skeleton コマンド案

開発・debug 用に以下の独立コマンドを検討する。

```bat
unit-test-runner generate-harness-skeleton ^
  --function-signature reports\function_signature.json ^
  --global-access reports\global_access.json ^
  --call-report reports\call_report.json ^
  --test-case-draft reports\test_case_draft.json ^
  --out D:\work\unit_test_workspace\Control_Update
```

オプション案:

```text
--overwrite
--no-argument-capture
--no-call-count-assertions
--fail-on-unresolved-expected
--emit-report json|md|all
```

---

## 9. Report 設計

### 9.1 harness_skeleton_report.json

例:

```json
{
  "schema_version": "0.1",
  "function": {
    "name": "Control_Update",
    "status": "generated"
  },
  "output_root": "D:/work/unit_test_workspace/Control_Update",
  "generated_files": [
    {
      "path": "generated/include/utr_assert.h",
      "file_kind": "assert_header",
      "review_required": false
    },
    {
      "path": "generated/stubs/stub_ReadSensor.c",
      "file_kind": "stub_source",
      "generated_from": ["STUB_ReadSensor", "CALL_001"],
      "review_required": true
    },
    {
      "path": "generated/tests/test_Control_Update.c",
      "file_kind": "test_source",
      "generated_from": ["TC_Control_Update_001"],
      "review_required": true
    }
  ],
  "stub_skeletons": [
    {
      "stub_name": "Stub_ReadSensor",
      "original_function_name": "ReadSensor",
      "capabilities": ["return_value_control", "call_count", "argument_capture", "reset"],
      "related_call_ids": ["CALL_001"],
      "related_test_case_ids": ["TC_Control_Update_001"]
    }
  ],
  "unresolved_placeholders": [
    {
      "placeholder_kind": "expected_return",
      "name": "TBD_EXPECTED_RETURN_INT",
      "related_test_case_id": "TC_Control_Update_001",
      "reason": "Expected return value is not determined in Step 12."
    }
  ],
  "build_hints": [
    {
      "hint_kind": "target_source_required",
      "message": "Target source file must be included in the build workspace.",
      "severity": "info"
    }
  ],
  "warnings": []
}
```

### 9.2 harness_skeleton_report.md

内容例:

```markdown
# Harness Skeleton Report

## Target

- Function: Control_Update
- Status: generated
- Output Root: D:/work/unit_test_workspace/Control_Update

## Generated Files

| File | Kind | Review Required |
|---|---|---|
| generated/include/utr_assert.h | assert_header | no |
| generated/stubs/stub_ReadSensor.c | stub_source | yes |
| generated/tests/test_Control_Update.c | test_source | yes |

## Stub Skeletons

| Stub | Original Function | Capabilities | Related Calls |
|---|---|---|---|
| Stub_ReadSensor | ReadSensor | return_value_control, call_count, argument_capture, reset | CALL_001 |

## Unresolved Placeholders

| Kind | Name | Related Test Case | Reason |
|---|---|---|---|
| expected_return | TBD_EXPECTED_RETURN_INT | TC_Control_Update_001 | Expected return value is not determined in Step 12. |

## Build Hints

| Kind | Message | Severity |
|---|---|---|
| target_source_required | Target source file must be included in the build workspace. | info |

## Warnings

なし
```

---

## 10. テスト計画

### 10.1 fixture 構成

```text
tests/
  fixtures/
    harness_skeleton/
      simple_function/
        function_signature.json
        call_report.json
        test_case_draft.json
      return_value_stub/
      void_stub/
      pointer_argument_stub/
      global_state_case/
      file_static_warning/
      unresolved_expected/
      static_target_function/
      complex_parameter/
```

### 10.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| HSK-001 | assert skeleton | minimal | utr_assert.h/c生成 |
| HSK-002 | runner skeleton | minimal | utr_runner.c生成 |
| HSK-003 | int return stub | external int func | SetReturn/GetCallCount生成 |
| HSK-004 | void stub | external void func | return controlなし |
| HSK-005 | argument capture | scalar args | arg last getter生成 |
| HSK-006 | pointer argument | pointer arg | pointer value capture + warning |
| HSK-007 | complex arg | function pointer / struct | complex_manual warning |
| HSK-008 | test case skeleton | test_case_draft | test function生成 |
| HSK-009 | target invocation | function_signature | Target_Invoke生成 |
| HSK-010 | expected placeholder | TBD expected | placeholder define + warning |
| HSK-011 | global setup | state setup | setup comment生成 |
| HSK-012 | file static setup | file static | wrapper_required warning |
| HSK-013 | static target function | static target | direct call warning |
| HSK-014 | include guard | stub header | guard形式確認 |
| HSK-015 | C90 syntax guard | generated C | 禁止構文なし |
| HSK-016 | no overwrite | existing file | overwriteしないwarning |
| HSK-017 | report json | harness_skeleton_report.json | JSON parse可能 |
| HSK-018 | report md | harness_skeleton_report.md | expected sectionあり |
| HSK-019 | generate-harness-skeleton cli | explicit inputs | generated filesあり |
| HSK-020 | analyze-function integration | Step04-13 | harness skeleton生成 |

### 10.3 テスト方針

- generator単体テストではfixture JSONから生成する
- 生成Cコードは文字列snapshotではなく、重要な構文と禁止構文を検証する
- JSONは `json.loads()` で検証する
- Markdownは主要sectionの存在を検証する
- C90 syntax guardでは `//`、`for (int`、`stdint.h`、`stdbool.h`、`inline` などが出ないことを確認する
- 実際のVC6ビルドはStep 14で扱うため、Step 13では実行しない

---

## 11. 実装タスク分解

### Task 13-01: Harness model 定義

成果物:

- `src/unit_test_runner/harness/harness_models.py`
- `HarnessGenerationRequest`
- `HarnessGenerationPolicy`
- `HarnessSkeletonReport`
- `GeneratedFile`
- `StubSkeleton`
- `StubParameter`
- `TestSkeleton`
- `UnresolvedPlaceholder`
- `BuildHint`
- `HarnessGenerationWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 13-02: C90 code writer utilities

成果物:

- `src/unit_test_runner/harness/c90_writer.py`
- identifier sanitize
- include guard生成
- indentation helper
- comment helper
- C90禁止構文guard

完了条件:

- HSK-014 / HSK-015 が通る

### Task 13-03: Assert skeleton generator

成果物:

- `src/unit_test_runner/harness/assert_generator.py`
- `utr_assert.h`
- `utr_assert.c`
- assert macro / function雛形

完了条件:

- HSK-001 が通る

### Task 13-04: Runner skeleton generator

成果物:

- `src/unit_test_runner/harness/runner_generator.py`
- `utr_runner.h`
- `utr_runner.c`
- test registration / execution loop雛形

完了条件:

- HSK-002 が通る

### Task 13-05: Stub skeleton generator

成果物:

- `src/unit_test_runner/harness/stub_generator.py`
- stub header/source生成
- return value control
- call count
- argument capture
- reset

完了条件:

- HSK-003 から HSK-007 が通る

### Task 13-06: Target invocation generator

成果物:

- `src/unit_test_runner/harness/target_invocation_generator.py`
- target invocation header/source生成
- void / non-void対応
- static target warning

完了条件:

- HSK-009 / HSK-013 が通る

### Task 13-07: Test case skeleton generator

成果物:

- `src/unit_test_runner/harness/test_case_generator.py`
- test function生成
- input setup placeholder
- state setup placeholder
- stub setup placeholder
- expected observation placeholder

完了条件:

- HSK-008 / HSK-010 / HSK-011 / HSK-012 が通る

### Task 13-08: Harness skeleton analyzer

成果物:

- `src/unit_test_runner/harness/harness_skeleton_generator.py`
- 各generator統合
- output layout生成
- unresolved placeholder集約
- build hint生成

完了条件:

- representative fixtureでgenerated filesが生成される

### Task 13-09: Harness report writer

成果物:

- `src/unit_test_runner/harness/harness_report_writer.py`
- `reports/harness_skeleton_markdown.py`
- `harness_skeleton_report.json`
- `harness_skeleton_report.md`

完了条件:

- HSK-017 / HSK-018 が通る

### Task 13-10: generate-harness-skeleton CLI 実装

成果物:

- `generate-harness-skeleton` コマンド検討・実装
- explicit input対応
- `--overwrite` 対応
- `--out` 出力対応

完了条件:

- HSK-019 が通る

### Task 13-11: analyze-function 接続

成果物:

- Step 04 source membership取得
- Step 05 source_digest生成
- Step 06 function_location生成
- Step 07 function_signature生成
- Step 08 global_access生成
- Step 09 call_report生成
- Step 10 coverage_design生成
- Step 11 boundary_equivalence_candidates生成
- Step 12 test_case_draft生成
- Step 13 harness_skeleton生成
- CLI `analyze-function` の出力更新

完了条件:

- HSK-020 が通る

### Task 13-12: fixture / test 整備

成果物:

- `tests/fixtures/harness_skeleton/...`
- `tests/unit/test_c90_writer.py`
- `tests/unit/test_assert_generator.py`
- `tests/unit/test_runner_generator.py`
- `tests/unit/test_stub_generator.py`
- `tests/unit/test_target_invocation_generator.py`
- `tests/unit/test_test_case_generator.py`
- `tests/unit/test_harness_report_writer.py`
- `tests/unit/test_generate_harness_skeleton_cli.py`
- `tests/unit/test_analyze_function_partial_harness.py`

完了条件:

- HSK-001 から HSK-020 が通る

---

## 12. 受け入れ基準

Step 13 は、以下をすべて満たしたら完了とする。

1. `test_case_draft` からC90互換のtest case skeletonを生成できる
2. `call_report.stub_candidates` からstub header/sourceを生成できる
3. int等のscalar戻り値にreturn value control APIを生成できる
4. void戻り値stubではreturn value controlを生成しない
5. call count記録APIを生成できる
6. scalar引数のargument capture APIを生成できる
7. pointer/complex引数は保守的に扱いwarningを出せる
8. test caseごとにstub reset / setup / target call / expected observation placeholderを生成できる
9. `TBD_EXPECTED_*` placeholderを生成し、warningとしてreportできる
10. file static setup困難をwarningとしてreportできる
11. target invocation wrapperを生成できる
12. static target functionの場合にdirect call困難のwarningを出せる
13. assert header/sourceを生成できる
14. runner header/sourceを生成できる
15. 生成CコードにC99以降の禁止構文を混入させない
16. 生成物を本番リポジトリではなく外部workspace配下に出力する設計になっている
17. 既存ファイルを既定では上書きしない
18. `harness_skeleton_report.json` を生成できる
19. `harness_skeleton_report.md` を生成できる
20. `generate-harness-skeleton` が明示入力から雛形を生成できる
21. `analyze-function` が Step 13 時点では harness skeleton生成まで進み、Step 14 が必要である旨を返せる
22. Step 14 の Build Workspace / Build Probe Generator に渡せるgenerated file list / build hintがある
23. 実ビルドやリンクエラー解析へ踏み込みすぎていない
24. 期待結果確定へ踏み込みすぎていない

---

## 13. 成果物

Step 13 の成果物は以下とする。

```text
src/
  unit_test_runner/
    harness/
      __init__.py
      harness_models.py
      c90_writer.py
      assert_generator.py
      runner_generator.py
      stub_generator.py
      target_invocation_generator.py
      test_case_generator.py
      harness_skeleton_generator.py
      harness_report_writer.py
    reports/
      harness_skeleton_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    harness_skeleton/
      simple_function/
      return_value_stub/
      void_stub/
      pointer_argument_stub/
      global_state_case/
      file_static_warning/
      unresolved_expected/
      static_target_function/
      complex_parameter/
  unit/
    test_c90_writer.py
    test_assert_generator.py
    test_runner_generator.py
    test_stub_generator.py
    test_target_invocation_generator.py
    test_test_case_generator.py
    test_harness_report_writer.py
    test_generate_harness_skeleton_cli.py
    test_analyze_function_partial_harness.py
```

生成先workspace例:

```text
workspace/
  Control_Update/
    generated/
      include/
      harness/
      stubs/
      tests/
    reports/
      harness_skeleton_report.json
      harness_skeleton_report.md
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/test_design/test_case_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/call_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/signature_models.py` 必要な場合のみ

---

## 14. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| VC6非互換コード生成 | 無意識にC99構文を出す | C90 writer utilityと禁止構文テストを用意する |
| 期待値placeholderの誤解 | 生成コードが完成済みテストに見える | `TBD` と `review required` をコード・reportに明記する |
| 複雑な型のstub生成 | struct戻り値、関数ポインタ引数などが難しい | raw保持 + warning + manual placeholderにする |
| pointer引数capture | deep copyすると危険・複雑 | 初期はpointer値のみ記録し、指す先はmanualにする |
| static target function | 外部から直接呼べない可能性 | warningを出し、Step14以降でexpose/wrapper方針を検討する |
| 生成物上書き | ユーザー編集済み雛形を壊す | 既定では上書きしない。`--overwrite` のみ許可する |
| 本番リポジトリ汚染 | 生成Cコードを本番側へ置いてしまう | output_rootを外部workspaceに限定し、reportに明記する |
| Step14責務の侵食 | build実行やリンク補完まで進めたくなる | Step13は雛形生成まで。ビルド確認はStep14へ委譲する |

---

## 15. Step 14 への接続

Step 13 完了後、Step 14 では Build Workspace / Build Probe Generator を実装する。
Step 14 は、Step 04 の build context、Step 13 の generated file list、対象 `.c` / `.h` 抽出情報を使い、VC6 / nmake / cl.exe でビルド試行できるworkspaceとMakefile相当を生成する。

想定接続:

```python
harness_report = generate_harness_skeleton(
    function_signature=function_signature,
    call_report=call_report,
    test_case_draft=test_case_draft,
)
build_workspace = generate_build_workspace(
    build_context=build_context,
    harness_report=harness_report,
    target_source=source_path,
)
```

Step 14 で使う情報:

- generated files
- target source / header
- include dirs
- defines
- PCH情報
- stub source list
- test source list
- unresolved placeholders
- build hints

Step 13 の責務は、Build Workspace / Build Probe Generator がビルド対象として扱える生成Cコード群と、その制約・未解決点を明確に渡すことである。

---

## 16. まとめ

Step 13 は、Step 12 のテストケース草案を、VC6 / C90 向けのスタブ・ハーネス・テストケース雛形へ変換するステップである。

このステップにより、対象関数について、どのスタブが必要で、どのテストケース関数が必要で、どのassertやplaceholderが未解決かを、Cコード雛形とreportとして確認できる。

ただし、Step 13 はビルド実行や期待結果確定を行う段階ではない。
雛形生成に責務を絞り、Step 14 の Build Workspace / Build Probe Generator へ安全な入力を渡すことを完了条件とする。

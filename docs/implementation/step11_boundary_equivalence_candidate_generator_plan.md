# Step 11: Boundary / Equivalence Candidate Generator 実装計画

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

---

## 1. 位置づけ

本書は、`unitTestRunner` の第11ステップとして **Boundary / Equivalence Candidate Generator** を実装するための計画である。

Step 10 では、対象関数内の分岐、条件式、ループ、switch/case、三項演算子、return経路を抽出し、単体テスト設計に使う `coverage_design` を生成する計画を定義した。
Step 11 では、その `coverage_design`、Step 07 の `function_signature`、Step 08 の `global_access`、Step 09 の `call_report` を使い、条件式や引数型から **境界値候補、同値クラス候補、NULL / 非NULL候補、enum / macro値候補、範囲内 / 範囲外候補** を生成する。

Step 11 は、テストケースの本生成ではない。
この段階では、具体的なテスト手順や期待結果を確定せず、テスト設計者がレビューできる **入力値候補・状態候補・スタブ戻り値候補** を作る。

Step 11 の主な責務は以下である。

- 比較条件から境界値候補を生成する
- `x < MIN` / `x <= MAX` / `x >= 0` などから前後値候補を生成する
- `p == NULL` / `p != NULL` からNULL / 非NULL候補を生成する
- `mode == MODE_AUTO` などからenum / macro値候補を生成する
- `switch case` からcase値 / default値候補を生成する
- ループ条件から0回 / 1回 / 複数回に必要そうな値候補を生成する
- 引数型から基本同値クラス候補を生成する
- pointer / array / struct pointer 引数からNULL / 有効ポインタ / 境界サイズ候補を生成する
- グローバル変数やfile static変数の初期状態候補を生成する
- 条件式内の外部関数呼び出しからスタブ戻り値候補を生成する
- `boundary_equivalence_candidates.json` / Markdown を生成する
- Step 12 の Test Case Draft Generator に渡せる入力候補を整理する

---

## 2. 目的

Step 11 の目的は、関数単位テスト設計に必要な **入力値・状態値・スタブ戻り値の候補** を、ソース解析結果からレビュー可能な形で生成することである。

具体的には、以下を実現する。

- `x < 10` から `9`, `10`, `11` のような境界周辺候補を生成できる
- `x <= MAX` から `MAX - 1`, `MAX`, `MAX + 1` のような候補を生成できる
- `x >= MIN && x <= MAX` から範囲内、下限未満、上限超過の同値クラス候補を生成できる
- `p == NULL` / `p != NULL` からNULL / 非NULL候補を生成できる
- `mode == MODE_AUTO` / `mode != MODE_MANUAL` から有効値 / 別値 / 不正値候補を生成できる
- `switch (state)` のcase labelから各case値とdefault到達候補を生成できる
- `for (i = 0; i < count; i++)` から `count=0`, `count=1`, `count=2以上` の候補を生成できる
- `char *buffer`, `int values[]`, `struct Foo *foo` からNULL、有効オブジェクト、空配列、最大件数候補を生成できる
- グローバル変数候補について、条件式に出る値の初期状態候補を生成できる
- 条件式内の関数呼び出し、例: `CheckLimit(x)` から戻り値true/falseのスタブ候補を生成できる
- 候補の根拠、関連coverage item、関連条件式、confidence、review_requiredを保持できる
- `boundary_equivalence_candidates.json` / `boundary_equivalence_candidates.md` を出力できる
- `analyze-function` を Step 11 時点で「coverage design + boundary/equivalence候補生成」まで進められる

---

## 3. スコープ

### 3.1 実装対象

Step 11 で実装するもの:

1. Comparison candidate generator
   - `<`
   - `<=`
   - `>`
   - `>=`
   - `==`
   - `!=`
   - 定数値
   - macro値
   - enum候補

2. Range candidate generator
   - `x >= MIN && x <= MAX`
   - `MIN <= x && x < MAX`
   - 下限のみ
   - 上限のみ
   - 範囲内 / 範囲外 / 境界上

3. Null candidate generator
   - `p == NULL`
   - `p != NULL`
   - `p == 0`
   - `p != 0`
   - pointer引数のNULL / 非NULL候補

4. Switch candidate generator
   - case値候補
   - default到達候補
   - enum / macro候補
   - fall-through review候補

5. Loop candidate generator
   - 0回
   - 1回
   - 複数回
   - break / continue候補
   - count / length / size 変数に対する値候補

6. Type-based equivalence generator
   - signed / unsigned int
   - char / unsigned char
   - long / unsigned long
   - enum-like / macro-like
   - pointer
   - array
   - struct pointer
   - typedef-like unknown

7. State candidate generator
   - global変数候補
   - file static変数候補
   - extern変数候補
   - 条件式に出る状態値
   - 初期値候補

8. Stub return candidate generator
   - 条件式内call result true / false
   - 比較に使われるcall resultの境界候補
   - external function の戻り値候補
   - error-like / success-like 候補

9. Reports
   - `boundary_equivalence_candidates.json`
   - `boundary_equivalence_candidates.md`

10. CLI 接続
   - `analyze-function` を boundary/equivalence candidate生成まで進める
   - status `partial` または `value_candidates_generated` を返す
   - Step 12 の Test Case Draft Generator が必要である旨を message に含める

11. Tests
   - simple comparison
   - inclusive / exclusive boundary
   - range check
   - NULL check
   - enum / macro comparison
   - switch case
   - loop count
   - pointer parameter
   - array parameter
   - global state
   - call result condition
   - unknown macro

### 3.2 対象外

Step 11 では以下を対象外とする。

- テストケース本体の生成
- 期待結果の確定
- 具体的なCテストコード生成
- スタブCコード生成
- macro値の完全解決
- enum定義の完全解決
- typedefの完全解決
- 複雑条件の充足可能性判定
- SAT/SMTによる入力値探索
- inter-proceduralな値域解析
- 実行パス制約の完全解決
- ランダムテスト / fuzzing 入力生成
- 実測カバレッジとの対応付け

Step 11 では、ソースから読み取れる条件・型・状態に基づいて、レビュー可能な候補を保守的に生成することに限定する。

---

## 4. 入力と出力

### 4.1 入力

主入力:

- Step 04 の `build_context`
- Step 05 の `source_digest`
- Step 06 の `function_location`
- Step 07 の `function_signature`
- Step 08 の `global_access`
- Step 09 の `call_report`
- Step 10 の `coverage_design`

入力イメージ:

```json
{
  "source": "D:/work/product/src/control.c",
  "function": "Control_Update",
  "function_signature": "reports/function_signature.json",
  "global_access": "reports/global_access.json",
  "call_report": "reports/call_report.json",
  "coverage_design": "reports/coverage_design.json"
}
```

### 4.2 出力

Step 11 の主要出力は `boundary_equivalence_candidates` である。

```text
workspace/
  Control_Update/
    reports/
      source_digest.json
      function_location.json
      function_signature.json
      global_access.json
      call_report.json
      coverage_design.json
      boundary_equivalence_candidates.json
      boundary_equivalence_candidates.md
    intermediate/
      masked_source.c
      function_slice.c
```

`boundary_equivalence_candidates.json` は Step 12 以降の入力になる。

---

## 5. データモデル設計

### 5.1 BoundaryCandidateRequest

```python
@dataclass
class BoundaryCandidateRequest:
    source_path: Path
    function_signature: FunctionSignature
    global_access: GlobalAccessReport
    call_report: CallReport
    coverage_design: CoverageDesignReport
```

役割:

- Boundary / Equivalence Candidate Generator の入力条件をまとめる
- CLI / internal usecase の境界を明確にする

### 5.2 BoundaryEquivalenceReport

```python
@dataclass
class BoundaryEquivalenceReport:
    source_path: Path
    function_name: str
    status: str
    input_candidates: list[InputValueCandidate]
    state_candidates: list[StateValueCandidate]
    stub_return_candidates: list[StubReturnCandidate]
    equivalence_classes: list[EquivalenceClass]
    boundary_groups: list[BoundaryGroup]
    coverage_links: list[CandidateCoverageLink]
    warnings: list[BoundaryCandidateWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `generated` | 候補生成が完了した |
| `partial` | 一部不明だが主要候補は生成した |
| `ambiguous` | 条件式または値候補が曖昧 |
| `insufficient_information` | 候補生成に必要な情報が不足している |

### 5.3 InputValueCandidate

```python
@dataclass
class InputValueCandidate:
    candidate_id: str
    target_name: str
    target_kind: str
    value_expression: str
    value_kind: str
    source: str
    related_condition_id: str | None
    related_coverage_ids: list[str]
    purpose: str
    confidence: str
    review_required: bool
    evidence: str
```

`target_kind` 候補:

| target_kind | 意味 |
|---|---|
| `parameter` | 関数引数 |
| `global` | グローバル変数候補 |
| `file_static` | file static変数候補 |
| `extern` | extern変数候補 |
| `stub_return` | スタブ戻り値 |
| `unknown` | 判定不能 |

`value_kind` 候補:

| value_kind | 意味 |
|---|---|
| `boundary_below` | 境界直下 |
| `boundary_at` | 境界上 |
| `boundary_above` | 境界直上 |
| `valid_equivalence` | 有効同値クラス |
| `invalid_equivalence` | 無効同値クラス |
| `null` | NULL |
| `non_null` | 非NULL |
| `enum_value` | enum / macro値 |
| `default_case_value` | switch default到達候補 |
| `zero` | 0 |
| `one` | 1 |
| `many` | 複数 |
| `true` | true相当 |
| `false` | false相当 |
| `unknown` | 不明 |

### 5.4 StateValueCandidate

```python
@dataclass
class StateValueCandidate:
    candidate_id: str
    variable_name: str
    scope: str
    value_expression: str
    value_kind: str
    related_condition_id: str | None
    related_coverage_ids: list[str]
    setup_hint: str
    confidence: str
    review_required: bool
    evidence: str
```

役割:

- global / file static / extern変数の初期状態候補を保持する
- テスト前提条件やsetup処理の候補になる

### 5.5 StubReturnCandidate

```python
@dataclass
class StubReturnCandidate:
    candidate_id: str
    call_name: str
    value_expression: str
    value_kind: str
    related_call_id: str | None
    related_condition_id: str | None
    related_coverage_ids: list[str]
    purpose: str
    confidence: str
    review_required: bool
    evidence: str
```

役割:

- 条件式内の外部関数やスタブ候補の戻り値候補を保持する
- Step 12 以降でテストケース草案やスタブ設定案に使う

### 5.6 EquivalenceClass

```python
@dataclass
class EquivalenceClass:
    class_id: str
    target_name: str
    target_kind: str
    class_name: str
    representative_values: list[str]
    description: str
    related_conditions: list[str]
    related_coverage_ids: list[str]
    confidence: str
    review_required: bool
```

例:

- `valid_range`
- `below_minimum`
- `above_maximum`
- `null_pointer`
- `non_null_pointer`
- `valid_enum_value`
- `invalid_enum_value`

### 5.7 BoundaryGroup

```python
@dataclass
class BoundaryGroup:
    group_id: str
    target_name: str
    boundary_expression: str
    operator: str
    candidates: list[str]
    related_condition_id: str
    confidence: str
    review_required: bool
```

役割:

- 1つの境界、例: `sensor >= SENSOR_MIN` に対する `SENSOR_MIN - 1`, `SENSOR_MIN`, `SENSOR_MIN + 1` を束ねる

### 5.8 CandidateCoverageLink

```python
@dataclass
class CandidateCoverageLink:
    coverage_id: str
    candidate_ids: list[str]
    link_reason: str
    confidence: str
```

役割:

- Step 10 の coverage item と Step 11 の値候補を接続する
- Step 12 の test case draft生成で使用する

### 5.9 BoundaryCandidateWarning

```python
@dataclass
class BoundaryCandidateWarning:
    code: str
    message: str
    related_condition_id: str | None = None
    text: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `macro_value_unresolved` | macro値を解決できない |
| `enum_values_unresolved` | enum値を解決できない |
| `type_range_unknown` | 型の範囲が不明 |
| `complex_condition_not_expanded` | 複雑条件を展開しきれない |
| `candidate_may_be_invalid_c_expression` | 候補値がC式としてそのまま使えない可能性 |
| `off_by_one_not_applicable` | 境界前後値が作れない |
| `pointer_candidate_requires_fixture` | 非NULLポインタ候補にはfixtureが必要 |
| `global_state_setup_required` | global状態設定が必要 |
| `stub_return_requires_review` | スタブ戻り値候補にレビューが必要 |
| `coverage_link_ambiguous` | coverage itemとの関連が曖昧 |

---

## 6. 候補生成設計

### 6.1 基本アルゴリズム

処理フロー:

```text
generate_boundary_equivalence_candidates(request)
  1. function_signature から parameter一覧と型情報を取得する
  2. global_access から global / file_static / extern状態候補を取得する
  3. call_report から stub candidate と戻り値利用情報を取得する
  4. coverage_design から condition expressions と coverage items を取得する
  5. 各condition expressionを比較 / NULL / range / macro / call_resultに分類する
  6. 条件式の対象変数またはcall resultを特定する
  7. 比較演算子ごとに境界候補を生成する
  8. 型情報から基本同値クラス候補を生成する
  9. switch caseからcase値 / default候補を生成する
 10. loop coverage itemから0/1/many候補を生成する
 11. stub return candidateを生成する
 12. coverage itemとのlinkを生成する
 13. warnings / confidence / review_requiredを整理する
 14. BoundaryEquivalenceReportを返す
```

### 6.2 比較演算子からの境界候補

代表ルール:

| 条件 | 候補 |
|---|---|
| `x < C` | `C - 1`, `C`, `C + 1` |
| `x <= C` | `C - 1`, `C`, `C + 1` |
| `x > C` | `C - 1`, `C`, `C + 1` |
| `x >= C` | `C - 1`, `C`, `C + 1` |
| `x == C` | `C`, `C - 1`, `C + 1` |
| `x != C` | `C`, `C以外` |

方針:

- `C` が数値リテラルなら具体値を計算してもよい
- `C` がmacroなら `C - 1`, `C`, `C + 1` の式候補として保持する
- `C` がenum-likeなら `C` と `C以外` を候補にする
- `C - 1` が意味を持たない可能性がある場合は `review_required=true`
- unsigned型で `0 - 1` のような候補は warningを付与する

### 6.3 範囲チェック候補

対象例:

```c
if (sensor >= SENSOR_MIN && sensor <= SENSOR_MAX)
```

候補:

- `SENSOR_MIN - 1`
- `SENSOR_MIN`
- `SENSOR_MIN + 1`
- `SENSOR_MAX - 1`
- `SENSOR_MAX`
- `SENSOR_MAX + 1`
- `SENSOR_MIN..SENSOR_MAX` の有効範囲同値クラス
- `SENSOR_MIN未満` の無効同値クラス
- `SENSOR_MAX超過` の無効同値クラス

方針:

- Step 10 の `range_check` 候補を優先する
- 同一変数に対する上下限比較をまとめて `BoundaryGroup` にする
- 上下限の大小関係は評価しない。必要なら warningを出す

### 6.4 NULL / 非NULL候補

対象例:

```c
if (buffer == NULL)
if (ctx != NULL)
```

候補:

- `NULL`
- `valid_pointer`
- `invalid_pointer_like` は初期では生成しない

方針:

- pointer引数は条件式に出なくても `NULL` / `non_null` 候補を生成してよい
- 非NULL候補には `fixture object required` のsetup hintを付ける
- struct pointerなら `valid struct instance` 候補を出す
- array引数は `NULL` 候補と `non_empty_array` 候補を出す

### 6.5 enum / macro値候補

対象例:

```c
if (mode == MODE_AUTO)
switch (state) {
case STATE_INIT:
case STATE_RUN:
default:
}
```

候補:

- `MODE_AUTO`
- `MODE_MANUAL` など同一prefix候補。初期では同一条件式またはswitch内caseから取得する
- `invalid_enum_value`
- `default_case_value`

方針:

- enum定義の完全解析はしない
- 同一switch内case labelを有効値候補にする
- `default` がある場合、case label以外をdefault到達候補にする
- macro値の実数値が不明でもraw symbolとして保持する

### 6.6 loop候補

対象例:

```c
for (i = 0; i < count; i++)
while (retry_count > 0)
```

候補:

- `count = 0`
- `count = 1`
- `count = 2`
- `retry_count = 0`
- `retry_count = 1`
- `retry_count > 1`

方針:

- Step 10 の `loop_zero` / `loop_one` / `loop_many` と関連付ける
- loop condition内の変数を対象にする
- 具体式が難しい場合は `zero_iterations`, `one_iteration`, `multiple_iterations` の抽象候補を出す

### 6.7 型ベース同値クラス候補

Step 07 の TypeInfo から生成する。

| 型・分類 | 候補 |
|---|---|
| signed integer | negative, zero, positive |
| unsigned integer | zero, positive, max_candidate |
| char | zero, normal char, boundary char |
| pointer | NULL, non_null |
| const pointer | NULL, valid_readable_object |
| nonconst pointer | NULL, valid_writable_object |
| array | empty, one_element, many_elements |
| enum-like / typedef-like | valid_symbol, invalid_symbol |

注意:

- C90 / VC6 では `stdint.h` 前提にしない
- 型のbit幅は断定しない
- `int` の最大最小値は `INT_MIN`, `INT_MAX` のようなsymbolic候補に留める

### 6.8 global state候補

Step 08 の global_accessから生成する。

対象:

- 条件式で参照されるglobal
- 書き込みされるglobal
- file static状態変数
- extern状態変数

候補:

- 条件式で比較される値
- 比較値の前後
- 初期値候補 `0`
- 正常状態候補
- 異常状態候補
- review_requiredな状態候補

方針:

- globalの初期化方法はこの段階では確定しない
- setup_hintとして `set global before call` を出す
- file staticは外部から直接設定できない可能性があるため warningを出す

### 6.9 stub return候補

Step 09 の call_reportから生成する。

対象:

```c
if (CheckLimit(sensor))
if (ReadSensor() < SENSOR_MIN)
error = GetErrorCode();
```

候補:

- true相当
- false相当
- 0
- 非0
- comparison境界値
- success-like value
- error-like value

方針:

- 条件式に直接使われるcallは true / false 候補を出す
- 比較されるcall resultは比較演算子に従って境界候補を出す
- 戻り値が代入されるだけの場合は候補を控えめにする
- external_function のstub candidateと関連付ける

---

## 7. CLI 接続設計

### 7.1 analyze-function の Step 11 接続

Step 11 では、`analyze-function` を境界値・同値クラス候補生成まで進める。

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
8. Step 11 の Boundary / Equivalence Candidate Generator を実行する
9. `boundary_equivalence_candidates.json` を生成する
10. `boundary_equivalence_candidates.md` を生成する
11. Step 12 の Test Case Draft Generator が必要であることを message に含める
12. 抽出に成功した場合、status `partial` または `value_candidates_generated` を返す

### 7.2 generate-boundary-candidates コマンド案

開発・debug 用に以下の独立コマンドを検討する。

```bat
unit-test-runner generate-boundary-candidates ^
  --function-signature D:\work\unit_test_workspace\Control_Update\reports\function_signature.json ^
  --global-access D:\work\unit_test_workspace\Control_Update\reports\global_access.json ^
  --call-report D:\work\unit_test_workspace\Control_Update\reports\call_report.json ^
  --coverage-design D:\work\unit_test_workspace\Control_Update\reports\coverage_design.json ^
  --out D:\work\unit_test_workspace\Control_Update\reports\boundary_equivalence_candidates.json
```

扱い:

- 公開コマンドにするかは実装時判断とする
- Step 11 計画では必須ではない
- 必須なのは internal usecase と `analyze-function` 接続である

---

## 8. Report 設計

### 8.1 boundary_equivalence_candidates.json

例:

```json
{
  "schema_version": "0.1",
  "source": {
    "path": "D:/work/product/src/control.c",
    "sha256": "..."
  },
  "function": {
    "name": "Control_Update",
    "status": "generated"
  },
  "input_candidates": [
    {
      "candidate_id": "IN_sensor_001",
      "target_name": "sensor",
      "target_kind": "parameter",
      "value_expression": "SENSOR_MIN - 1",
      "value_kind": "boundary_below",
      "source": "condition",
      "related_condition_id": "COND_001",
      "related_coverage_ids": ["BR_Control_Update_001_FALSE"],
      "purpose": "below lower boundary",
      "confidence": "high",
      "review_required": true,
      "evidence": "sensor >= SENSOR_MIN"
    },
    {
      "candidate_id": "IN_sensor_002",
      "target_name": "sensor",
      "target_kind": "parameter",
      "value_expression": "SENSOR_MIN",
      "value_kind": "boundary_at",
      "source": "condition",
      "related_condition_id": "COND_001",
      "related_coverage_ids": ["BR_Control_Update_001_TRUE"],
      "purpose": "at lower boundary",
      "confidence": "high",
      "review_required": true,
      "evidence": "sensor >= SENSOR_MIN"
    }
  ],
  "equivalence_classes": [
    {
      "class_id": "EQ_sensor_valid_range",
      "target_name": "sensor",
      "target_kind": "parameter",
      "class_name": "valid_range",
      "representative_values": ["SENSOR_MIN", "SENSOR_MAX"],
      "description": "sensor is within valid range",
      "related_conditions": ["COND_001"],
      "related_coverage_ids": ["BR_Control_Update_001_TRUE"],
      "confidence": "medium",
      "review_required": true
    }
  ],
  "stub_return_candidates": [
    {
      "candidate_id": "STUB_CheckLimit_TRUE",
      "call_name": "CheckLimit",
      "value_expression": "true",
      "value_kind": "true",
      "related_call_id": "CALL_001",
      "related_condition_id": "COND_002",
      "related_coverage_ids": ["BR_Control_Update_002_TRUE"],
      "purpose": "make condition true",
      "confidence": "high",
      "review_required": true,
      "evidence": "if (CheckLimit(sensor))"
    }
  ],
  "warnings": []
}
```

### 8.2 boundary_equivalence_candidates.md

内容例:

```markdown
# Boundary / Equivalence Candidate Report

## Target

- Source: D:/work/product/src/control.c
- Function: Control_Update
- Status: generated

## Input Value Candidates

| ID | Target | Value | Kind | Related Coverage | Evidence | Review |
|---|---|---|---|---|---|---|
| IN_sensor_001 | sensor | SENSOR_MIN - 1 | boundary_below | BR_Control_Update_001_FALSE | `sensor >= SENSOR_MIN` | yes |
| IN_sensor_002 | sensor | SENSOR_MIN | boundary_at | BR_Control_Update_001_TRUE | `sensor >= SENSOR_MIN` | yes |

## Equivalence Classes

| ID | Target | Class | Representative Values | Coverage | Review |
|---|---|---|---|---|---|
| EQ_sensor_valid_range | sensor | valid_range | SENSOR_MIN, SENSOR_MAX | BR_Control_Update_001_TRUE | yes |

## State Candidates

| ID | Variable | Scope | Value | Setup Hint | Review |
|---|---|---|---|---|---|

## Stub Return Candidates

| ID | Call | Value | Purpose | Coverage | Review |
|---|---|---|---|---|---|
| STUB_CheckLimit_TRUE | CheckLimit | true | make condition true | BR_Control_Update_002_TRUE | yes |

## Warnings

なし
```

---

## 9. テスト計画

### 9.1 fixture 構成

```text
tests/
  fixtures/
    c_sources/
      boundary_equivalence/
        simple_less_than.c
        inclusive_upper_bound.c
        range_check.c
        null_check.c
        enum_macro_compare.c
        switch_cases.c
        loop_count.c
        pointer_parameter.c
        array_parameter.c
        global_state_condition.c
        call_result_condition.c
        unsigned_zero_boundary.c
        unresolved_macro_value.c
        complex_condition.c
```

### 9.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| BND-001 | less than | `x < 10` | 9,10,11候補 |
| BND-002 | less equal | `x <= MAX` | MAX-1,MAX,MAX+1候補 |
| BND-003 | greater equal | `x >= MIN` | MIN-1,MIN,MIN+1候補 |
| BND-004 | equality | `mode == MODE_AUTO` | MODE_AUTO,別値候補 |
| BND-005 | not equal | `mode != MODE_AUTO` | MODE_AUTO,MODE_AUTO以外候補 |
| BND-006 | range check | `x >= MIN && x <= MAX` | 有効範囲/下限未満/上限超過 |
| BND-007 | null equal | `p == NULL` | NULL/非NULL候補 |
| BND-008 | null not equal | `p != NULL` | NULL/非NULL候補 |
| BND-009 | switch cases | case A/B/default | A/B/default候補 |
| BND-010 | loop zero one many | `i < count` | count=0/1/2候補 |
| BND-011 | signed int type | `int x` | negative/zero/positive候補 |
| BND-012 | unsigned zero | `unsigned count >= 0` | underflow warning |
| BND-013 | pointer parameter | `char *buf` | NULL/non_null候補 |
| BND-014 | array parameter | `int values[]` | empty/one/many候補 |
| BND-015 | global state | `g_state == READY` | g_state初期値候補 |
| BND-016 | file static state | file static条件 | setup warning |
| BND-017 | call result bool | `if (Check())` | true/false stub戻り値候補 |
| BND-018 | call result compare | `Read() < MIN` | MIN-1/MIN/MIN+1 stub戻り値候補 |
| BND-019 | unresolved macro | macro値不明 | symbolic候補 + warning |
| BND-020 | complex condition | 複雑条件 | review_required候補 |
| BND-021 | coverage link | coverage itemあり | candidateCoverageLink生成 |
| BND-022 | json output | boundary_equivalence_candidates.json | JSON parse可能 |
| BND-023 | markdown output | boundary_equivalence_candidates.md | expected sectionあり |
| BND-024 | analyze-function integration | Step04-11 | boundary candidates生成 |

### 9.3 テスト方針

- comparison generator は条件式単体でテストする
- range generator は上下限の組み合わせを重点的にテストする
- pointer / array / type-based候補は Step 07 の FunctionSignature fixture と接続する
- global state候補は Step 08 の GlobalAccessReport fixture と接続する
- stub return候補は Step 09 の CallReport fixture と接続する
- coverage link は Step 10 の CoverageDesignReport fixture と接続する
- JSONは `json.loads()` で検証する
- Markdownは主要sectionの存在を検証する
- macro値不明や複雑条件は warning / review_required を重視する

---

## 10. 実装タスク分解

### Task 11-01: Boundary / equivalence model 定義

成果物:

- `src/unit_test_runner/c_analyzer/boundary_models.py`
- `BoundaryCandidateRequest`
- `BoundaryEquivalenceReport`
- `InputValueCandidate`
- `StateValueCandidate`
- `StubReturnCandidate`
- `EquivalenceClass`
- `BoundaryGroup`
- `CandidateCoverageLink`
- `BoundaryCandidateWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 11-02: Comparison candidate generator

成果物:

- `src/unit_test_runner/c_analyzer/comparison_candidate_generator.py`
- 比較演算子別候補生成
- symbolic boundary生成
- warning生成

完了条件:

- BND-001 から BND-005 が通る

### Task 11-03: Range candidate generator

成果物:

- 上下限比較の統合
- valid / invalid equivalence生成
- BoundaryGroup生成

完了条件:

- BND-006 が通る

### Task 11-04: Null / pointer candidate generator

成果物:

- NULL / non_null候補
- pointer parameter候補
- setup hint生成

完了条件:

- BND-007 / BND-008 / BND-013 が通る

### Task 11-05: Switch / enum / macro candidate generator

成果物:

- case値候補
- default候補
- enum/macro raw symbol保持

完了条件:

- BND-004 / BND-005 / BND-009 / BND-019 が通る

### Task 11-06: Loop candidate generator

成果物:

- zero / one / many候補
- count/size変数候補
- loop coverage link

完了条件:

- BND-010 が通る

### Task 11-07: Type-based equivalence generator

成果物:

- signed / unsigned / pointer / array / typedef-like候補
- symbolic INT_MIN / INT_MAX候補
- unsigned underflow warning

完了条件:

- BND-011 / BND-012 / BND-014 が通る

### Task 11-08: State candidate generator

成果物:

- global / file_static / extern状態候補
- setup_hint生成
- file static setup warning

完了条件:

- BND-015 / BND-016 が通る

### Task 11-09: Stub return candidate generator

成果物:

- call result true/false
- call result comparison boundary
- stub candidateとの関連付け

完了条件:

- BND-017 / BND-018 が通る

### Task 11-10: Coverage link generator

成果物:

- coverage item とcandidateの関連付け
- CandidateCoverageLink生成
- ambiguous warning

完了条件:

- BND-021 が通る

### Task 11-11: Boundary report writer

成果物:

- `src/unit_test_runner/c_analyzer/boundary_candidate_writer.py`
- `boundary_equivalence_candidates.json`
- `reports/boundary_equivalence_markdown.py`

完了条件:

- BND-022 / BND-023 が通る

### Task 11-12: analyze-function 接続

成果物:

- Step 04 source membership取得
- Step 05 source_digest生成
- Step 06 function_location生成
- Step 07 function_signature生成
- Step 08 global_access生成
- Step 09 call_report生成
- Step 10 coverage_design生成
- Step 11 boundary_equivalence_candidates生成
- CLI `analyze-function` の出力更新

完了条件:

- BND-024 が通る

### Task 11-13: fixture / test 整備

成果物:

- `tests/fixtures/c_sources/boundary_equivalence/...`
- `tests/unit/test_comparison_candidate_generator.py`
- `tests/unit/test_range_candidate_generator.py`
- `tests/unit/test_null_pointer_candidate_generator.py`
- `tests/unit/test_type_equivalence_generator.py`
- `tests/unit/test_state_candidate_generator.py`
- `tests/unit/test_stub_return_candidate_generator.py`
- `tests/unit/test_boundary_report_writer.py`
- `tests/unit/test_analyze_function_partial_boundary.py`

完了条件:

- BND-001 から BND-024 が通る

---

## 11. 受け入れ基準

Step 11 は、以下をすべて満たしたら完了とする。

1. `<` / `<=` / `>` / `>=` / `==` / `!=` から境界候補を生成できる
2. 数値リテラル境界では前後値候補を生成できる
3. macro境界ではsymbolic候補を生成できる
4. 範囲チェックから有効範囲 / 下限未満 / 上限超過候補を生成できる
5. NULL / 非NULL候補を生成できる
6. pointer / array引数に対する基本同値クラス候補を生成できる
7. signed / unsigned / typedef-like型に対する保守的な同値クラス候補を生成できる
8. switch case / default 候補を生成できる
9. loop zero / one / many 候補を生成できる
10. global / file static / extern状態値候補を生成できる
11. file static状態候補にsetup上の注意を付与できる
12. 条件式内call resultに対するstub戻り値候補を生成できる
13. comparison対象のcall resultに境界候補を生成できる
14. 候補とcoverage itemを関連付けられる
15. 候補にconfidenceとreview_requiredを付与できる
16. macro値未解決や複雑条件をwarningとして保持できる
17. `boundary_equivalence_candidates.json` を生成できる
18. `boundary_equivalence_candidates.md` を生成できる
19. `analyze-function` が Step 11 時点では boundary/equivalence candidate生成まで進み、Step 12 が必要である旨を返せる
20. Step 12 の Test Case Draft Generator に渡せる candidate / equivalence / coverage link 情報がある
21. テストケース本生成へ踏み込みすぎていない
22. 期待結果確定へ踏み込みすぎていない

---

## 12. 成果物

Step 11 の成果物は以下とする。

```text
src/
  unit_test_runner/
    c_analyzer/
      boundary_models.py
      comparison_candidate_generator.py
      range_candidate_generator.py
      null_pointer_candidate_generator.py
      switch_candidate_generator.py
      loop_candidate_generator.py
      type_equivalence_generator.py
      state_candidate_generator.py
      stub_return_candidate_generator.py
      coverage_candidate_linker.py
      boundary_candidate_analyzer.py
      boundary_candidate_writer.py
    reports/
      boundary_equivalence_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    c_sources/
      boundary_equivalence/
        simple_less_than.c
        inclusive_upper_bound.c
        range_check.c
        null_check.c
        enum_macro_compare.c
        switch_cases.c
        loop_count.c
        pointer_parameter.c
        array_parameter.c
        global_state_condition.c
        call_result_condition.c
        unsigned_zero_boundary.c
        unresolved_macro_value.c
        complex_condition.c
  unit/
    test_comparison_candidate_generator.py
    test_range_candidate_generator.py
    test_null_pointer_candidate_generator.py
    test_type_equivalence_generator.py
    test_state_candidate_generator.py
    test_stub_return_candidate_generator.py
    test_boundary_report_writer.py
    test_analyze_function_partial_boundary.py
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/c_analyzer/coverage_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/signature_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/call_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/global_access_models.py` 必要な場合のみ

---

## 13. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| macro値未解決 | `MAX + 1` の実値が分からない | symbolic候補として保持し、review_requiredにする |
| enum値未解決 | enum定義を辿らないため候補が不足する | switch caseや比較条件に現れたsymbolを有効値候補にする |
| unsigned境界 | `0 - 1` のような候補が不適切 | warningを付け、候補はsymbolicまたはreview_requiredにする |
| pointer候補の実体 | 非NULLポインタにはfixtureが必要 | setup_hintを付け、Test Case Draftで明示する |
| file static状態設定 | 外部から直接設定できない可能性がある | setup warningを付け、後続でwrapper/初期化経路検討に回す |
| 条件充足性 | 複数条件の組み合わせが実現不能な可能性がある | Step11では候補に留め、Step12で組み合わせ時にreview_requiredにする |
| 候補過多 | 境界値・同値クラスが増えすぎる | coverage linkとconfidenceで優先度を付ける |
| テストケース生成への前倒し | 候補からすぐTC化したくなる | Step11は候補生成のみ。TC草案化はStep12へ委譲する |

---

## 14. Step 12 への接続

Step 11 完了後、Step 12 では Test Case Draft Generator を実装する。
Step 12 は、Step 10 の `coverage_design` と Step 11 の `boundary_equivalence_candidates` を使い、レビュー可能なテストケース草案を生成する。

想定接続:

```python
coverage_design = analyze_branches(
    source_digest=source_digest,
    function_location=function_location,
    global_access=global_access,
    call_report=call_report,
)
boundary_candidates = generate_boundary_candidates(
    function_signature=function_signature,
    global_access=global_access,
    coverage_design=coverage_design,
)
test_case_draft = generate_test_case_draft(
    function_signature=function_signature,
    global_access=global_access,
    call_report=call_report,
    coverage_design=coverage_design,
    boundary_candidates=boundary_candidates,
)
```

Step 12 で使う情報:

- parameters
- global / state candidates
- stub return candidates
- coverage items
- boundary groups
- equivalence classes
- candidate coverage links
- warnings / review_required

Step 11 の責務は、Test Case Draft Generator がテストケース草案を構成するための値候補とcoverage itemの対応を作ることである。

---

## 15. まとめ

Step 11 は、Step 10 で整理した設計カバレッジ項目を、具体的な値候補・状態候補・スタブ戻り値候補へ変換するステップである。

このステップにより、対象関数について、どの引数値、グローバル状態、スタブ戻り値を使えば分岐・条件・return経路を確認できそうかを `boundary_equivalence_candidates` として整理できる。

ただし、Step 11 はテストケース本生成や期待結果確定を行う段階ではない。
候補生成に責務を絞り、Step 12 の Test Case Draft Generator へ安全な入力を渡すことを完了条件とする。

# Step 10: Branch / Condition Analyzer 実装計画

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

---

## 1. 位置づけ

本書は、`unitTestRunner` の第10ステップとして **Branch / Condition Analyzer** を実装するための計画である。

Step 09 では、対象関数内の関数呼び出し、呼び出し先分類、引数式、戻り値利用、スタブ候補、副作用候補を `call_report` として抽出する計画を定義した。
Step 10 では、Step 05 の token stream、Step 06 の関数本文範囲、Step 08 の変数アクセス情報、Step 09 の呼び出し情報を使い、対象関数内の **分岐、条件式、ループ、switch/case、三項演算子、return経路** を抽出し、単体テスト設計に使う **設計カバレッジ項目** を生成する。

Step 10 は、実測カバレッジ計測ではない。
この段階では、コードを実行して分岐を通過したかを測定するのではなく、どの分岐・条件・経路をテスト観点として設計すべきかを整理する。

Step 10 の主な責務は以下である。

- `if` / `else if` / `else` を抽出する
- `switch` / `case` / `default` を抽出する
- `for` / `while` / `do while` を抽出する
- 三項演算子 `?:` を抽出する
- 論理演算 `&&` / `||` を含む複合条件を抽出する
- 比較演算、NULLチェック、範囲チェックらしき条件を抽出する
- return文とreturn経路を抽出する
- 条件式に含まれる変数アクセス・関数呼び出しを関連付ける
- 分岐網羅、条件網羅、switch case網羅、ループ0/1/複数回候補を生成する
- `coverage_design.json` / `coverage_design.md` を生成する
- Step 11 の Boundary / Equivalence Candidate Generator に渡せる条件式情報を整理する

---

## 2. 目的

Step 10 の目的は、関数単位テスト設計に必要な **分岐・条件・経路カバレッジの設計情報** を安定して抽出することである。

具体的には、以下を実現する。

- 対象関数内の `if` 条件を一覧化できる
- `else if` / `else` を親 `if` と関連付けられる
- `switch` の `case` / `default` を一覧化できる
- `for` / `while` / `do while` の条件式を抽出できる
- 三項演算子を条件分岐候補として抽出できる
- `&&` / `||` を含む複合条件を条件網羅候補へ分解できる
- `x < MIN`、`x >= MAX`、`p == NULL` のような境界値・NULLチェックの元情報を抽出できる
- 条件式に含まれるグローバル変数、引数、ローカル変数、外部関数呼び出しを関連付けられる
- return文を一覧化し、到達経路候補として扱える
- 分岐網羅項目、条件網羅項目、switch case網羅項目、loop実行回数候補を生成できる
- 実測カバレッジではなく、レビュー可能な設計カバレッジとして出力できる
- `coverage_design.json` / `coverage_design.md` を出力できる
- `analyze-function` を Step 10 時点で「呼び出し解析 + 分岐・条件カバレッジ設計」まで進められる

---

## 3. スコープ

### 3.1 実装対象

Step 10 で実装するもの:

1. Branch scanner
   - `if`
   - `else if`
   - `else`
   - branch nesting level
   - branch range

2. Switch scanner
   - `switch` expression
   - `case` labels
   - `default`
   - case body range
   - fall-through候補

3. Loop scanner
   - `for`
   - `while`
   - `do while`
   - loop condition
   - loop initializer / increment summary
   - 0回 / 1回 / 複数回候補

4. Condition expression analyzer
   - 比較演算子
   - 論理演算子
   - NULLチェック
   - 範囲チェック候補
   - enum / macro比較候補
   - 関数呼び出しを含む条件
   - 副作用を含む条件候補

5. Return path analyzer
   - return文一覧
   - return value expression
   - early return候補
   - error return候補
   - normal return候補

6. Coverage item generator
   - branch coverage item
   - condition coverage item
   - switch coverage item
   - loop coverage item
   - return path coverage item

7. Context linking
   - Step 08 の global/parameter/local access と条件式を関連付ける
   - Step 09 の call sites と条件式を関連付ける
   - conditional active_state を付与する

8. Reports
   - `coverage_design.json`
   - `coverage_design.md`

9. CLI 接続
   - `analyze-function` を coverage design 生成まで進める
   - status `partial` または `coverage_designed` を返す
   - Step 11 の Boundary / Equivalence Candidate Generator が必要である旨を message に含める

10. Tests
   - simple if
   - if / else
   - else if chain
   - nested if
   - switch / case / default
   - for / while / do while
   - ternary
   - logical and/or
   - NULL check
   - range check
   - return paths
   - conditional call
   - inactive conditional region

### 3.2 対象外

Step 10 では以下を対象外とする。

- 実測カバレッジ計測
- テストコードへの計測ポイント埋め込み
- MC/DC の完全生成
- SAT/SMTによる条件充足性判定
- データフロー解析の完全実装
- 境界値・同値クラス候補の本生成
- テストケースの本生成
- スタブCコード生成
- 条件を満たす具体入力値の自動決定
- inter-proceduralな分岐解析
- macro展開後の分岐解析

Step 10 では、関数本文から読み取れる分岐・条件・経路候補を保守的に抽出し、テスト設計のための材料として整理することに限定する。

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
- 元ソーステキスト
- masked text
- token stream

入力イメージ:

```json
{
  "source": "D:/work/product/src/control.c",
  "function": "Control_Update",
  "source_digest": "reports/source_digest.json",
  "function_location": "reports/function_location.json",
  "function_signature": "reports/function_signature.json",
  "global_access": "reports/global_access.json",
  "call_report": "reports/call_report.json"
}
```

### 4.2 出力

Step 10 の主要出力は `coverage_design` である。

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
      coverage_design.md
    intermediate/
      masked_source.c
      function_slice.c
```

`coverage_design.json` は Step 11 以降の入力になる。

---

## 5. データモデル設計

### 5.1 BranchAnalysisRequest

```python
@dataclass
class BranchAnalysisRequest:
    source_path: Path
    source_text: str
    masked_text: str
    tokens: list[LexToken]
    function_location: FunctionLocation
    function_signature: FunctionSignature
    global_access: GlobalAccessReport
    call_report: CallReport
```

役割:

- Branch / Condition Analyzer の入力条件をまとめる
- CLI / internal usecase の境界を明確にする

### 5.2 CoverageDesignReport

```python
@dataclass
class CoverageDesignReport:
    source_path: Path
    function_name: str
    status: str
    branches: list[BranchNode]
    switches: list[SwitchNode]
    loops: list[LoopNode]
    ternaries: list[TernaryNode]
    return_paths: list[ReturnPath]
    condition_expressions: list[ConditionExpression]
    coverage_items: list[CoverageItem]
    warnings: list[BranchAnalyzerWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `analyzed` | 分岐・条件候補抽出が完了した |
| `partial` | 一部不明だが主要候補は抽出した |
| `ambiguous` | 条件式または構造が曖昧 |
| `malformed` | token範囲や括弧対応が壊れて解析不能 |

### 5.3 BranchNode

```python
@dataclass
class BranchNode:
    branch_id: str
    kind: str
    condition: ConditionExpression | None
    branch_range: SourceRange
    body_range: SourceRange | None
    parent_branch_id: str | None
    nesting_level: int
    has_else: bool
    else_branch_id: str | None
    active_state: str
    confidence: str
    evidence: str
```

`kind` 候補:

| kind | 意味 |
|---|---|
| `if` | if分岐 |
| `else_if` | else if分岐 |
| `else` | else分岐 |

### 5.4 ConditionExpression

```python
@dataclass
class ConditionExpression:
    condition_id: str
    raw: str
    expression_range: SourceRange
    condition_kind: str
    operands: list[ConditionOperand]
    operators: list[str]
    related_variables: list[str]
    related_calls: list[str]
    complexity: str
    active_state: str
    confidence: str
    warnings: list[BranchAnalyzerWarning]
```

`condition_kind` 候補:

| condition_kind | 意味 |
|---|---|
| `boolean` | 真偽値条件 |
| `comparison` | 比較条件 |
| `range_check` | 範囲チェック候補 |
| `null_check` | NULLチェック候補 |
| `macro_check` | macro値比較候補 |
| `call_result` | 関数戻り値条件 |
| `compound` | 複合条件 |
| `unknown` | 判定不能 |

`complexity` 候補:

- `simple`
- `compound`
- `nested`
- `complex`
- `unknown`

### 5.5 ConditionOperand

```python
@dataclass
class ConditionOperand:
    raw: str
    operand_kind: str
    resolved_as: str
    name: str | None
    literal_value: str | None
    position: SourcePosition
    confidence: str
```

`operand_kind` 候補:

| operand_kind | 意味 |
|---|---|
| `parameter` | 関数引数 |
| `local` | ローカル変数 |
| `global` | グローバル変数候補 |
| `constant` | 数値・文字定数 |
| `macro` | macro候補 |
| `call` | 関数呼び出し結果 |
| `member_access` | メンバアクセス |
| `unknown` | 判定不能 |

### 5.6 SwitchNode / CaseNode

```python
@dataclass
class SwitchNode:
    switch_id: str
    expression: ConditionExpression
    switch_range: SourceRange
    cases: list[CaseNode]
    has_default: bool
    active_state: str
    confidence: str
```

```python
@dataclass
class CaseNode:
    case_id: str
    label_raw: str
    label_kind: str
    label_value: str | None
    case_range: SourceRange
    body_range: SourceRange | None
    fallthrough_candidate: bool
    confidence: str
```

`label_kind` 候補:

- `constant`
- `macro`
- `enum_candidate`
- `default`
- `unknown`

### 5.7 LoopNode

```python
@dataclass
class LoopNode:
    loop_id: str
    kind: str
    condition: ConditionExpression | None
    initializer_raw: str | None
    increment_raw: str | None
    loop_range: SourceRange
    body_range: SourceRange | None
    coverage_hints: list[str]
    active_state: str
    confidence: str
```

`kind` 候補:

- `for`
- `while`
- `do_while`

`coverage_hints` 候補:

- `zero_iterations`
- `one_iteration`
- `multiple_iterations`
- `break_path_candidate`
- `continue_path_candidate`
- `infinite_loop_candidate`

### 5.8 TernaryNode

```python
@dataclass
class TernaryNode:
    ternary_id: str
    condition: ConditionExpression
    true_expression_raw: str
    false_expression_raw: str
    expression_range: SourceRange
    confidence: str
```

### 5.9 ReturnPath

```python
@dataclass
class ReturnPath:
    return_id: str
    return_range: SourceRange
    expression_raw: str | None
    return_kind: str
    related_variables: list[str]
    related_calls: list[str]
    active_state: str
    confidence: str
    evidence: str
```

`return_kind` 候補:

| return_kind | 意味 |
|---|---|
| `void_return` | `return;` |
| `constant_return` | 定数を返す |
| `parameter_return` | 引数を返す |
| `local_return` | ローカル変数を返す |
| `global_return` | グローバル候補を返す |
| `call_return` | 関数呼び出し結果を返す |
| `error_like_return` | エラー値らしい戻り |
| `unknown` | 判定不能 |

### 5.10 CoverageItem

```python
@dataclass
class CoverageItem:
    coverage_id: str
    coverage_type: str
    target_id: str
    purpose: str
    condition_value: str | None
    required_state: str | None
    related_variables: list[str]
    related_calls: list[str]
    review_required: bool
    confidence: str
```

`coverage_type` 候補:

| coverage_type | 意味 |
|---|---|
| `branch_true` | if条件true側 |
| `branch_false` | if条件false側 |
| `condition_true` | 単一条件true |
| `condition_false` | 単一条件false |
| `switch_case` | switch case到達 |
| `switch_default` | default到達 |
| `loop_zero` | ループ0回 |
| `loop_one` | ループ1回 |
| `loop_many` | ループ複数回 |
| `return_path` | return経路到達 |
| `ternary_true` | 三項演算子true側 |
| `ternary_false` | 三項演算子false側 |
| `review` | 人手レビューが必要な観点 |

### 5.11 BranchAnalyzerWarning

```python
@dataclass
class BranchAnalyzerWarning:
    code: str
    message: str
    line_number: int | None = None
    column: int | None = None
    text: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `branch_parse_failed` | 分岐構造の解析失敗 |
| `condition_parse_failed` | 条件式の解析失敗 |
| `unmatched_parenthesis` | 条件式括弧の対応不整合 |
| `unmatched_brace` | body範囲のbrace対応不整合 |
| `switch_case_without_switch` | switch外case候補 |
| `fallthrough_candidate` | fall-through候補 |
| `loop_condition_unknown` | loop条件の判定不能 |
| `complex_condition` | 条件式が複雑 |
| `side_effect_in_condition` | 条件式内に副作用候補 |
| `call_in_condition` | 条件式内に関数呼び出し |
| `conditional_inactive_region` | inactive条件下の分岐候補 |
| `unknown_active_state` | 条件コンパイル有効性不明 |

---

## 6. 解析設計

### 6.1 基本アルゴリズム

処理フロー:

```text
analyze_branches(request)
  1. source_digest / token stream を取得する
  2. function_location.body_range を取得する
  3. body範囲内の制御構文tokenを走査する
  4. if / else if / else を抽出する
  5. switch / case / default を抽出する
  6. for / while / do while を抽出する
  7. ternary operator を抽出する
  8. return statement を抽出する
  9. 各条件式を ConditionExpression に変換する
 10. Step 08 の変数アクセス情報と関連付ける
 11. Step 09 の call site 情報と関連付ける
 12. coverage item を生成する
 13. conditional active_state を付与する
 14. warnings / confidence を整理する
 15. CoverageDesignReport を返す
```

### 6.2 if / else if / else 抽出

対象例:

```c
if (mode == MODE_AUTO) {
    UpdateAuto();
} else if (mode == MODE_MANUAL) {
    UpdateManual();
} else {
    SetError(ERR_MODE);
}
```

方針:

- `if` token の直後の `(` から対応する `)` までを条件式とする
- 条件式後の statement または block をbody_rangeとする
- `else if` は `else_if` として親ifに関連付ける
- `else` はconditionなしのbranchとして扱う
- braceなし単文bodyも範囲を取る
- ネストレベルを保持する

### 6.3 switch / case 抽出

対象例:

```c
switch (state) {
case STATE_INIT:
    Init();
    break;
case STATE_RUN:
    Run();
    break;
default:
    Error();
    break;
}
```

方針:

- `switch` 条件式を抽出する
- switch body内の `case` / `default` を抽出する
- `case` labelは constant / macro / enum_candidate として分類する
- `break` がないcaseは fallthrough_candidate とする
- fall-through commentの検出は初期では必須にしない
- defaultがない場合は coverage itemにreview項目を追加してもよい

### 6.4 loop 抽出

対象:

- `for (i = 0; i < n; i++)`
- `while (p != NULL)`
- `do { ... } while (retry);`

方針:

- for は initializer / condition / increment を分ける
- while / do while はconditionを抽出する
- ループ条件が空の場合、infinite_loop_candidate を付与する
- coverage itemとして zero / one / many を候補生成する
- break / continue がbody内にあれば coverage_hints に追加する

### 6.5 condition expression 解析

代表パターン:

| パターン | condition_kind |
|---|---|
| `x == 0` | comparison |
| `x != 0` | comparison |
| `p == NULL` | null_check |
| `p != NULL` | null_check |
| `x >= MIN && x <= MAX` | range_check / compound |
| `mode == MODE_AUTO` | macro_check / comparison |
| `CheckLimit(x)` | call_result |
| `a && b` | compound |
| `a || b` | compound |

方針:

- 完全な式木は作らないが、トップレベルの `&&` / `||` は分解する
- 比較演算子を抽出する
- `NULL` / `0` との比較は null_check候補にする
- 同一変数に対する上下限比較は range_check候補にする
- 条件式内の関数呼び出しは Step 09 の call site と関連付ける
- 条件式内の `++` / `--` / assignment は side_effect_in_condition warningを付ける

### 6.6 return path 抽出

対象例:

```c
if (error) {
    return ERROR;
}
return OK;
```

方針:

- body範囲内の `return` tokenを抽出する
- `return;` と `return expr;` を区別する
- return expression内の変数・呼び出しをStep 08/09と関連付ける
- `ERROR` / `ERR_` / `NG` / `FAIL` など名前ヒントがある場合、error_like_return候補にする
- 最後のreturnはnormal return候補として扱う。ただし断定しない

### 6.7 coverage item生成

生成方針:

- if条件ごとに true / false を生成する
- else branchが存在する場合は else到達項目を生成する
- 複合条件は各単一条件の true / false 候補を生成する
- switchは各caseとdefaultの到達項目を生成する
- loopは zero / one / many を生成する
- return文ごとに return path item を生成する
- 条件が複雑な場合は review item を生成する

Coverage item ID例:

```text
BR_Control_Update_001_TRUE
BR_Control_Update_001_FALSE
COND_Control_Update_002_A_TRUE
SW_Control_Update_001_CASE_STATE_INIT
LOOP_Control_Update_001_ZERO
RET_Control_Update_003
```

### 6.8 context linking

Step 08 / Step 09 の情報を使い、coverage itemに関連情報を付ける。

例:

```c
if (g_state == STATE_RUN && CheckLimit(sensor)) {
    WritePort(PORT_A, sensor);
}
```

関連付け:

- related_variables: `g_state`, `sensor`
- related_calls: `CheckLimit`
- branch body call: `WritePort`
- stub candidate influence: `CheckLimit` の戻り値制御が必要

---

## 7. CLI 接続設計

### 7.1 analyze-function の Step 10 接続

Step 10 では、`analyze-function` を分岐・条件カバレッジ設計まで進める。

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
7. Step 10 の Branch / Condition Analyzer を実行する
8. `coverage_design.json` を生成する
9. `coverage_design.md` を生成する
10. Step 11 の Boundary / Equivalence Candidate Generator が必要であることを message に含める
11. 抽出に成功した場合、status `partial` または `coverage_designed` を返す

### 7.2 analyze-branches コマンド案

開発・debug 用に以下の独立コマンドを検討する。

```bat
unit-test-runner analyze-branches ^
  --source D:\work\product\src\control.c ^
  --source-digest D:\work\unit_test_workspace\Control_Update\reports\source_digest.json ^
  --function-location D:\work\unit_test_workspace\Control_Update\reports\function_location.json ^
  --global-access D:\work\unit_test_workspace\Control_Update\reports\global_access.json ^
  --call-report D:\work\unit_test_workspace\Control_Update\reports\call_report.json ^
  --out D:\work\unit_test_workspace\Control_Update\reports\coverage_design.json
```

扱い:

- 公開コマンドにするかは実装時判断とする
- Step 10 計画では必須ではない
- 必須なのは internal usecase と `analyze-function` 接続である

---

## 8. Report 設計

### 8.1 coverage_design.json

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
    "status": "analyzed"
  },
  "branches": [
    {
      "branch_id": "BR_001",
      "kind": "if",
      "line": 120,
      "condition": {
        "condition_id": "COND_001",
        "raw": "mode == MODE_AUTO && CheckLimit(sensor)",
        "condition_kind": "compound",
        "related_variables": ["mode", "sensor"],
        "related_calls": ["CheckLimit"],
        "complexity": "compound"
      },
      "nesting_level": 0,
      "confidence": "high"
    }
  ],
  "coverage_items": [
    {
      "coverage_id": "BR_Control_Update_001_TRUE",
      "coverage_type": "branch_true",
      "target_id": "BR_001",
      "purpose": "if condition is true",
      "condition_value": "true",
      "related_variables": ["mode", "sensor"],
      "related_calls": ["CheckLimit"],
      "review_required": true,
      "confidence": "high"
    },
    {
      "coverage_id": "BR_Control_Update_001_FALSE",
      "coverage_type": "branch_false",
      "target_id": "BR_001",
      "purpose": "if condition is false",
      "condition_value": "false",
      "related_variables": ["mode", "sensor"],
      "related_calls": ["CheckLimit"],
      "review_required": true,
      "confidence": "high"
    }
  ],
  "warnings": []
}
```

### 8.2 coverage_design.md

内容例:

```markdown
# Coverage Design Report

## Target

- Source: D:/work/product/src/control.c
- Function: Control_Update
- Status: analyzed

## Branches

| ID | Line | Kind | Condition | Related Variables | Related Calls | Confidence |
|---|---:|---|---|---|---|---|
| BR_001 | 120 | if | `mode == MODE_AUTO && CheckLimit(sensor)` | mode, sensor | CheckLimit | high |

## Switches

| ID | Line | Expression | Cases | Default |
|---|---:|---|---:|---|

## Loops

| ID | Line | Kind | Condition | Coverage Hints |
|---|---:|---|---|---|

## Return Paths

| ID | Line | Expression | Kind | Confidence |
|---|---:|---|---|---|

## Coverage Items

| ID | Type | Target | Purpose | Review Required |
|---|---|---|---|---|
| BR_Control_Update_001_TRUE | branch_true | BR_001 | if condition is true | yes |
| BR_Control_Update_001_FALSE | branch_false | BR_001 | if condition is false | yes |

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
      branches/
        simple_if.c
        if_else.c
        else_if_chain.c
        nested_if.c
        switch_case.c
        switch_fallthrough.c
        for_loop.c
        while_loop.c
        do_while_loop.c
        ternary.c
        logical_and_or.c
        null_check.c
        range_check.c
        return_paths.c
        condition_call.c
        side_effect_condition.c
        inactive_branch.c
        malformed_condition.c
```

### 9.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| BRN-001 | simple if | `if (x)` | branch true/false item |
| BRN-002 | if else | `if/else` | else branchを関連付け |
| BRN-003 | else if | chain | else_ifを親ifと関連付け |
| BRN-004 | nested if | nested | nesting level保持 |
| BRN-005 | switch case | switch | case coverage item |
| BRN-006 | default | defaultあり | switch_default item |
| BRN-007 | fallthrough | breakなしcase | fallthrough warning |
| BRN-008 | for loop | `for` | zero/one/many item |
| BRN-009 | while loop | `while` | zero/one/many item |
| BRN-010 | do while | `do while` | one/many item |
| BRN-011 | ternary | `a ? b : c` | ternary true/false item |
| BRN-012 | logical and | `a && b` | condition items |
| BRN-013 | logical or | `a || b` | condition items |
| BRN-014 | null check | `p == NULL` | null_check |
| BRN-015 | range check | `x >= MIN && x <= MAX` | range_check候補 |
| BRN-016 | condition call | `if (Check())` | related call |
| BRN-017 | side effect condition | `if (x++)` | side_effect warning |
| BRN-018 | return path | multiple return | return path items |
| BRN-019 | inactive branch | `#if 0`内 | inactive warning |
| BRN-020 | malformed condition | 括弧不整合 | warning condition_parse_failed |
| BRN-021 | json output | coverage_design.json | JSON parse可能 |
| BRN-022 | markdown output | coverage_design.md | expected sectionあり |
| BRN-023 | analyze-function integration | Step04-10 | coverage_design生成 |

### 9.3 テスト方針

- branch scanner は小さなC断片で単体テストする
- condition analyzer は条件式単体でもテストする
- switch / loop は個別fixtureで検証する
- return path は複数return関数で検証する
- integration test では Step 05 source_digest、Step 06 function_location、Step 08 global_access、Step 09 call_report fixture と接続する
- JSONは `json.loads()` で検証する
- Markdownは主要sectionの存在を検証する
- 複雑条件は過信せず warning / review_required として検証する

---

## 10. 実装タスク分解

### Task 10-01: Coverage design model 定義

成果物:

- `src/unit_test_runner/c_analyzer/coverage_models.py`
- `BranchAnalysisRequest`
- `CoverageDesignReport`
- `BranchNode`
- `ConditionExpression`
- `ConditionOperand`
- `SwitchNode`
- `CaseNode`
- `LoopNode`
- `TernaryNode`
- `ReturnPath`
- `CoverageItem`
- `BranchAnalyzerWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 10-02: Branch scanner

成果物:

- `src/unit_test_runner/c_analyzer/branch_scanner.py`
- if / else if / else抽出
- nesting level
- branch body range推定

完了条件:

- BRN-001 から BRN-004 が通る

### Task 10-03: Switch scanner

成果物:

- switch expression抽出
- case / default抽出
- fallthrough候補検出

完了条件:

- BRN-005 から BRN-007 が通る

### Task 10-04: Loop scanner

成果物:

- for / while / do while抽出
- loop condition抽出
- zero / one / many coverage hint生成

完了条件:

- BRN-008 から BRN-010 が通る

### Task 10-05: Ternary scanner

成果物:

- `?:` 抽出
- true / false expression範囲推定
- coverage item生成

完了条件:

- BRN-011 が通る

### Task 10-06: Condition expression analyzer

成果物:

- comparison抽出
- logical and/or分解
- null_check抽出
- range_check候補抽出
- related variable / call linking

完了条件:

- BRN-012 から BRN-017 が通る

### Task 10-07: Return path analyzer

成果物:

- return文抽出
- return expression分類
- early/error/normal候補
- return coverage item生成

完了条件:

- BRN-018 が通る

### Task 10-08: Conditional context integration

成果物:

- Step 05 active_stateとの接続
- inactive / unknown warning
- confidence調整

完了条件:

- BRN-019 が通る

### Task 10-09: Coverage item generator

成果物:

- branch true/false
- condition true/false
- switch case/default
- loop zero/one/many
- return path
- review item

完了条件:

- coverage_items が期待形式で生成される

### Task 10-10: Coverage design writer

成果物:

- `src/unit_test_runner/c_analyzer/coverage_design_writer.py`
- `coverage_design.json`
- `reports/coverage_design_markdown.py`

完了条件:

- BRN-021 / BRN-022 が通る

### Task 10-11: analyze-function 接続

成果物:

- Step 04 source membership取得
- Step 05 source_digest生成
- Step 06 function_location生成
- Step 07 function_signature生成
- Step 08 global_access生成
- Step 09 call_report生成
- Step 10 coverage_design生成
- CLI `analyze-function` の出力更新

完了条件:

- BRN-023 が通る

### Task 10-12: fixture / test 整備

成果物:

- `tests/fixtures/c_sources/branches/...`
- `tests/unit/test_branch_scanner.py`
- `tests/unit/test_switch_scanner.py`
- `tests/unit/test_loop_scanner.py`
- `tests/unit/test_condition_analyzer.py`
- `tests/unit/test_return_path_analyzer.py`
- `tests/unit/test_coverage_item_generator.py`
- `tests/unit/test_coverage_design_writer.py`
- `tests/unit/test_analyze_function_partial_coverage.py`

完了条件:

- BRN-001 から BRN-023 が通る

---

## 11. 受け入れ基準

Step 10 は、以下をすべて満たしたら完了とする。

1. `if` / `else if` / `else` を抽出できる
2. branch nesting level と body range を保持できる
3. `switch` / `case` / `default` を抽出できる
4. fall-through候補をwarningとして保持できる
5. `for` / `while` / `do while` を抽出できる
6. loop zero / one / many coverage itemを生成できる
7. 三項演算子を抽出できる
8. 比較条件を抽出できる
9. `&&` / `||` を含む複合条件を分解できる
10. NULLチェック候補を抽出できる
11. 範囲チェック候補を抽出できる
12. 条件式内の関連変数をStep 08情報と関連付けられる
13. 条件式内の関連呼び出しをStep 09情報と関連付けられる
14. 条件式内副作用候補をwarningとして保持できる
15. return文とreturn経路を抽出できる
16. branch / condition / switch / loop / return coverage itemを生成できる
17. 複雑条件を review_required として扱える
18. inactive / unknown conditional contextの分岐候補にwarningを付与できる
19. `coverage_design.json` を生成できる
20. `coverage_design.md` を生成できる
21. `analyze-function` が Step 10 時点では coverage design まで進み、Step 11 が必要である旨を返せる
22. Step 11 の Boundary / Equivalence Candidate Generator に渡せる条件式情報がある
23. 実測カバレッジ計測へ踏み込みすぎていない
24. テストケース本生成へ踏み込みすぎていない

---

## 12. 成果物

Step 10 の成果物は以下とする。

```text
src/
  unit_test_runner/
    c_analyzer/
      coverage_models.py
      branch_scanner.py
      switch_scanner.py
      loop_scanner.py
      ternary_scanner.py
      condition_analyzer.py
      return_path_analyzer.py
      coverage_item_generator.py
      coverage_design_analyzer.py
      coverage_design_writer.py
    reports/
      coverage_design_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    c_sources/
      branches/
        simple_if.c
        if_else.c
        else_if_chain.c
        nested_if.c
        switch_case.c
        switch_fallthrough.c
        for_loop.c
        while_loop.c
        do_while_loop.c
        ternary.c
        logical_and_or.c
        null_check.c
        range_check.c
        return_paths.c
        condition_call.c
        side_effect_condition.c
        inactive_branch.c
        malformed_condition.c
  unit/
    test_branch_scanner.py
    test_switch_scanner.py
    test_loop_scanner.py
    test_condition_analyzer.py
    test_return_path_analyzer.py
    test_coverage_item_generator.py
    test_coverage_design_writer.py
    test_analyze_function_partial_coverage.py
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/c_analyzer/tokens.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/call_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/global_access_models.py` 必要な場合のみ

---

## 13. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| 条件式解析の複雑さ | 完全な式木を作らないと難しい条件がある | トップレベル演算子中心に抽出し、complex/review_requiredを残す |
| else対応の誤判定 | ネストしたifでdangling elseが紛らわしい | token位置とbody rangeで親子関係を保守的に推定する |
| switch fall-through | 意図的fall-throughとbreak漏れの区別が難しい | 初期はfallthrough_candidateとしてwarningに留める |
| loop回数候補の過信 | 実際に0回到達可能かは入力条件次第 | zero/one/manyは設計候補としてreview_requiredにする |
| 条件式内副作用 | `if (x++ && f())` の評価順序が絡む | side_effect_in_condition warningを付ける |
| macro条件 | macro展開しないと実条件が分からない | macro_check / unknownとして保持する |
| 実測coverageと混同 | 設計項目と実行結果を混同しやすい | reportで設計カバレッジであることを明記する |
| Step11責務の侵食 | 境界値や具体入力値をここで生成したくなる | Step10は条件式抽出まで。値候補生成はStep11へ委譲する |

---

## 14. Step 11 への接続

Step 10 完了後、Step 11 では Boundary / Equivalence Candidate Generator を実装する。
Step 11 は、Step 10 の `ConditionExpression` と `CoverageItem` を使い、境界値候補、同値クラス候補、NULL / 非NULL、enum / macro値、範囲内 / 範囲外候補を生成する。

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
```

Step 11 で使う情報:

- parameters
- TypeInfo
- direction_hint
- global/parameter access
- condition expressions
- comparison operators
- macro / enum candidate
- coverage items
- call return usage

Step 10 の責務は、Boundary / Equivalence Candidate Generator が具体的な値候補を考えるための、条件式・演算子・関連変数・関連呼び出しを整理することである。

---

## 15. まとめ

Step 10 は、対象関数の分岐・条件・ループ・return経路を整理し、単体テスト設計で確認すべきカバレッジ項目を作るステップである。

このステップにより、対象関数について、どのif条件、switch case、loop実行回数、return経路をテスト観点として扱うべきかを `coverage_design` として整理できる。

ただし、Step 10 は実測カバレッジ計測や具体的な境界値生成を行う段階ではない。
設計カバレッジ候補に責務を絞り、Step 11 の Boundary / Equivalence Candidate Generator へ安全な入力を渡すことを完了条件とする。

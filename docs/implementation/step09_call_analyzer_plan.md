# Step 09: Call Analyzer 実装計画

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

---

## 1. 位置づけ

本書は、`unitTestRunner` の第9ステップとして **Call Analyzer** を実装するための計画である。

Step 08 では、対象関数の本文からグローバル変数候補、file scope static変数、extern変数、引数経由の副作用候補を抽出する計画を定義した。
Step 09 では、Step 06 で特定した関数本文範囲、Step 07 のシグネチャ、Step 08 の変数アクセス情報を使い、対象関数内の **関数呼び出し、呼び出し先分類、引数式、戻り値利用、スタブ候補、副作用候補** を抽出する。

Step 09 は、単体テストでモック・スタブが必要になりそうな依存関数を見つける段階である。
ただし、スタブコードの生成やテストケース生成はまだ行わない。
スタブ雛形生成は後続ステップで扱う。
分岐・条件網羅、境界値・同値クラス候補の生成も Step 10 以降で扱う。

Step 09 の主な責務は以下である。

- 関数本文内の関数呼び出し式を抽出する
- 制御構文、マクロ、型キャスト、関数定義、プロトタイプを呼び出し候補から除外する
- 呼び出し先を same-file function / static function / external function / standard library candidate / macro-like / unknown に分類する
- 呼び出し行、呼び出し式、引数式、戻り値利用有無を記録する
- ポインタ引数、グローバル変数、アドレス渡しを伴う呼び出しを副作用候補として記録する
- Step 08 の address_taken / passed_to_call 候補と照合する
- スタブ候補を抽出する
- 呼び出し回数期待値の設計候補を作る。ただし確定はしない
- `call_report.json` / `call_report.md` を生成する
- Step 10 の Branch / Condition Analyzer に渡せる call site 情報を整理する

---

## 2. 目的

Step 09 の目的は、関数単位テストで差し替え・観測が必要になる **呼び出し依存情報** を安定して抽出することである。

具体的には、以下を実現する。

- 対象関数内で呼ばれる関数を一覧化できる
- 同一 `.c` 内に定義がある関数と、外部依存関数を区別できる
- file scope static関数らしき呼び出しを区別できる
- 標準ライブラリ候補を区別できる
- function-like macroの可能性がある呼び出しを過信せず扱える
- 呼び出しごとの引数式を取得できる
- 戻り値が代入、比較、return、条件式で使われているかを判定できる
- 戻り値が無視されている呼び出しを判定できる
- `&global`、`&local`、pointer引数、array引数、global変数を渡す呼び出しを副作用候補として扱える
- 外部関数呼び出しをスタブ候補として出力できる
- 未分類の呼び出しを warning と raw expression として保持できる
- `call_report.json` / `call_report.md` を出力できる
- `analyze-function` を Step 09 時点で「グローバルアクセス候補 + 呼び出し候補抽出」まで進められる

---

## 3. スコープ

### 3.1 実装対象

Step 09 で実装するもの:

1. Call expression scanner
   - 関数本文内の `identifier(` パターン抽出
   - 対応する `)` の検出
   - ネストした呼び出しへの対応
   - 引数式のトップレベルcomma分割

2. Non-call filter
   - `if` / `while` / `switch` / `for` / `return` / `sizeof` などの除外
   - 関数定義・プロトタイプの除外
   - 関数ポインタ宣言の除外
   - castらしき表現の除外
   - preprocessor directive行の除外

3. Call target classifier
   - same-file function
   - same-file static function
   - external function candidate
   - standard library candidate
   - macro-like candidate
   - function pointer call candidate
   - unknown

4. Argument analyzer
   - 引数式 raw text
   - 引数式内identifier
   - global変数引数
   - address-taking引数
   - pointer/array parameter引数
   - literal / constant / macro-like 引数

5. Return usage analyzer
   - 戻り値無視
   - 代入先あり
   - returnで返す
   - 条件式で使用
   - 比較式で使用
   - logical expressionで使用
   - cast / wrapperで使用
   - unknown

6. Side effect bridge
   - Step 08 の `passed_to_call` / `address_taken` と照合
   - 呼び出し引数経由の副作用候補を出力
   - スタブ設計時に注意すべき引数を記録

7. Stub candidate extractor
   - external function candidate
   - hardware-like API candidate
   - time-like API candidate
   - I/O-like API candidate
   - unknown dependency candidate
   - return value control needed
   - call count assertion candidate

8. Reports
   - `call_report.json`
   - `call_report.md`

9. CLI 接続
   - `analyze-function` を call analysis まで進める
   - status `partial` または `calls_analyzed` を返す
   - Step 10 の Branch / Condition Analyzer が必要である旨を message に含める

10. Tests
   - simple call
   - nested call
   - macro-like call
   - function pointer call
   - standard library call
   - external call
   - same-file static call
   - return value assignment
   - return value ignored
   - call in condition
   - address argument
   - global argument
   - pointer parameter argument

### 3.2 対象外

Step 09 では以下を対象外とする。

- 実際のスタブCコード生成
- モック動作仕様の確定
- 呼び出し回数期待値の確定
- 引数期待値の確定
- 分岐・条件網羅候補生成
- 境界値・同値クラス候補生成
- 外部関数の実体探索をinclude / libraryまで完全に行うこと
- リンクエラー解析
- ハードウェアI/O APIの完全分類
- 関数ポインタ呼び出し先の完全解決
- macro展開後の呼び出し解析
- inter-procedural解析
- テストハーネス生成

Step 09 では、関数本文から読み取れる呼び出し依存候補を保守的に抽出することに限定する。

---

## 4. 入力と出力

### 4.1 入力

主入力:

- Step 04 の `build_context`
- Step 05 の `source_digest`
- Step 06 の `function_location`
- Step 07 の `function_signature`
- Step 08 の `global_access`
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
  "global_access": "reports/global_access.json"
}
```

### 4.2 出力

Step 09 の主要出力は `call_report` である。

```text
workspace/
  Control_Update/
    reports/
      source_digest.json
      function_location.json
      function_signature.json
      global_access.json
      call_report.json
      call_report.md
    intermediate/
      masked_source.c
      function_slice.c
```

`call_report.json` は Step 10 以降の入力になる。

---

## 5. データモデル設計

### 5.1 CallAnalysisRequest

```python
@dataclass
class CallAnalysisRequest:
    source_path: Path
    source_text: str
    masked_text: str
    tokens: list[LexToken]
    function_location: FunctionLocation
    function_signature: FunctionSignature
    global_access: GlobalAccessReport
```

役割:

- Call Analyzer の入力条件をまとめる
- CLI / internal usecase の境界を明確にする

### 5.2 CallReport

```python
@dataclass
class CallReport:
    source_path: Path
    function_name: str
    status: str
    calls: list[FunctionCall]
    stub_candidates: list[StubCandidate]
    side_effect_candidates: list[CallSideEffectCandidate]
    unresolved_calls: list[FunctionCall]
    warnings: list[CallAnalyzerWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `analyzed` | 呼び出し候補抽出が完了した |
| `partial` | 一部不明だが主要候補は抽出した |
| `ambiguous` | 呼び出し分類が曖昧 |
| `malformed` | token範囲や括弧対応が壊れて解析不能 |

### 5.3 FunctionCall

```python
@dataclass
class FunctionCall:
    call_id: str
    name: str
    target_kind: str
    call_range: SourceRange
    name_position: SourcePosition
    arguments: list[CallArgument]
    return_usage: ReturnUsage
    nesting_level: int
    conditional_context: ConditionalContext | None
    confidence: str
    evidence: str
    warnings: list[CallAnalyzerWarning]
```

`target_kind` 候補:

| target_kind | 意味 |
|---|---|
| `same_file_function` | 同一 `.c` 内の非static関数候補 |
| `same_file_static_function` | 同一 `.c` 内のstatic関数候補 |
| `external_function` | 外部関数候補 |
| `standard_library` | 標準ライブラリ候補 |
| `macro_like` | function-like macro候補 |
| `function_pointer` | 関数ポインタ呼び出し候補 |
| `compiler_intrinsic` | コンパイラ組み込み候補 |
| `unknown` | 判定不能 |

### 5.4 CallArgument

```python
@dataclass
class CallArgument:
    index: int
    raw: str
    expression_range: SourceRange
    identifiers: list[IdentifierUse]
    argument_kind: str
    passing_mode_hint: str
    confidence: str
    warnings: list[CallAnalyzerWarning]
```

`argument_kind` 候補:

| argument_kind | 意味 |
|---|---|
| `literal` | 数値・文字列・文字定数 |
| `constant_or_macro` | 定数macro候補 |
| `parameter` | 関数引数 |
| `local` | ローカル変数 |
| `global` | グローバル変数候補 |
| `address_of_global` | `&global` |
| `address_of_local` | `&local` |
| `pointer_dereference` | `*p` |
| `member_access` | `x.member` / `x->member` |
| `call_expression` | ネストした呼び出し |
| `expression` | その他式 |
| `unknown` | 判定不能 |

`passing_mode_hint` 候補:

- `by_value`
- `by_address`
- `pointer_or_array`
- `callback_candidate`
- `unknown`

### 5.5 ReturnUsage

```python
@dataclass
class ReturnUsage:
    usage_kind: str
    consumer_range: SourceRange | None
    assigned_to: str | None
    compared_with: str | None
    evidence: str
    confidence: str
```

`usage_kind` 候補:

| usage_kind | 意味 |
|---|---|
| `ignored` | 戻り値を使っていない |
| `assigned` | 変数に代入している |
| `returned` | 呼び出し結果をreturnしている |
| `condition` | if/whileなどの条件に使っている |
| `comparison` | 比較演算に使っている |
| `logical` | `&&` / `||` に使っている |
| `argument_to_call` | 別の呼び出しの引数になっている |
| `unknown` | 判定不能 |

### 5.6 StubCandidate

```python
@dataclass
class StubCandidate:
    name: str
    reason: str
    target_kind: str
    call_count: int
    return_value_control_needed: bool
    argument_capture_needed: bool
    side_effect_control_needed: bool
    related_calls: list[str]
    confidence: str
    tags: list[str]
```

`tags` 候補:

- `external_dependency`
- `hardware_like`
- `time_like`
- `io_like`
- `stateful`
- `return_value_used`
- `return_value_ignored`
- `pointer_argument`
- `global_argument`
- `callback_candidate`
- `unknown_dependency`

### 5.7 CallSideEffectCandidate

```python
@dataclass
class CallSideEffectCandidate:
    call_id: str
    call_name: str
    kind: str
    argument_index: int | None
    related_identifier: str | None
    reason: str
    confidence: str
    evidence: str
```

`kind` 候補:

| kind | 意味 |
|---|---|
| `global_passed_by_address` | globalアドレスを渡している |
| `local_passed_by_address` | localアドレスを渡している |
| `parameter_pointer_passed` | pointer/array引数を渡している |
| `global_pointer_passed` | global pointerを渡している |
| `callback_passed` | callback候補を渡している |
| `unknown` | 不明な副作用候補 |

### 5.8 CallAnalyzerWarning

```python
@dataclass
class CallAnalyzerWarning:
    code: str
    message: str
    line_number: int | None = None
    column: int | None = None
    text: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `call_parse_failed` | 呼び出し式の解析失敗 |
| `unmatched_call_parenthesis` | 呼び出しの括弧対応が崩れている |
| `call_target_unresolved` | 呼び出し先分類不能 |
| `macro_call_candidate` | macro呼び出し候補 |
| `function_pointer_call_candidate` | 関数ポインタ呼び出し候補 |
| `standard_library_guess` | 標準ライブラリ候補として推定 |
| `return_usage_unknown` | 戻り値利用の判定不能 |
| `argument_parse_failed` | 引数式の解析失敗 |
| `side_effect_unknown` | 副作用有無が不明 |
| `conditional_inactive_region` | inactive条件下の呼び出し候補 |
| `unknown_active_state` | 条件コンパイル有効性不明 |

---

## 6. 解析設計

### 6.1 基本アルゴリズム

処理フロー:

```text
analyze_calls(request)
  1. source_digest / token stream を取得する
  2. function_location.body_range を取得する
  3. body範囲内の identifier + `(` 候補を抽出する
  4. non-call filter で制御構文、sizeof、cast、macro directiveを除外する
  5. 対応する `)` を探し、call_range を確定する
  6. 引数式をトップレベルcommaで分割する
  7. 呼び出し先を分類する
  8. 引数式を Step 08 の identifier情報と照合する
  9. 戻り値利用を呼び出し周辺tokenから判定する
 10. side effect candidate を作成する
 11. stub candidate を集約する
 12. conditional context を付与する
 13. warnings / confidence を整理する
 14. CallReport を返す
```

### 6.2 call expression 抽出

対象例:

```c
ReadSensor(mode);
g_error = GetErrorCode();
if (CheckLimit(value)) {
    WritePort(PORT_A, value);
}
result = Convert(ReadRaw());
```

抽出方針:

- body_range 内の `identifier` の直後に `(` があるtokenを候補にする
- 対応する `)` を探す
- `(` / `)` の対応はネストを考慮する
- コメント・文字列内の候補は Step 05 でmask済みのため対象外
- brace depth は関数本文内の範囲として扱う

### 6.3 non-call filter

除外対象:

- `if (`
- `while (`
- `switch (`
- `for (`
- `sizeof (`
- `return (` は通常関数呼び出しではない。ただし `return f()` 内の `f` は抽出する
- cast: `(int)x`、`(TYPE *)p`
- function definition / prototype
- preprocessor directive

注意:

- `sizeof f()` のような特殊ケースは低頻度とし、fixtureが出た段階で補正する
- cast判定は完全には行わず、型名候補や括弧位置から保守的に除外する

### 6.4 呼び出し先分類

分類の優先順位:

1. Step 05 の function-like macro 名に一致する → `macro_like`
2. 関数ポインタ呼び出しらしい、例: `(*cb)(x)` / `cb(x)` かつ cbがparameter/local pointer候補 → `function_pointer`
3. 同一 `.c` 内で Step 06 の全関数一覧に含まれる → `same_file_function`
4. 同一 `.c` 内でstatic関数として検出される → `same_file_static_function`
5. 標準ライブラリ既知リストに含まれる → `standard_library`
6. VC6 / compiler intrinsic 既知リストに含まれる → `compiler_intrinsic`
7. それ以外 → `external_function`
8. 情報不足 → `unknown`

標準ライブラリ候補例:

```text
memcpy memset memcmp strcpy strncpy strcmp strlen sprintf printf malloc free abs labs qsort bsearch
```

注意:

- 本ツールはVC6/C90対象のため、`snprintf` は標準前提にしない
- 標準ライブラリ候補でもスタブ不要とは限らないが、初期stub candidateからは低優先度にする

### 6.5 引数式解析

対象例:

```c
WritePort(PORT_A, g_state.value);
ReadData(&g_buffer[0], size);
UpdateStatus(status, &g_error);
callback(mode);
```

方針:

- `(` と `)` の内側をトップレベルcommaで分割する
- 引数式内のidentifierを抽出する
- Step 08 の分類情報を参照し、parameter / local / global / macro / unknown を付与する
- `&` が付く場合は by_address とする
- `*p`、`p->field`、`p[index]` は pointer_or_array とする
- ネストした呼び出しは `call_expression` とする

### 6.6 戻り値利用解析

代表パターン:

| パターン | usage_kind |
|---|---|
| `Foo();` | `ignored` |
| `x = Foo();` | `assigned` |
| `return Foo();` | `returned` |
| `if (Foo())` | `condition` |
| `while (Foo())` | `condition` |
| `Foo() == 0` | `comparison` |
| `Foo() && Bar()` | `logical` |
| `Bar(Foo())` | `argument_to_call` |

方針:

- 呼び出し式の親文脈を周辺tokenから推定する
- 完全なASTは作らない
- 判定不能なら `unknown`
- 戻り値が使われている外部関数は `return_value_control_needed=true` のstub候補にする

### 6.7 side effect bridge

Step 08 の情報を使う。

例:

```c
UpdateStatus(&g_state);
FillBuffer(buffer, size);
ReadSensor(&sensor_value);
```

方針:

- `&global` を渡す場合、`global_passed_by_address`
- `&local` を渡す場合、`local_passed_by_address`
- pointer/array引数を渡す場合、`parameter_pointer_passed`
- global pointerを渡す場合、`global_pointer_passed`
- 関数名や関数ポインタらしき引数を渡す場合、`callback_passed`
- これらはスタブ仕様やテスト事前条件に影響するため、evidence付きで残す

### 6.8 stub candidate 抽出

stub candidate にする対象:

- `external_function`
- `unknown`
- hardware/time/ioらしき名前を持つ関数
- 戻り値が使われている関数
- pointer/global引数を受け取る関数
- 呼び出し回数がテスト観点になりそうな関数

名前ヒント:

| タグ | 名前ヒント |
|---|---|
| `hardware_like` | `Port`, `Io`, `IO`, `Device`, `Sensor`, `Ad`, `Da`, `Reg` |
| `time_like` | `Time`, `Timer`, `Tick`, `Clock`, `Delay`, `Sleep` |
| `io_like` | `Read`, `Write`, `Send`, `Recv`, `Open`, `Close` |
| `stateful` | `Init`, `Reset`, `Update`, `Set`, `Get` |

注意:

- 名前ヒントは仕様ではない
- reportでは review required として扱う
- Step 09 ではスタブ雛形を生成しない

---

## 7. CLI 接続設計

### 7.1 analyze-function の Step 09 接続

Step 09 では、`analyze-function` を呼び出し候補抽出まで進める。

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
6. Step 09 の Call Analyzer を実行する
7. `call_report.json` を生成する
8. `call_report.md` を生成する
9. Step 10 の Branch / Condition Analyzer が必要であることを message に含める
10. 抽出に成功した場合、status `partial` または `calls_analyzed` を返す

### 7.2 analyze-calls コマンド案

開発・debug 用に以下の独立コマンドを検討する。

```bat
unit-test-runner analyze-calls ^
  --source D:\work\product\src\control.c ^
  --source-digest D:\work\unit_test_workspace\Control_Update\reports\source_digest.json ^
  --function-location D:\work\unit_test_workspace\Control_Update\reports\function_location.json ^
  --function-signature D:\work\unit_test_workspace\Control_Update\reports\function_signature.json ^
  --global-access D:\work\unit_test_workspace\Control_Update\reports\global_access.json ^
  --out D:\work\unit_test_workspace\Control_Update\reports\call_report.json
```

扱い:

- 公開コマンドにするかは実装時判断とする
- Step 09 計画では必須ではない
- 必須なのは internal usecase と `analyze-function` 接続である

---

## 8. Report 設計

### 8.1 call_report.json

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
  "calls": [
    {
      "call_id": "CALL_001",
      "name": "ReadSensor",
      "target_kind": "external_function",
      "line": 120,
      "arguments": [
        {
          "index": 0,
          "raw": "mode",
          "argument_kind": "parameter",
          "passing_mode_hint": "by_value"
        }
      ],
      "return_usage": {
        "usage_kind": "assigned",
        "assigned_to": "sensor_value"
      },
      "confidence": "high",
      "evidence": "sensor_value = ReadSensor(mode)"
    },
    {
      "call_id": "CALL_002",
      "name": "WritePort",
      "target_kind": "external_function",
      "line": 135,
      "arguments": [
        {
          "index": 0,
          "raw": "PORT_A",
          "argument_kind": "constant_or_macro"
        },
        {
          "index": 1,
          "raw": "g_state.value",
          "argument_kind": "global"
        }
      ],
      "return_usage": {
        "usage_kind": "ignored"
      },
      "confidence": "high",
      "evidence": "WritePort(PORT_A, g_state.value)"
    }
  ],
  "stub_candidates": [
    {
      "name": "ReadSensor",
      "reason": "external function with return value used",
      "target_kind": "external_function",
      "call_count": 1,
      "return_value_control_needed": true,
      "argument_capture_needed": true,
      "side_effect_control_needed": false,
      "tags": ["external_dependency", "return_value_used", "hardware_like"]
    },
    {
      "name": "WritePort",
      "reason": "external I/O-like function",
      "target_kind": "external_function",
      "call_count": 1,
      "return_value_control_needed": false,
      "argument_capture_needed": true,
      "side_effect_control_needed": true,
      "tags": ["external_dependency", "io_like", "global_argument"]
    }
  ],
  "warnings": []
}
```

### 8.2 call_report.md

内容例:

```markdown
# Call Report

## Target

- Source: D:/work/product/src/control.c
- Function: Control_Update
- Status: analyzed

## Calls

| ID | Line | Name | Target Kind | Return Usage | Evidence | Confidence |
|---|---:|---|---|---|---|---|
| CALL_001 | 120 | ReadSensor | external_function | assigned | `sensor_value = ReadSensor(mode)` | high |
| CALL_002 | 135 | WritePort | external_function | ignored | `WritePort(PORT_A, g_state.value)` | high |

## Stub Candidates

| Name | Reason | Return Control | Arg Capture | Side Effect | Tags |
|---|---|---|---|---|---|
| ReadSensor | external function with return value used | yes | yes | no | external_dependency, return_value_used, hardware_like |
| WritePort | external I/O-like function | no | yes | yes | external_dependency, io_like, global_argument |

## Side Effect Candidates

| Call | Kind | Evidence | Confidence |
|---|---|---|---|

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
      calls/
        simple_call.c
        nested_call.c
        return_value_assigned.c
        return_value_ignored.c
        call_in_condition.c
        call_in_return.c
        standard_library_call.c
        macro_like_call.c
        function_pointer_call.c
        same_file_static_call.c
        external_call.c
        address_argument.c
        global_argument.c
        pointer_parameter_argument.c
        malformed_call.c
        conditional_call.c
        cast_not_call.c
```

### 9.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| CAL-001 | simple call | `Foo();` | call抽出、return ignored |
| CAL-002 | assigned return | `x = Foo();` | return_usage assigned |
| CAL-003 | ignored return | `Foo();` | return_usage ignored |
| CAL-004 | call in condition | `if (Foo())` | return_usage condition |
| CAL-005 | call in return | `return Foo();` | return_usage returned |
| CAL-006 | nested call | `Foo(Bar())` | FooとBarを抽出 |
| CAL-007 | standard library | `memcpy(...)` | target_kind standard_library |
| CAL-008 | macro-like | `MAX(a,b)` | macro_like candidate |
| CAL-009 | function pointer | `cb(x)` | function_pointer candidate |
| CAL-010 | same file static | static helper call | same_file_static_function |
| CAL-011 | external call | 未定義関数 | external_function |
| CAL-012 | argument split | `Foo(a, Bar(b,c), d)` | top-level引数3つ |
| CAL-013 | address global | `Foo(&g_value)` | global_passed_by_address |
| CAL-014 | address local | `Foo(&local)` | local_passed_by_address |
| CAL-015 | pointer param | `Foo(buffer)` | parameter_pointer_passed |
| CAL-016 | global argument | `Foo(g_state)` | global argument |
| CAL-017 | cast not call | `(int)(x)` | call候補にしない |
| CAL-018 | sizeof not call | `sizeof(x)` | call候補にしない |
| CAL-019 | malformed call | 括弧不整合 | warning unmatched_call_parenthesis |
| CAL-020 | inactive conditional | `#if 0 Foo()` | inactive warning |
| CAL-021 | stub candidate return used | `x = External()` | return_value_control_needed |
| CAL-022 | stub candidate io-like | `WritePort(...)` | tag io_like |
| CAL-023 | json output | call_report.json | JSON parse可能 |
| CAL-024 | markdown output | call_report.md | expected sectionあり |
| CAL-025 | analyze-function integration | Step04+05+06+07+08+09 | call_report生成 |

### 9.3 テスト方針

- call expression scanner は小さなC断片で単体テストする
- argument splitter はネスト括弧を重点的にテストする
- return usage analyzer は周辺token単位でテストする
- target classifier は既知リスト、same-file関数、macro、externalを分けてテストする
- integration test では Step 05 source_digest、Step 06 function_location、Step 07 function_signature、Step 08 global_access fixture と接続する
- JSONは `json.loads()` で検証する
- Markdownは主要sectionの存在を検証する
- macro-like / function pointer / cast は false positive 防止を重視する

---

## 10. 実装タスク分解

### Task 09-01: Call model 定義

成果物:

- `src/unit_test_runner/c_analyzer/call_models.py`
- `CallAnalysisRequest`
- `CallReport`
- `FunctionCall`
- `CallArgument`
- `ReturnUsage`
- `StubCandidate`
- `CallSideEffectCandidate`
- `CallAnalyzerWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 09-02: Call expression scanner

成果物:

- `src/unit_test_runner/c_analyzer/call_scanner.py`
- `identifier + (` 候補抽出
- 対応 `)` 検出
- ネスト呼び出し対応

完了条件:

- CAL-001 / CAL-006 / CAL-019 が通る

### Task 09-03: Non-call filter

成果物:

- 制御構文除外
- sizeof除外
- cast除外
- preprocessor行除外

完了条件:

- CAL-017 / CAL-018 が通る

### Task 09-04: Argument splitter / analyzer

成果物:

- top-level comma split
- nested call対応
- identifier抽出
- argument_kind分類

完了条件:

- CAL-012 から CAL-016 が通る

### Task 09-05: Return usage analyzer

成果物:

- ignored / assigned / returned / condition / comparison / logical / argument_to_call判定

完了条件:

- CAL-001 から CAL-005 が通る

### Task 09-06: Call target classifier

成果物:

- same-file関数分類
- static関数分類
- standard library候補分類
- macro-like分類
- function pointer候補分類
- external分類

完了条件:

- CAL-007 から CAL-011 が通る

### Task 09-07: Side effect bridge

成果物:

- Step 08 global_access連携
- address argument副作用候補
- pointer/array parameter引数候補
- callback candidate候補

完了条件:

- CAL-013 から CAL-016 が通る

### Task 09-08: Stub candidate extractor

成果物:

- external call集約
- return value control判定
- argument capture判定
- side effect control判定
- name hint tag付与

完了条件:

- CAL-021 / CAL-022 が通る

### Task 09-09: Conditional context integration

成果物:

- Step 05 active_stateとの接続
- inactive / unknown warning
- confidence調整

完了条件:

- CAL-020 が通る

### Task 09-10: Call report writer

成果物:

- `src/unit_test_runner/c_analyzer/call_report_writer.py`
- `call_report.json`
- `reports/call_report_markdown.py`

完了条件:

- CAL-023 / CAL-024 が通る

### Task 09-11: analyze-function 接続

成果物:

- Step 04 source membership取得
- Step 05 source_digest生成
- Step 06 function_location生成
- Step 07 function_signature生成
- Step 08 global_access生成
- Step 09 call_report生成
- CLI `analyze-function` の出力更新

完了条件:

- CAL-025 が通る

### Task 09-12: fixture / test 整備

成果物:

- `tests/fixtures/c_sources/calls/...`
- `tests/unit/test_call_scanner.py`
- `tests/unit/test_call_argument_analyzer.py`
- `tests/unit/test_return_usage_analyzer.py`
- `tests/unit/test_call_target_classifier.py`
- `tests/unit/test_stub_candidate_extractor.py`
- `tests/unit/test_call_report_writer.py`
- `tests/unit/test_analyze_function_partial_calls.py`

完了条件:

- CAL-001 から CAL-025 が通る

---

## 11. 受け入れ基準

Step 09 は、以下をすべて満たしたら完了とする。

1. 関数本文内の関数呼び出し候補を抽出できる
2. 制御構文、sizeof、castを呼び出し候補から除外できる
3. ネストした呼び出しを抽出できる
4. 引数式をトップレベルcommaで分割できる
5. 引数式内のidentifierを分類できる
6. global / local / parameter / macro / unknown引数を分類できる
7. `&global` / `&local` / pointer parameter引数を副作用候補として保持できる
8. 戻り値無視、代入、return、条件式、比較式での利用を分類できる
9. same-file functionとsame-file static functionを分類できる
10. external function candidateを分類できる
11. standard library candidateを分類できる
12. macro-like call candidateを保守的に扱える
13. function pointer call candidateを保守的に扱える
14. external dependencyをstub candidateとして出力できる
15. 戻り値が使われるstub候補に `return_value_control_needed` を付与できる
16. 引数観測が必要なstub候補に `argument_capture_needed` を付与できる
17. pointer/global引数を持つstub候補に `side_effect_control_needed` を付与できる
18. hardware/time/ioらしき名前ヒントをtagとして付与できる
19. inactive / unknown conditional contextの呼び出し候補にwarningを付与できる
20. `call_report.json` を生成できる
21. `call_report.md` を生成できる
22. `analyze-function` が Step 09 時点では call analysis まで進み、Step 10 が必要である旨を返せる
23. Step 10 の Branch / Condition Analyzer に渡せる call site情報がある
24. スタブCコード生成へ踏み込みすぎていない
25. 分岐・条件解析へ踏み込みすぎていない

---

## 12. 成果物

Step 09 の成果物は以下とする。

```text
src/
  unit_test_runner/
    c_analyzer/
      call_models.py
      call_scanner.py
      call_argument_analyzer.py
      return_usage_analyzer.py
      call_target_classifier.py
      stub_candidate_extractor.py
      call_analyzer.py
      call_report_writer.py
    reports/
      call_report_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    c_sources/
      calls/
        simple_call.c
        nested_call.c
        return_value_assigned.c
        return_value_ignored.c
        call_in_condition.c
        call_in_return.c
        standard_library_call.c
        macro_like_call.c
        function_pointer_call.c
        same_file_static_call.c
        external_call.c
        address_argument.c
        global_argument.c
        pointer_parameter_argument.c
        malformed_call.c
        conditional_call.c
        cast_not_call.c
  unit/
    test_call_scanner.py
    test_call_argument_analyzer.py
    test_return_usage_analyzer.py
    test_call_target_classifier.py
    test_stub_candidate_extractor.py
    test_call_report_writer.py
    test_analyze_function_partial_calls.py
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/c_analyzer/tokens.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/function_locator.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/global_access_models.py` 必要な場合のみ

---

## 13. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| 呼び出しとcastの誤判定 | `(TYPE)(x)` と `Func(x)` が紛らわしい | 型名候補、前後token、identifier位置で保守的に除外する |
| macro-like call | macro展開しないと実関数か分からない | Step05 MacroDefinitionを参照し、macro_likeとしてwarning付きで保持する |
| 関数ポインタ呼び出し | `cb(x)` の実体が不明 | parameter/local分類とTypeInfoを使いfunction_pointer candidateにする |
| same-file判定不足 | 全関数一覧が未整備だと分類できない | Step06の全関数一覧optional機能を利用または補助scannerを実装する |
| 標準ライブラリ判定 | 独自関数名と衝突する可能性 | standard_libraryはcandidate扱いにしてconfidenceを持つ |
| スタブ候補過多 | external扱いしすぎると候補が多すぎる | target_kind、return usage、name hint、side effectで優先度を付ける |
| 戻り値利用の誤判定 | 完全なASTなしでは親文脈が難しい | 周辺tokenベースで分類し、不明はunknownにする |
| Step10責務の侵食 | if条件や分岐網羅まで解析したくなる | Step09はcall siteに限定し、分岐条件はStep10へ委譲する |
| スタブ生成への前倒し | stub candidateからコード生成したくなる | Step09では候補抽出のみ。生成は後続ステップへ分離する |

---

## 14. Step 10 への接続

Step 09 完了後、Step 10 では Branch / Condition Analyzer を実装する。
Step 10 は、Step 05 の token stream、Step 06 の function body range、Step 08 の変数アクセス、Step 09 の call sitesを使い、if / switch / loop / ternary / logical condition などから設計カバレッジ項目を抽出する。

想定接続:

```python
global_access = analyze_global_access(
    source_digest=source_digest,
    function_location=function_location,
    function_signature=function_signature,
)
call_report = analyze_calls(
    source_digest=source_digest,
    function_location=function_location,
    global_access=global_access,
)
branch_report = analyze_branches(
    source_digest=source_digest,
    function_location=function_location,
    global_access=global_access,
    call_report=call_report,
)
```

Step 10 で使う情報:

- function body range
- token stream
- identifier use
- global / parameter access
- call sites
- return usage
- conditional context
- stub candidates

Step 09 の責務は、Branch / Condition Analyzer が条件式内の呼び出し、戻り値利用、スタブ候補を考慮できるように、call site情報を整理することである。

---

## 15. まとめ

Step 09 は、対象関数内の呼び出し依存を整理するステップである。

このステップにより、対象関数がどの関数を呼び、どの呼び出しが外部依存で、どの呼び出しがスタブ候補で、どの引数や戻り値がテスト設計上重要なのかを `call_report` として整理できる。

ただし、Step 09 はスタブコード生成や分岐・条件網羅の生成を行う段階ではない。
呼び出し候補、戻り値利用、引数副作用候補、スタブ候補に責務を絞り、Step 10 の Branch / Condition Analyzer へ安全な入力を渡すことを完了条件とする。

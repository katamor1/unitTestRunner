# Step 06: Function Locator 実装計画

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

---

## 1. 位置づけ

本書は、`unitTestRunner` の第6ステップとして **Function Locator** を実装するための計画である。

Step 05 では、Cソースを読み込み、コメント・文字列・文字定数をマスクし、プリプロセッサ情報と token stream の下地を作る計画を定義した。
Step 06 では、その `masked_text` と token stream を使って、ユーザーが指定した関数の **定義位置と関数本文の範囲** を特定する。

Step 06 は、関数の詳細なシグネチャ解析そのものではない。
戻り値型、引数型、引数名、ポインタ種別などの詳細解析は Step 07 で行う。

Step 06 の主な責務は以下である。

- 指定関数名を `.c` ファイル内から探す
- 宣言・プロトタイプ・関数ポインタ・関数呼び出しと、関数定義を区別する
- 関数定義の開始行、終了行を特定する
- 関数ヘッダ範囲、関数本文範囲を特定する
- 波括弧対応により本文終端を特定する
- `static` 関数を含めて検出する
- 条件コンパイル内の関数定義を検出し、active_state を付与する
- 同名候補が複数ある場合に曖昧性を報告する
- Step 07 の Signature Extractor に渡せる function slice を作る

---

## 2. 目的

Step 06 の目的は、関数単位テストの入口となる **対象関数の範囲特定** を安定して行うことである。

具体的には、以下を実現する。

- `Control_Update` のような関数名を指定して定義を探せる
- コメントや文字列内の関数名を誤検出しない
- 関数呼び出しを関数定義と誤検出しない
- プロトタイプ宣言を関数定義と誤検出しない
- `if` / `while` / `switch` などの制御構文を関数定義と誤検出しない
- 関数ポインタ宣言を関数定義と誤検出しない
- function-like macro を関数定義と誤検出しない
- K&R 風の旧式関数定義を候補として扱える
- 波括弧の対応を取り、関数本文の終了位置を得られる
- 元ソースの行番号・列番号で report できる
- `function_location.json` / `function_location.md` を出力できる
- `analyze-function` を Step 06 時点で「対象関数の位置特定まで」進められる

---

## 3. スコープ

### 3.1 実装対象

Step 06 で実装するもの:

1. Function candidate scanner
   - token stream から関数定義候補を抽出
   - 指定関数名による検索
   - 全関数一覧の抽出 optional

2. Definition classifier
   - definition
   - prototype
   - function call
   - function pointer declaration
   - macro-like candidate
   - unknown

3. Function range detector
   - header start / end
   - body start / end
   - opening brace / closing brace
   - line / column / offset

4. Brace matcher
   - `{` / `}` の対応
   - nested block 対応
   - unmatched brace warning

5. Conditional context resolver
   - Step 05 の `PreprocessorDirective` / active_state を参照
   - 関数定義が条件コンパイル内にあるか記録

6. Reports
   - `function_location.json`
   - `function_location.md`
   - `function_slice.c` optional output

7. CLI 接続
   - `analyze-function` を function location まで進める
   - status `partial` または `ok_for_location` を返す
   - Step 07 が必要である旨を message に含める

8. Tests
   - 通常関数
   - static 関数
   - multi-line header
   - prototype
   - function call
   - function pointer
   - K&R style
   - nested brace
   - comment/string 内の関数名
   - conditional compilation
   - duplicate candidate
   - malformed brace

### 3.2 対象外

Step 06 では以下を対象外とする。

- 戻り値型の詳細解析
- 引数型・引数名の詳細解析
- ポインタ引数・配列引数の分類
- グローバル変数アクセス解析
- 外部呼び出し解析
- 分岐・条件網羅候補生成
- 境界値・同値クラス候補生成
- テストハーネス生成
- スタブ生成
- macro 展開
- include ファイルをまたいだ関数定義探索
- C++ member function の本格対応

Step 06 では、対象 `.c` ファイル内にある C 関数定義の範囲特定に限定する。

---

## 4. 入力と出力

### 4.1 入力

主入力:

- 対象 `.c` ファイルパス
- Step 04 の `build_context`
- Step 05 の `source_digest`
- Step 05 の `masked_text`
- Step 05 の token stream
- 対象関数名

入力イメージ:

```json
{
  "source": "D:/work/product/src/control.c",
  "function": "Control_Update",
  "build_context": "reports/build_context.json",
  "source_digest": "reports/source_digest.json",
  "masked_source": "intermediate/masked_source.c"
}
```

### 4.2 出力

Step 06 の主要出力は `function_location` である。

```text
workspace/
  Control_Update/
    reports/
      source_digest.json
      function_location.json
      function_location.md
    intermediate/
      masked_source.c
      function_slice.c
```

`function_location.json` は Step 07 の Signature Extractor への入力になる。

---

## 5. データモデル設計

### 5.1 FunctionLocateRequest

```python
@dataclass
class FunctionLocateRequest:
    source_path: Path
    function_name: str
    build_context_path: Path | None
    source_digest_path: Path | None
    masked_text: str | None
    tokens: list[LexToken]
```

役割:

- Function Locator の入力条件をまとめる
- CLI / internal usecase の境界を明確にする

### 5.2 FunctionLocation

```python
@dataclass
class FunctionLocation:
    function_name: str
    source_path: Path
    status: str
    selected_candidate: FunctionCandidate | None
    candidates: list[FunctionCandidate]
    warnings: list[FunctionLocatorWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `found` | 一意に定義を特定できた |
| `not_found` | 指定関数が見つからない |
| `multiple_candidates` | 同名の定義候補が複数ある |
| `ambiguous` | 定義らしいが判定が曖昧 |
| `malformed` | 波括弧などが壊れており範囲確定できない |

### 5.3 FunctionCandidate

```python
@dataclass
class FunctionCandidate:
    name: str
    kind: str
    confidence: str
    header_range: SourceRange
    body_range: SourceRange | None
    full_range: SourceRange
    opening_brace: SourcePosition | None
    closing_brace: SourcePosition | None
    storage_class_hint: str | None
    conditional_context: ConditionalContext | None
    signature_preview: str
    reason: str
```

`kind` 候補:

| kind | 内容 |
|---|---|
| `definition` | 関数定義 |
| `prototype` | 関数プロトタイプ |
| `call` | 関数呼び出し |
| `function_pointer` | 関数ポインタ宣言 |
| `macro_like` | macro 由来らしい候補 |
| `unknown` | 判定不能 |

`confidence` 候補:

- `high`
- `medium`
- `low`

### 5.4 SourceRange / SourcePosition

```python
@dataclass
class SourcePosition:
    line: int
    column: int
    offset: int
```

```python
@dataclass
class SourceRange:
    start: SourcePosition
    end: SourcePosition
```

役割:

- 元ソース上の範囲を表す
- Markdown report や function slice 生成に使う

### 5.5 ConditionalContext

```python
@dataclass
class ConditionalContext:
    active_state: str
    nesting_level: int
    directives: list[PreprocessorDirective]
```

役割:

- 関数定義が `#ifdef` などの条件下にある場合に記録する
- Step 07 以降で解析対象に含めるかレビュー判断できるようにする

### 5.6 FunctionLocatorWarning

```python
@dataclass
class FunctionLocatorWarning:
    code: str
    message: str
    line_number: int | None = None
    column: int | None = None
    text: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `function_not_found` | 指定関数が見つからない |
| `multiple_function_definitions` | 同名定義候補が複数ある |
| `prototype_only` | プロトタイプのみ見つかった |
| `candidate_in_inactive_region` | inactive と推定される条件コンパイル内にある |
| `unknown_active_state` | 条件コンパイルの有効性が不明 |
| `unmatched_opening_brace` | `{` に対応する `}` が見つからない |
| `unexpected_closing_brace` | 余分な `}` を検出した |
| `function_pointer_candidate_ignored` | 関数ポインタ候補を除外した |
| `macro_like_candidate_ignored` | macro風候補を除外した |
| `old_style_definition_detected` | K&R style らしき定義を検出した |
| `signature_too_complex` | header範囲の判定が難しい |

---

## 6. Function Locator 設計

### 6.1 基本アルゴリズム

Step 05 の token stream と masked_text を使う。
コメントや文字列は既に mask されているため、`{` / `}` の対応を取りやすい。

処理フロー:

```text
locate_function(request)
  1. source_digest を読み込む、または生成済み objects を受け取る
  2. token stream を取得する
  3. function_name と一致する identifier token を探す
  4. 直後の token が `(` か確認する
  5. 対応する `)` を探す
  6. 候補の前後 token を見て分類する
  7. `)` の後に `{` があれば definition とする
  8. `)` の後に `;` があれば prototype とする
  9. K&R style の場合は `)` と `{` の間の宣言列を許容する
 10. `{` から対応する `}` を探す
 11. header start を推定する
 12. full range / body range を作る
 13. conditional context を付与する
 14. 候補が1つなら selected_candidate にする
 15. 複数なら multiple_candidates として返す
```

### 6.2 definition 判定の基本形

対象:

```c
int Control_Update(int mode, int sensor)
{
    return 0;
}
```

判定:

- `Control_Update` が identifier
- 直後に `(`
- 対応する `)` がある
- `)` の後、空白・改行・preprocessor line を除いた次の有効 token が `{`
- `{` に対応する `}` がある

この場合、`kind=definition`、`confidence=high` とする。

### 6.3 prototype 判定

対象:

```c
int Control_Update(int mode, int sensor);
```

判定:

- `Control_Update` が identifier
- 直後に `(`
- 対応する `)` がある
- `)` の後の有効 token が `;`

この場合、`kind=prototype` として候補に残すが、selected definition にはしない。
指定関数について prototype のみ見つかった場合は `status=not_found` または `prototype_only` warning を返す。

### 6.4 function call 判定

対象:

```c
ret = Control_Update(mode, sensor);
```

判定:

- `Control_Update` が identifier
- 直後に `(`
- 対応する `)` の後が `;` などでも、候補の前に代入演算子や式文脈がある
- header start の候補として戻り値型らしい token 列がない
- file scope ではなく関数本文内にある

この場合、`kind=call` として除外する。

補足:

- Step 06 では完全なスコープ解析はしない
- ただし token の brace depth を使い、top-level 以外の候補は call である可能性を高く見る
- Cでは関数定義は top-level にしか出ないため、brace depth 0 以外の `name(` は definition ではない

### 6.5 function pointer 判定

対象:

```c
int (*Control_Update)(int mode, int sensor);
```

または:

```c
void RegisterCallback(int (*Control_Update)(int));
```

判定ヒント:

- 関数名の直前または近傍に `*` と `(` がある
- `(* name ) (` の形がある
- `)` の後に `;` または `,` がある

この場合、`kind=function_pointer` として除外する。

### 6.6 K&R style 旧式定義

C90 / 古いコードでは以下があり得る。

```c
int Control_Update(mode, sensor)
int mode;
int sensor;
{
    return 0;
}
```

判定方針:

- `name (` と対応する `)` を見つける
- `)` の直後が `{` でなくても、次の `{` までに C 宣言らしい行が並ぶ場合は旧式定義候補とする
- `)` から `{` までに `;` が複数出ることを許容する
- `=` や実行文らしき token が出る場合は confidence を下げる
- warning `old_style_definition_detected` を付与する
- `kind=definition`, `confidence=medium` とする

### 6.7 static 関数

対象:

```c
static int Control_Update(int mode)
{
    return 0;
}
```

判定方針:

- header start 推定時に `static` が含まれていれば `storage_class_hint=static`
- static であっても通常の関数定義として扱う

### 6.8 multi-line header

対象:

```c
int
Control_Update(
    int mode,
    int sensor
)
{
    return 0;
}
```

判定方針:

- token stream で `identifier` と `(` の対応を見るため、改行に依存しない
- header start は前方へ戻って推定する
- signature_preview は元ソース行から構成する

### 6.9 macro-like candidate

対象:

```c
#define Control_Update(x) ((x) + 1)
```

または:

```c
DECLARE_HANDLER(Control_Update)
```

判定方針:

- Step 05 の MacroDefinition に同名 function-like macro があれば macro_like として警告する
- preprocessor directive 行上の候補は definition としない
- 大文字 macro 呼び出し内の候補は low confidence とする

---

## 7. Brace Matching 設計

### 7.1 目的

関数本文の終了位置を特定するため、opening brace `{` から対応する closing brace `}` を探す。

### 7.2 方針

- Step 05 の masked_text / token stream を使用する
- コメント・文字列内の `{` / `}` は既にmask済みのため対象外
- `{` で depth +1
- `}` で depth -1
- opening brace の depth が 0 に戻った位置を closing brace とする
- EOFまで戻らなければ warning `unmatched_opening_brace`
- openingなしの `}` は warning `unexpected_closing_brace`

### 7.3 top-level depth

関数定義候補は原則として top-level depth 0 に出る。

方針:

- token stream 全体に brace_depth を注釈できるなら行う
- `name(` が brace_depth 0 でなければ definition 候補から除外する
- ただし malformed source では brace_depth が壊れるため warning とする

---

## 8. Header Range 推定

### 8.1 header_start の推定

Step 06 ではシグネチャ詳細解析はしないが、Step 07 の入力として関数ヘッダ範囲が必要である。

推定方針:

- 関数名 token から前方へ戻る
- 直前の top-level `;`、`}`、preprocessor directive、またはファイル先頭の次を header_start 候補にする
- 空行やコメントは元ソース上では含めてもよいが、previewでは整形する
- `static`、`extern`、戻り値型、改行を含む header を含める

### 8.2 header_end の推定

- 通常定義では opening brace `{` の直前を header_end とする
- K&R style では opening brace 直前までの旧式引数宣言を含める
- `signature_preview` は header range から最大数行を切り出す

### 8.3 制約

header range は Step 07 の入力であり、完全な型解析結果ではない。
Step 06 では、header範囲を少し広めに取ることを許容する。

---

## 9. Conditional Context 設計

### 9.1 active_state 付与

Step 05 の `PreprocessorDirective` と active_state を利用し、関数定義の開始行がどの条件コンパイル範囲にあるかを推定する。

方針:

- 関数開始行より前の conditional directive stack を参照する
- 最内側の active_state を優先する
- 複数条件がある場合、1つでも inactive があれば inactive候補
- unknown を含む場合は unknown とする

### 9.2 inactive 関数の扱い

inactive と推定される関数定義が見つかった場合:

- candidate としては保持する
- selected_candidate にするかは設定次第
- 既定では warning `candidate_in_inactive_region` を付ける
- 同名の active candidate があれば active を優先する
- active candidate がなく inactive のみなら `found` ではなく `ambiguous` または `found_in_inactive_region` 相当を検討する

Step 06 では status enum を増やしすぎず、`found` + warning または `ambiguous` として扱う。

---

## 10. CLI 接続設計

### 10.1 analyze-function の Step 06 接続

Step 06 では、`analyze-function` を対象関数の位置特定まで進める。

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
3. Step 06 の Function Locator を実行する
4. `function_location.json` を生成する
5. `function_location.md` を生成する
6. optionalで `function_slice.c` を生成する
7. Step 07 の Signature Extractor が必要であることを message に含める
8. 関数が見つかれば status `partial` または `located` を返す

### 10.2 locate-function コマンド案

開発・debug 用に以下の独立コマンドを検討する。

```bat
unit-test-runner locate-function ^
  --source D:\work\product\src\control.c ^
  --function Control_Update ^
  --source-digest D:\work\unit_test_workspace\Control_Update\reports\source_digest.json ^
  --out D:\work\unit_test_workspace\Control_Update\reports\function_location.json
```

扱い:

- 公開コマンドにするかは実装時判断とする
- Step 06 計画では必須ではない
- 必須なのは internal usecase と `analyze-function` 接続である

---

## 11. Report 設計

### 11.1 function_location.json

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
    "status": "found",
    "selected_candidate": {
      "kind": "definition",
      "confidence": "high",
      "storage_class_hint": "static",
      "header_range": {
        "start": {"line": 120, "column": 1, "offset": 3200},
        "end": {"line": 124, "column": 1, "offset": 3340}
      },
      "body_range": {
        "start": {"line": 124, "column": 1, "offset": 3340},
        "end": {"line": 180, "column": 1, "offset": 5200}
      },
      "signature_preview": "static int Control_Update(int mode, int sensor)",
      "conditional_context": {
        "active_state": "active",
        "nesting_level": 0
      }
    },
    "candidate_count": 1
  },
  "warnings": []
}
```

### 11.2 function_location.md

内容例:

```markdown
# Function Location Report

## Target

- Source: D:/work/product/src/control.c
- Function: Control_Update
- Status: found

## Selected Candidate

| Item | Value |
|---|---|
| Kind | definition |
| Confidence | high |
| Storage | static |
| Header Start | line 120, column 1 |
| Body Start | line 124, column 1 |
| Body End | line 180, column 1 |
| Active State | active |

## Signature Preview

```c
static int Control_Update(int mode, int sensor)
```

## Warnings

なし
```

### 11.3 function_slice.c

`function_slice.c` は中間生成物であり、本番コードではない。

用途:

- 対象関数の範囲確認
- CODEX / 開発者による debug
- Step 07 の signature extractor fixture

注意:

- function slice はビルド対象ではない
- 本番リポジトリへ出力しない
- 外部ワークスペース配下にのみ生成する

---

## 12. テスト計画

### 12.1 fixture 構成

```text
tests/
  fixtures/
    c_sources/
      functions/
        simple_function.c
        static_function.c
        multiline_header.c
        prototype_only.c
        function_call.c
        function_pointer.c
        old_style_definition.c
        nested_braces.c
        duplicate_name_conditional.c
        inactive_function.c
        malformed_unmatched_brace.c
        macro_like_function.c
        comment_string_noise.c
```

### 12.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| LOC-001 | simple function | `int f(void) {}` | definition found |
| LOC-002 | static function | `static int f(void) {}` | storage_class_hint static |
| LOC-003 | multiline header | header複数行 | rangeを特定 |
| LOC-004 | prototype only | `int f(void);` | prototype_only warning |
| LOC-005 | function call | `f();` | callをdefinitionにしない |
| LOC-006 | control keyword | `if (...)` | 関数候補にしない |
| LOC-007 | function pointer | `int (*f)(void);` | function_pointerとして除外 |
| LOC-008 | old style | K&R style | definition medium confidence |
| LOC-009 | nested braces | if/switch内block | closing braceを正しく検出 |
| LOC-010 | comment noise | コメント内 `f(){}` | 誤検出しない |
| LOC-011 | string noise | 文字列内 `f(){}` | 誤検出しない |
| LOC-012 | inactive function | `#if 0`内 | inactive warning |
| LOC-013 | unknown active | 複雑な#if内 | unknown_active_state warning |
| LOC-014 | duplicate candidates | 同名複数 | multiple_candidates |
| LOC-015 | unmatched brace | `{` 未close | malformed warning |
| LOC-016 | macro-like | `#define f(x)` | macro_like除外 |
| LOC-017 | target not found | なし | not_found |
| LOC-018 | analyze-function integration | Step04+05+06 | function_location生成 |
| LOC-019 | json output | analyze-function --json | stdout JSONのみ |
| LOC-020 | function_slice | located function | function_slice.c生成 |

### 12.3 テスト方針

- Function Locator 単体テストでは Step 05 の masker/tokenizer を組み合わせる
- classifier は小さな token sequence でもテストする
- brace matcher は独立してテストする
- integration test では Step 04 build_context、Step 05 source_digest と接続する
- JSONは `json.loads()` で検証する
- 行番号・列番号は明示assertで検証する
- K&R style は high confidence にしすぎず medium として検証する

---

## 13. 実装タスク分解

### Task 06-01: Function locator model 定義

成果物:

- `src/unit_test_runner/c_analyzer/function_models.py`
- `FunctionLocateRequest`
- `FunctionLocation`
- `FunctionCandidate`
- `SourceRange`
- `SourcePosition`
- `ConditionalContext`
- `FunctionLocatorWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 06-02: Brace matcher

成果物:

- `src/unit_test_runner/c_analyzer/brace_matcher.py`
- opening / closing brace 対応
- brace_depth annotation helper
- unmatched warning

完了条件:

- LOC-009 / LOC-015 が通る

### Task 06-03: Candidate scanner

成果物:

- `src/unit_test_runner/c_analyzer/function_locator.py`
- target function name検索
- `identifier + (` 候補抽出
- top-level depth 判定

完了条件:

- LOC-001 / LOC-003 / LOC-017 が通る

### Task 06-04: Definition classifier

成果物:

- definition / prototype / call / function_pointer / macro_like 分類
- control keyword 除外
- Step 05 MacroDefinition 連携

完了条件:

- LOC-004 から LOC-007、LOC-016 が通る

### Task 06-05: K&R style handling

成果物:

- `)` と `{` の間の旧式引数宣言候補を許容
- warning `old_style_definition_detected`
- confidence medium

完了条件:

- LOC-008 が通る

### Task 06-06: Function range detector

成果物:

- header_range 推定
- body_range 推定
- full_range 推定
- signature_preview 生成

完了条件:

- LOC-001 / LOC-002 / LOC-003 / LOC-009 が通る

### Task 06-07: Conditional context resolver

成果物:

- Step 05 directive情報との接続
- active / inactive / unknown context付与
- inactive warning

完了条件:

- LOC-012 / LOC-013 が通る

### Task 06-08: Function location writer

成果物:

- `src/unit_test_runner/c_analyzer/function_location_writer.py`
- `function_location.json`
- `reports/function_location_markdown.py`
- optional `function_slice.c`

完了条件:

- LOC-020 が通る

### Task 06-09: analyze-function 接続

成果物:

- Step 04 source membership取得
- Step 05 source_digest生成
- Step 06 function location生成
- CLI `analyze-function` の出力更新

完了条件:

- LOC-018 / LOC-019 が通る

### Task 06-10: fixture / test 整備

成果物:

- `tests/fixtures/c_sources/functions/...`
- `tests/unit/test_brace_matcher.py`
- `tests/unit/test_function_locator.py`
- `tests/unit/test_function_classifier.py`
- `tests/unit/test_function_location_writer.py`
- `tests/unit/test_analyze_function_partial_location.py`

完了条件:

- LOC-001 から LOC-020 が通る

---

## 14. 受け入れ基準

Step 06 は、以下をすべて満たしたら完了とする。

1. 指定関数名から関数定義候補を抽出できる
2. コメント・文字列内の関数名を誤検出しない
3. 関数呼び出しを関数定義として扱わない
4. プロトタイプを関数定義として扱わない
5. 関数ポインタ宣言を関数定義として扱わない
6. control keyword を関数候補として扱わない
7. `static` 関数を検出できる
8. multi-line header の関数を検出できる
9. K&R style 関数定義を medium confidence で検出できる
10. opening brace から closing brace までの関数本文範囲を特定できる
11. unmatched brace を warning として返せる
12. header_range / body_range / full_range を出力できる
13. signature_preview を出力できる
14. 条件コンパイル内の関数に active_state を付与できる
15. inactive / unknown active state を warning として返せる
16. 同名候補が複数ある場合に multiple_candidates として返せる
17. `function_location.json` を生成できる
18. `function_location.md` を生成できる
19. optionalで `function_slice.c` を生成できる
20. `analyze-function` が Step 06 時点では function location まで進み、Step 07 が必要である旨を返せる
21. Step 07 の Signature Extractor に渡せる function slice / header range がある
22. シグネチャ詳細解析へ踏み込みすぎていない

---

## 15. 成果物

Step 06 の成果物は以下とする。

```text
src/
  unit_test_runner/
    c_analyzer/
      function_models.py
      brace_matcher.py
      function_locator.py
      function_location_writer.py
    reports/
      function_location_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    c_sources/
      functions/
        simple_function.c
        static_function.c
        multiline_header.c
        prototype_only.c
        function_call.c
        function_pointer.c
        old_style_definition.c
        nested_braces.c
        duplicate_name_conditional.c
        inactive_function.c
        malformed_unmatched_brace.c
        macro_like_function.c
        comment_string_noise.c
  unit/
    test_brace_matcher.py
    test_function_locator.py
    test_function_classifier.py
    test_function_location_writer.py
    test_analyze_function_partial_location.py
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/c_analyzer/source_digest.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/tokens.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/preprocessor.py` 必要な場合のみ

---

## 16. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| 関数定義と呼び出しの誤判定 | `name(` は多くの文脈で出る | top-level brace depth、後続 `{`、前後tokenで分類する |
| プロトタイプ誤認 | `int f(void);` をdefinition扱いする | `)` 後の `;` を明確に prototype とする |
| 関数ポインタ誤認 | `int (*f)(void)` をdefinition扱いする | `(* name ) (` pattern を検出し除外する |
| K&R style | 古いC定義で `)` 直後に `{` が来ない | 旧式引数宣言候補を medium confidence で許容する |
| macroとの混同 | `#define f(x)` や `DECLARE(f)` | Step 05 MacroDefinition と preprocessor行情報を使い除外する |
| 条件コンパイル | inactive領域の関数を誤って選ぶ | active_stateを付け、active候補を優先する |
| brace不整合 | 壊れたソースや条件コンパイルで対応が崩れる | malformed status / warning を返し、partial情報を残す |
| header_rangeの過不足 | 戻り値型や修飾子の範囲推定が難しい | Step 06では広めに取り、詳細はStep 07に委譲する |
| C++混在 | `.cpp` や member function が混ざる | Step 06は `.c` 主対象。C++は warning または low confidence とする |

---

## 17. Step 07 への接続

Step 06 完了後、Step 07 では Signature Extractor を実装する。
Step 07 は、Step 06 の `header_range` と `signature_preview` を使って、戻り値型、引数型、引数名、ポインタ、配列、const、構造体型などを抽出する。

想定接続:

```python
function_location = locate_function(source_digest, function_name="Control_Update")
selected = function_location.selected_candidate
signature = extract_signature(
    original_text=source_digest.source.text,
    header_range=selected.header_range,
    function_name=selected.name,
)
```

Step 07 で使う情報:

- header_range
- signature_preview
- source original text
- masked_text
- token stream
- function-like macro一覧
- conditional context

Step 06 の責務は、Signature Extractor が解析すべき範囲を安全に切り出すことである。

---

## 18. まとめ

Step 06 は、関数単位テスト支援の中心に入る最初のステップであり、指定関数の定義範囲を特定する。

このステップにより、対象 `.c` 内で指定関数がどこにあり、どこからどこまでが関数本文なのかを、元ソースの行番号付きで把握できるようになる。

ただし、Step 06 ではシグネチャ詳細解析やグローバル変数解析には進まない。
範囲特定に責務を絞り、Step 07 の Signature Extractor へ安全な `header_range` と `function_slice` を渡すことを完了条件とする。

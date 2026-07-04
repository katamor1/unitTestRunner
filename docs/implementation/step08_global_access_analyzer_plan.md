# Step 08: Global Access Analyzer 実装計画

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

---

## 1. 位置づけ

本書は、`unitTestRunner` の第8ステップとして **Global Access Analyzer** を実装するための計画である。

Step 07 では、対象関数の戻り値型、引数、ポインタ、配列、const、呼び出し規約などを `function_signature` として抽出する計画を定義した。
Step 08 では、Step 06 で特定した関数本文範囲と、Step 07 で得た関数シグネチャを使い、対象関数が参照・更新する **グローバル変数候補、file scope static変数、extern変数、引数経由の副作用候補** を抽出する。

Step 08 は、関数本文のデータアクセスを整理する段階である。
ただし、外部関数呼び出しの詳細解析は Step 09、分岐・条件解析は Step 10 以降で扱う。

Step 08 の主な責務は以下である。

- file scope の変数宣言候補を抽出する
- `static` file scope 変数を抽出する
- `extern` 変数宣言候補を抽出する
- 関数本文内のローカル変数宣言を抽出する
- 引数、ローカル変数、グローバル変数候補を区別する
- グローバル変数の read / write / read_write / address_taken 候補を抽出する
- 配列アクセス、構造体メンバアクセス、ポインタ経由アクセスを保守的に扱う
- 非const pointer引数や配列引数を副作用候補として扱う
- 解析不能箇所を warning として保持する
- `global_access.json` / `global_access.md` を生成する
- Step 09 の Call Analyzer に渡せる本文内識別子・副作用候補情報を整理する

---

## 2. 目的

Step 08 の目的は、関数単位テスト設計に必要な **状態入出力情報** を安定して抽出することである。

具体的には、以下を実現する。

- 対象関数が読むグローバル変数候補を一覧化できる
- 対象関数が書くグローバル変数候補を一覧化できる
- file scope static変数とextern変数候補を区別できる
- 関数内ローカル変数を抽出し、グローバル変数候補から除外できる
- 引数とローカル変数とグローバル変数らしき識別子を区別できる
- 代入左辺、インクリメント、デクリメント、複合代入を write または read_write として検出できる
- 条件式、return式、関数引数として使われる識別子を read 候補として検出できる
- `&global` のようなアドレス取得を address_taken として検出できる
- `global.member`、`global->member`、`global[index]` をアクセスパス付きで記録できる
- `*p = value` や `p->field = value` のようなポインタ経由副作用を unknown side effect として保持できる
- pointer / array 引数に対する書き込み候補を parameter side effect として抽出できる
- `global_access.json` / `global_access.md` を出力できる
- `analyze-function` を Step 08 時点で「シグネチャ抽出 + グローバルアクセス候補抽出」まで進められる

---

## 3. スコープ

### 3.1 実装対象

Step 08 で実装するもの:

1. File scope declaration scanner
   - file scope variable definition候補
   - file scope static変数候補
   - extern変数宣言候補
   - 配列・ポインタ・構造体変数の粗分類
   - function prototype / function definition の除外

2. Local declaration scanner
   - 関数本文内のローカル変数宣言候補
   - block scope変数候補
   - for文初期化部の宣言候補
   - static local変数候補

3. Identifier use analyzer
   - 関数本文内の識別子利用箇所抽出
   - パラメータ利用
   - ローカル変数利用
   - グローバル変数候補利用
   - 未分類識別子

4. Access classifier
   - read
   - write
   - read_write
   - address_taken
   - passed_to_call
   - unknown

5. Assignment / mutation detector
   - `=`
   - `+=` / `-=` / `*=` / `/=` / `%=` / `&=` / `|=` / `^=` / `<<=` / `>>=`
   - `++` / `--`
   - array element assignment
   - struct member assignment
   - pointer dereference assignment

6. Parameter side effect detector
   - 非const pointer引数
   - array引数
   - `*param = ...`
   - `param[index] = ...`
   - `param->field = ...`
   - `&param` / `param` を外部関数へ渡す箇所は Step 09 と連携できるよう候補保持

7. Reports
   - `global_access.json`
   - `global_access.md`

8. CLI 接続
   - `analyze-function` を global access 抽出まで進める
   - status `partial` または `global_access_analyzed` を返す
   - Step 09 の Call Analyzer が必要である旨を message に含める

9. Tests
   - simple global read
   - global write
   - compound assignment
   - increment / decrement
   - file static
   - extern
   - local shadowing
   - parameter access
   - pointer parameter side effect
   - array parameter side effect
   - struct member access
   - pointer unknown side effect
   - macro-like identifier
   - conditional region

### 3.2 対象外

Step 08 では以下を対象外とする。

- 外部関数呼び出しの詳細解析
- 呼び出し回数期待値の抽出
- スタブ候補生成の詳細化
- 分岐・条件網羅候補生成
- 境界値・同値クラス候補生成
- typedef / struct / union / enum の完全解決
- includeファイルを再帰的に解析したextern変数収集
- macro展開後の変数アクセス解析
- ポインタ解析の完全実装
- alias解析の完全実装
- データフロー解析の完全実装
- テストハーネス生成

Step 08 では、関数本文から読み取れる変数アクセス候補を保守的に抽出することに限定する。

---

## 4. 入力と出力

### 4.1 入力

主入力:

- Step 04 の `build_context`
- Step 05 の `source_digest`
- Step 06 の `function_location`
- Step 07 の `function_signature`
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
  "function_signature": "reports/function_signature.json"
}
```

### 4.2 出力

Step 08 の主要出力は `global_access` である。

```text
workspace/
  Control_Update/
    reports/
      source_digest.json
      function_location.json
      function_signature.json
      global_access.json
      global_access.md
    intermediate/
      masked_source.c
      function_slice.c
```

`global_access.json` は Step 09 以降の入力になる。

---

## 5. データモデル設計

### 5.1 GlobalAccessRequest

```python
@dataclass
class GlobalAccessRequest:
    source_path: Path
    source_text: str
    masked_text: str
    tokens: list[LexToken]
    function_location: FunctionLocation
    function_signature: FunctionSignature
```

役割:

- Global Access Analyzer の入力条件をまとめる
- CLI / internal usecase の境界を明確にする

### 5.2 GlobalAccessReport

```python
@dataclass
class GlobalAccessReport:
    source_path: Path
    function_name: str
    status: str
    file_scope_declarations: list[VariableDeclaration]
    local_declarations: list[VariableDeclaration]
    parameter_accesses: list[ParameterAccess]
    global_accesses: list[VariableAccess]
    unresolved_identifiers: list[IdentifierUse]
    side_effect_candidates: list[SideEffectCandidate]
    warnings: list[GlobalAccessWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `analyzed` | 候補抽出が完了した |
| `partial` | 一部不明だが主要候補は抽出した |
| `ambiguous` | ローカル/グローバル判定が曖昧 |
| `malformed` | token範囲やbraceが壊れて解析不能 |

### 5.3 VariableDeclaration

```python
@dataclass
class VariableDeclaration:
    name: str
    scope: str
    storage_class: str | None
    type_raw: str
    type_hint: TypeInfo | None
    declaration_range: SourceRange
    initializer_range: SourceRange | None
    is_array: bool
    is_pointer: bool
    is_struct_like: bool
    confidence: str
    raw: str
```

`scope` 候補:

| scope | 意味 |
|---|---|
| `file` | file scope変数 |
| `file_static` | file scope static変数 |
| `extern` | extern宣言 |
| `local` | 関数内ローカル変数 |
| `local_static` | 関数内static変数 |
| `parameter` | 関数引数 |
| `unknown` | 判定不能 |

### 5.4 IdentifierUse

```python
@dataclass
class IdentifierUse:
    name: str
    position: SourcePosition
    context: str
    token_index: int
    resolved_as: str
    confidence: str
```

`resolved_as` 候補:

- `parameter`
- `local`
- `global_candidate`
- `file_static_candidate`
- `extern_candidate`
- `function_name`
- `macro`
- `type_name_candidate`
- `unknown`

### 5.5 VariableAccess

```python
@dataclass
class VariableAccess:
    name: str
    access_kind: str
    scope: str
    position: SourcePosition
    expression_range: SourceRange
    access_path: str | None
    operator: str | None
    confidence: str
    evidence: str
    related_declaration: VariableDeclaration | None
```

`access_kind` 候補:

| access_kind | 意味 |
|---|---|
| `read` | 値を読む |
| `write` | 値を書く |
| `read_write` | 読み書きする |
| `address_taken` | アドレスを取る |
| `passed_to_call` | 関数呼び出しに渡す |
| `unknown` | 判定不能 |

`access_path` 例:

- `g_state`
- `g_state.mode`
- `g_state->mode`
- `g_table[index]`
- `(*g_ptr)`

### 5.6 ParameterAccess

```python
@dataclass
class ParameterAccess:
    parameter_name: str
    access_kind: str
    position: SourcePosition
    expression_range: SourceRange
    access_path: str | None
    direction_hint_before_body: str
    body_access_hint: str
    confidence: str
    evidence: str
```

`body_access_hint` 候補:

| body_access_hint | 意味 |
|---|---|
| `read` | 引数値を読む |
| `write_candidate` | 引数先へ書く候補 |
| `read_write_candidate` | 読み書き候補 |
| `address_taken` | アドレスを取る |
| `passed_to_call` | 外部関数へ渡す |
| `unknown` | 判定不能 |

### 5.7 SideEffectCandidate

```python
@dataclass
class SideEffectCandidate:
    kind: str
    name: str | None
    position: SourcePosition
    expression_range: SourceRange
    reason: str
    confidence: str
    evidence: str
```

`kind` 候補:

| kind | 意味 |
|---|---|
| `global_write` | グローバル変数書き込み候補 |
| `file_static_write` | file static変数書き込み候補 |
| `extern_write` | extern変数書き込み候補 |
| `parameter_write` | pointer/array引数先書き込み候補 |
| `pointer_dereference_write` | ポインタ経由書き込み候補 |
| `address_escape` | アドレスが外へ渡る候補 |
| `unknown` | 不明な副作用候補 |

### 5.8 GlobalAccessWarning

```python
@dataclass
class GlobalAccessWarning:
    code: str
    message: str
    line_number: int | None = None
    column: int | None = None
    text: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `global_declaration_parse_failed` | file scope宣言の解析失敗 |
| `local_declaration_parse_failed` | local宣言の解析失敗 |
| `identifier_unresolved` | 識別子分類不能 |
| `local_shadows_global` | local変数がglobal候補と同名 |
| `macro_access_ignored` | macro由来のアクセスを除外した |
| `pointer_write_unknown_target` | ポインタ経由write先が不明 |
| `address_taken_unknown_effect` | アドレス取得の副作用が不明 |
| `complex_expression` | 式が複雑で分類不能 |
| `conditional_inactive_region` | inactive条件下のアクセス候補 |
| `unknown_active_state` | 条件コンパイル有効性不明 |
| `typedef_or_type_name_ambiguous` | 型名と変数名の区別が曖昧 |

---

## 6. 解析設計

### 6.1 基本アルゴリズム

処理フロー:

```text
analyze_global_access(request)
  1. source_digest / token stream を取得する
  2. function_location.body_range を取得する
  3. function_signature.parameters を取得する
  4. file scope範囲を走査して変数宣言候補を抽出する
  5. function body範囲を走査してlocal宣言候補を抽出する
  6. body内identifier useを抽出する
  7. identifierを parameter / local / global candidate / macro / unknown に分類する
  8. 代入・複合代入・++/--・アドレス取得・配列/メンバアクセスを判定する
  9. global_accesses / parameter_accesses / side_effect_candidates を生成する
 10. conditional context を付与する
 11. warnings / confidence を整理する
 12. GlobalAccessReport を返す
```

### 6.2 file scope declaration 抽出

対象例:

```c
int g_counter;
static int g_state;
extern int g_error;
struct ControlState g_control;
static char g_buffer[256];
```

方針:

- brace depth 0 かつ関数定義外の宣言文を対象にする
- `;` で終わる top-level 宣言を候補にする
- `(` を含む関数プロトタイプは原則除外する
- `typedef` 宣言は変数宣言ではなく type name candidate として別扱いまたは除外する
- `static` があれば scope `file_static`
- `extern` があれば scope `extern`
- initializer があっても宣言として扱う
- 複数宣言 `int a, b;` は初期対応では分割候補とする
- 複雑な宣言は raw保持 + warning とする

### 6.3 local declaration 抽出

対象例:

```c
int i;
static int initialized;
char *p;
struct Foo local;
int table[10];
```

方針:

- function body range内の宣言らしき文を抽出する
- C90前提ではブロック先頭宣言が多いが、実用上途中宣言も候補として扱う
- typedef-like な型名は Step 07 の TypeInfo と同様、解決せず候補扱いにする
- `static` localは scope `local_static`
- local変数名がfile scope変数と同名の場合、localを優先し warning `local_shadows_global` を出す

### 6.4 identifier分類

優先順位:

1. 関数名そのもの
2. キーワード
3. Step 05 macro definition 名
4. 関数引数名
5. local declaration 名
6. file scope static変数名
7. file scope global変数名
8. extern変数名
9. type name candidate
10. unknown

注意:

- 型名と変数名の曖昧性は残す
- macro由来の識別子はアクセス解析から除外し warningまたはmetadataに残す
- member名単体、例: `state.mode` の `mode` はglobal変数扱いしない

### 6.5 read / write 分類

代表ルール:

| パターン | 分類 |
|---|---|
| `x = y` の `x` | write |
| `x = y` の `y` | read |
| `x += y` の `x` | read_write |
| `x++` / `++x` | read_write |
| `return x` | read |
| `if (x)` | read |
| `f(x)` | read または passed_to_call |
| `f(&x)` | address_taken + passed_to_call |
| `&x` | address_taken |
| `x[i]` | read |
| `x[i] = y` | write / read_write候補 |
| `x.member` | read |
| `x.member = y` | write |

### 6.6 parameter side effect 分類

Step 07 の `direction_hint` と本文アクセスを組み合わせる。

対象例:

```c
*out_value = 1;
buffer[0] = 'A';
param->field = 10;
Update(param);
```

方針:

- `*param = ...` は `parameter_write`
- `param[index] = ...` は `parameter_write` または `read_write_candidate`
- `param->field = ...` は `parameter_write`
- `param.field = ...` は parameterがstruct値の場合のlocal write候補。Cでは値渡しのため副作用ではないが、rawとして記録する
- `Update(param)` は Step 09 の Call Analyzer で詳細化するため、Step 08では `passed_to_call` として候補保持
- `Update(&local)` は address escape candidate

### 6.7 pointer dereference unknown side effect

対象例:

```c
*p = value;
*(base + i) = value;
```

方針:

- `p` がparameterなら parameter_write候補
- `p` がglobal pointerなら global経由の unknown side effect候補
- `p` がlocal pointerなら unknown side effect候補
- alias解析はしない
- evidence と raw expression を必ず残す

### 6.8 conditional context

Step 05 の conditional active_state と Step 06 の function conditional contextを使う。

方針:

- アクセス行が inactive と推定される場合、accessは候補として残すが warningを付与する
- unknown active_stateの場合も候補として残し、confidenceを下げる
- active候補とinactive候補をreportで分けてもよい

---

## 7. CLI 接続設計

### 7.1 analyze-function の Step 08 接続

Step 08 では、`analyze-function` をグローバルアクセス候補抽出まで進める。

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
5. Step 08 の Global Access Analyzer を実行する
6. `global_access.json` を生成する
7. `global_access.md` を生成する
8. Step 09 の Call Analyzer が必要であることを message に含める
9. 抽出に成功した場合、status `partial` または `global_access_analyzed` を返す

### 7.2 analyze-global-access コマンド案

開発・debug 用に以下の独立コマンドを検討する。

```bat
unit-test-runner analyze-global-access ^
  --source D:\work\product\src\control.c ^
  --source-digest D:\work\unit_test_workspace\Control_Update\reports\source_digest.json ^
  --function-location D:\work\unit_test_workspace\Control_Update\reports\function_location.json ^
  --function-signature D:\work\unit_test_workspace\Control_Update\reports\function_signature.json ^
  --out D:\work\unit_test_workspace\Control_Update\reports\global_access.json
```

扱い:

- 公開コマンドにするかは実装時判断とする
- Step 08 計画では必須ではない
- 必須なのは internal usecase と `analyze-function` 接続である

---

## 8. Report 設計

### 8.1 global_access.json

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
  "file_scope_declarations": [
    {
      "name": "g_state",
      "scope": "file_static",
      "type_raw": "int",
      "is_pointer": false,
      "is_array": false,
      "line": 20
    }
  ],
  "global_accesses": [
    {
      "name": "g_state",
      "access_kind": "read_write",
      "scope": "file_static",
      "line": 120,
      "access_path": "g_state",
      "operator": "++",
      "confidence": "high",
      "evidence": "g_state++"
    },
    {
      "name": "g_error",
      "access_kind": "write",
      "scope": "extern",
      "line": 135,
      "access_path": "g_error",
      "operator": "=",
      "confidence": "high",
      "evidence": "g_error = ERROR_TIMEOUT"
    }
  ],
  "parameter_accesses": [
    {
      "parameter_name": "out_value",
      "body_access_hint": "write_candidate",
      "line": 150,
      "access_path": "*out_value",
      "confidence": "high",
      "evidence": "*out_value = result"
    }
  ],
  "side_effect_candidates": [
    {
      "kind": "parameter_write",
      "name": "out_value",
      "line": 150,
      "reason": "non-const pointer parameter is assigned through dereference",
      "confidence": "high"
    }
  ],
  "warnings": []
}
```

### 8.2 global_access.md

内容例:

```markdown
# Global Access Report

## Target

- Source: D:/work/product/src/control.c
- Function: Control_Update
- Status: analyzed

## File Scope Declarations

| Name | Scope | Type | Line |
|---|---|---|---:|
| g_state | file_static | int | 20 |
| g_error | extern | int | 25 |

## Global Accesses

| Line | Name | Scope | Access | Evidence | Confidence |
|---:|---|---|---|---|---|
| 120 | g_state | file_static | read_write | `g_state++` | high |
| 135 | g_error | extern | write | `g_error = ERROR_TIMEOUT` | high |

## Parameter Side Effects

| Line | Parameter | Access | Evidence | Confidence |
|---:|---|---|---|---|
| 150 | out_value | write_candidate | `*out_value = result` | high |

## Unresolved Identifiers

| Line | Name | Context | Confidence |
|---:|---|---|---|

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
      global_access/
        global_read.c
        global_write.c
        compound_assignment.c
        increment_decrement.c
        file_static.c
        extern_variable.c
        local_shadowing.c
        local_declarations.c
        parameter_read.c
        pointer_parameter_write.c
        array_parameter_write.c
        struct_member_access.c
        pointer_unknown_side_effect.c
        address_taken.c
        macro_identifier.c
        conditional_global_access.c
        malformed_expression.c
```

### 9.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| GLO-001 | global read | `return g_value;` | g_value read |
| GLO-002 | global write | `g_value = 1;` | g_value write |
| GLO-003 | read write compound | `g_value += 1;` | g_value read_write |
| GLO-004 | increment | `g_value++;` | g_value read_write |
| GLO-005 | file static | `static int g_state;` | scope file_static |
| GLO-006 | extern | `extern int g_error;` | scope extern |
| GLO-007 | local shadowing | local `g_value` | local優先、warning |
| GLO-008 | local declaration | `int local;` | local_declarationsに入る |
| GLO-009 | parameter read | `if (mode)` | parameter read |
| GLO-010 | pointer param write | `*out = 1;` | parameter_write |
| GLO-011 | array param write | `buf[0] = 1;` | parameter_write候補 |
| GLO-012 | struct member read | `g_state.mode` | access_path付きread |
| GLO-013 | struct member write | `g_state.mode = 1;` | access_path付きwrite |
| GLO-014 | pointer unknown | `*p = 1;` | pointer_write_unknown_target |
| GLO-015 | address taken | `&g_value` | address_taken |
| GLO-016 | passed to call | `foo(g_value)` | passed_to_call候補 |
| GLO-017 | macro identifier | `MAX(g_value)` | macro扱いを保守的に処理 |
| GLO-018 | inactive conditional | `#if 0 g=1` | inactive warning |
| GLO-019 | unresolved identifier | 未宣言識別子 | unresolved_identifiers |
| GLO-020 | malformed expression | 壊れた式 | warning complex_expression |
| GLO-021 | json output | global_access.json | JSON parse可能 |
| GLO-022 | markdown output | global_access.md | expected sectionあり |
| GLO-023 | analyze-function integration | Step04+05+06+07+08 | global_access生成 |

### 9.3 テスト方針

- declaration scanner は小さなC断片で単体テストする
- access classifier はtoken sequence単位でもテストする
- integration test では Step 05 source_digest、Step 06 function_location、Step 07 function_signature fixture と接続する
- JSONは `json.loads()` で検証する
- Markdownは主要sectionの存在を検証する
- ポインタ経由アクセスは過信せず、unknown side effect候補として検証する
- local shadowing は明示的にテストする

---

## 10. 実装タスク分解

### Task 08-01: Global access model 定義

成果物:

- `src/unit_test_runner/c_analyzer/global_access_models.py`
- `GlobalAccessRequest`
- `GlobalAccessReport`
- `VariableDeclaration`
- `IdentifierUse`
- `VariableAccess`
- `ParameterAccess`
- `SideEffectCandidate`
- `GlobalAccessWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 08-02: File scope declaration scanner

成果物:

- `src/unit_test_runner/c_analyzer/declaration_scanner.py`
- file scope変数候補抽出
- static / extern分類
- prototype / function definition除外

完了条件:

- GLO-005 / GLO-006 が通る

### Task 08-03: Local declaration scanner

成果物:

- function body内local変数候補抽出
- local_static分類
- local shadowing検出

完了条件:

- GLO-007 / GLO-008 が通る

### Task 08-04: Identifier use analyzer

成果物:

- body内identifier抽出
- parameter / local / global / macro / unknown分類
- member名除外

完了条件:

- GLO-001 / GLO-009 / GLO-019 が通る

### Task 08-05: Access classifier

成果物:

- read / write / read_write分類
- assignment / compound assignment / increment対応
- return / condition / expression read対応

完了条件:

- GLO-001 から GLO-004 が通る

### Task 08-06: Member / array access path builder

成果物:

- `g_state.mode`
- `g_state->mode`
- `g_table[index]`
- access_path生成

完了条件:

- GLO-011 / GLO-012 / GLO-013 が通る

### Task 08-07: Parameter side effect detector

成果物:

- pointer parameter write候補
- array parameter write候補
- address_taken / passed_to_call候補

完了条件:

- GLO-010 / GLO-011 / GLO-015 / GLO-016 が通る

### Task 08-08: Unknown side effect handler

成果物:

- pointer dereference writeのunknown化
- complex expression warning
- evidence保持

完了条件:

- GLO-014 / GLO-020 が通る

### Task 08-09: Conditional context integration

成果物:

- Step 05 active_stateとの接続
- inactive / unknown warning
- confidence調整

完了条件:

- GLO-018 が通る

### Task 08-10: Global access writer

成果物:

- `src/unit_test_runner/c_analyzer/global_access_writer.py`
- `global_access.json`
- `reports/global_access_markdown.py`

完了条件:

- GLO-021 / GLO-022 が通る

### Task 08-11: analyze-function 接続

成果物:

- Step 04 source membership取得
- Step 05 source_digest生成
- Step 06 function_location生成
- Step 07 function_signature生成
- Step 08 global_access生成
- CLI `analyze-function` の出力更新

完了条件:

- GLO-023 が通る

### Task 08-12: fixture / test 整備

成果物:

- `tests/fixtures/c_sources/global_access/...`
- `tests/unit/test_declaration_scanner.py`
- `tests/unit/test_identifier_use_analyzer.py`
- `tests/unit/test_access_classifier.py`
- `tests/unit/test_parameter_side_effect.py`
- `tests/unit/test_global_access_writer.py`
- `tests/unit/test_analyze_function_partial_global_access.py`

完了条件:

- GLO-001 から GLO-023 が通る

---

## 11. 受け入れ基準

Step 08 は、以下をすべて満たしたら完了とする。

1. file scope変数候補を抽出できる
2. file scope static変数を区別できる
3. extern変数宣言候補を区別できる
4. 関数本文内local変数候補を抽出できる
5. local変数がglobal候補をshadowする場合にlocalを優先できる
6. 関数引数をidentifier分類に反映できる
7. グローバル変数候補のreadを抽出できる
8. グローバル変数候補のwriteを抽出できる
9. 複合代入、increment/decrementをread_writeとして扱える
10. address_takenを抽出できる
11. passed_to_call候補を保持できる
12. 配列アクセスと構造体メンバアクセスをaccess_path付きで保持できる
13. 非const pointer / array引数の書き込み候補を抽出できる
14. ポインタ経由の不明writeをunknown side effectとして保持できる
15. macro由来または型名候補の識別子を過信せずwarningまたはmetadataに残せる
16. inactive / unknown conditional contextのアクセス候補にwarningを付与できる
17. `global_access.json` を生成できる
18. `global_access.md` を生成できる
19. `analyze-function` が Step 08 時点では global access 抽出まで進み、Step 09 が必要である旨を返せる
20. Step 09 の Call Analyzer に渡せる identifier use / side effect candidate 情報がある
21. 外部関数呼び出しの詳細解析へ踏み込みすぎていない
22. 分岐・条件解析へ踏み込みすぎていない

---

## 12. 成果物

Step 08 の成果物は以下とする。

```text
src/
  unit_test_runner/
    c_analyzer/
      global_access_models.py
      declaration_scanner.py
      identifier_use.py
      access_classifier.py
      parameter_side_effect.py
      global_access_analyzer.py
      global_access_writer.py
    reports/
      global_access_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    c_sources/
      global_access/
        global_read.c
        global_write.c
        compound_assignment.c
        increment_decrement.c
        file_static.c
        extern_variable.c
        local_shadowing.c
        local_declarations.c
        parameter_read.c
        pointer_parameter_write.c
        array_parameter_write.c
        struct_member_access.c
        pointer_unknown_side_effect.c
        address_taken.c
        macro_identifier.c
        conditional_global_access.c
        malformed_expression.c
  unit/
    test_declaration_scanner.py
    test_identifier_use_analyzer.py
    test_access_classifier.py
    test_parameter_side_effect.py
    test_global_access_writer.py
    test_analyze_function_partial_global_access.py
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/c_analyzer/tokens.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/signature_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/function_models.py` 必要な場合のみ

---

## 13. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| C宣言解析の複雑さ | ポインタ、配列、複数宣言、初期化子で壊れやすい | 完全解析せずrawとconfidenceを保持する |
| local/global誤分類 | 型名、macro、local shadowingで誤判定しやすい | 優先順位を明文化し、warningを出す |
| ポインタalias | `*p` が何を指すか分からない | unknown side effectとして保守的に扱う |
| 関数呼び出し副作用 | `Update(&g)` の影響はStep08だけでは分からない | Step08ではpassed_to_call/address_takenとして保持し、Step09に渡す |
| macroによるアクセス | macro展開しないと実アクセスが見えない | macro由来は過信せずwarningにする |
| 条件コンパイル | inactive領域のアクセスを候補に含めるか迷う | active_stateを付与し、review可能にする |
| Step09責務の侵食 | 外部呼び出し解析まで進みたくなる | Step08は変数アクセスと副作用候補に限定する |
| false positive | 未解決識別子をglobal扱いしすぎる | unresolved_identifiersとして別枠にし、confidenceを下げる |

---

## 14. Step 09 への接続

Step 08 完了後、Step 09 では Call Analyzer を実装する。
Step 09 は、Step 08 の identifier use / side effect candidate と、Step 05 の token stream、Step 06 の function body rangeを使い、外部関数呼び出し、内部static関数呼び出し、標準ライブラリ候補、スタブ候補を抽出する。

想定接続:

```python
function_signature = extract_signature(source_digest, function_location)
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
```

Step 09 で使う情報:

- function body range
- token stream
- parameter list
- identifier use
- address_taken
- passed_to_call候補
- side_effect_candidates
- conditional context

Step 08 の責務は、Call Analyzer が関数呼び出しの副作用やスタブ候補を評価する際に使える、変数アクセスと副作用候補の土台を作ることである。

---

## 15. まとめ

Step 08 は、Step 07 で整理した関数インターフェースと Step 06 で特定した関数本文範囲を使い、対象関数の状態入出力候補を抽出するステップである。

このステップにより、対象関数が参照・更新するグローバル変数候補、file scope static変数、extern変数、ローカル変数、引数経由の副作用候補を `global_access` として整理できる。

ただし、Step 08 は外部関数呼び出しや分岐・条件の詳細解析を行う段階ではない。
変数アクセスと副作用候補に責務を絞り、Step 09 の Call Analyzer へ安全な入力を渡すことを完了条件とする。

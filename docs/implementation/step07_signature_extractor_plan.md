# Step 07: Signature Extractor 実装計画

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

---

## 1. 位置づけ

本書は、`unitTestRunner` の第7ステップとして **Signature Extractor** を実装するための計画である。

Step 06 では、指定関数の定義位置、関数ヘッダ範囲、関数本文範囲、`function_slice` を特定する計画を定義した。
Step 07 では、Step 06 が切り出した `header_range` と `signature_preview` を使い、対象関数の **戻り値型、関数名、引数、修飾子、旧式K&R引数宣言の概要** を抽出する。

Step 07 は、関数の入出力インターフェースを整理する段階であり、まだ関数本文の意味解析には踏み込まない。
グローバル変数アクセス解析、外部呼び出し解析、分岐・条件解析は Step 08 以降で扱う。

Step 07 の主な責務は以下である。

- 関数ヘッダ範囲からシグネチャ文字列を取得する
- 戻り値型を抽出する
- storage class、type qualifier、calling convention を抽出する
- 関数名を確認する
- 引数リストを抽出する
- 各引数の型、名前、ポインタ、配列、const / volatile を粗く分類する
- `void` 引数、可変長引数 `...` を扱う
- K&R style 旧式関数定義の引数宣言を粗く扱う
- 関数ポインタ引数や配列引数など、複雑な引数を `complex` として保守的に残す
- Step 08 以降の入出力解析に渡せる `function_signature.json` を生成する

---

## 2. 目的

Step 07 の目的は、関数単位テスト設計の起点となる **関数インターフェース情報** を安定して抽出することである。

具体的には、以下を実現する。

- `int Control_Update(int mode, int sensor)` から戻り値型 `int` と引数 `mode` / `sensor` を抽出できる
- `static` / `extern` などの storage class を抽出できる
- `const` / `volatile` などの qualifier を保持できる
- `__stdcall` / `__cdecl` などのVC6で見かける calling convention を保持できる
- `struct Foo *p`、`const char *name`、`int values[]` のような引数を分類できる
- `void` 引数を「引数なし」として扱える
- `...` を可変長引数として扱える
- 複数行シグネチャを扱える
- K&R style の旧式定義を medium confidence で扱える
- 解析不能または曖昧な型は捨てずに warning と raw text として保持できる
- `function_signature.json` / `function_signature.md` を出力できる
- `analyze-function` を Step 07 時点で「関数位置特定 + シグネチャ抽出」まで進められる

---

## 3. スコープ

### 3.1 実装対象

Step 07 で実装するもの:

1. Signature source builder
   - Step 06 の `header_range` から元ソースのヘッダ文字列を取得
   - コメント・文字列マスク済み情報との対応
   - K&R style の場合は `{` 前までの旧式引数宣言範囲を含める

2. Signature normalizer
   - 改行、タブ、連続空白の正規化
   - calling convention 位置の揺れを吸収
   - function name の前後を解析しやすい形に整える

3. Return type extractor
   - storage class
   - return type raw
   - base type
   - pointer level
   - qualifier
   - calling convention

4. Parameter list extractor
   - `(...)` 内のトップレベル comma 分割
   - `void`
   - `...`
   - pointer / array / function pointer の粗分類
   - unnamed parameter の扱い

5. K&R style parameter extractor
   - `int f(a, b)` の名前リスト抽出
   - 後続の `int a; char *b;` の型宣言対応
   - 未解決引数への warning

6. Type classification
   - scalar
   - pointer
   - array
   - struct / union / enum
   - typedef-like
   - function pointer
   - unknown / complex

7. Reports
   - `function_signature.json`
   - `function_signature.md`

8. CLI 接続
   - `analyze-function` を signature 抽出まで進める
   - status `partial` または `signature_extracted` を返す
   - Step 08 の Global Access Analyzer が必要である旨を message に含める

9. Tests
   - simple signature
   - static function
   - const pointer
   - struct pointer
   - array parameter
   - function pointer parameter
   - void parameter
   - varargs
   - multi-line signature
   - K&R style
   - calling convention
   - malformed signature

### 3.2 対象外

Step 07 では以下を対象外とする。

- typedef の定義解決
- struct / union / enum のフィールド解析
- include ファイルを辿った型定義解析
- グローバル変数アクセス解析
- 引数が実際に入力か出力かの本文解析
- 外部呼び出し解析
- 分岐・条件網羅候補生成
- 境界値・同値クラス候補生成
- スタブ生成
- テストハーネス生成
- 関数ポインタ型の完全解析
- C++ method / template / overload の対応

Step 07 では、あくまで関数ヘッダから読み取れるインターフェース情報に限定する。

---

## 4. 入力と出力

### 4.1 入力

主入力:

- Step 04 の `build_context`
- Step 05 の `source_digest`
- Step 06 の `function_location`
- 元ソーステキスト
- masked text
- token stream

入力イメージ:

```json
{
  "source": "D:/work/product/src/control.c",
  "function": "Control_Update",
  "source_digest": "reports/source_digest.json",
  "function_location": "reports/function_location.json"
}
```

### 4.2 出力

Step 07 の主要出力は `function_signature` である。

```text
workspace/
  Control_Update/
    reports/
      source_digest.json
      function_location.json
      function_signature.json
      function_signature.md
    intermediate/
      masked_source.c
      function_slice.c
```

`function_signature.json` は Step 08 以降の入力になる。

---

## 5. データモデル設計

### 5.1 FunctionSignatureRequest

```python
@dataclass
class FunctionSignatureRequest:
    source_path: Path
    function_name: str
    source_text: str
    masked_text: str
    function_location: FunctionLocation
    tokens: list[LexToken]
```

役割:

- Signature Extractor の入力条件をまとめる
- CLI / internal usecase の境界を明確にする

### 5.2 FunctionSignature

```python
@dataclass
class FunctionSignature:
    function_name: str
    source_path: Path
    status: str
    style: str
    confidence: str
    signature_range: SourceRange
    header_text_raw: str
    header_text_normalized: str
    storage_class: str | None
    calling_convention: str | None
    return_type: TypeInfo
    parameters: list[ParameterInfo]
    warnings: list[SignatureWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `parsed` | シグネチャを抽出できた |
| `partial` | 一部不明だが主要情報は抽出できた |
| `ambiguous` | 候補が曖昧 |
| `malformed` | 解析不能 |

`style` 候補:

| style | 意味 |
|---|---|
| `ansi` | ANSI C style prototype |
| `knr` | K&R old style definition |
| `unknown` | 判定不能 |

### 5.3 TypeInfo

```python
@dataclass
class TypeInfo:
    raw: str
    normalized: str
    base_type: str | None
    qualifiers: list[str]
    storage_class: str | None
    pointer_level: int
    is_const_pointer: bool | None
    is_struct: bool
    is_union: bool
    is_enum: bool
    is_typedef_like: bool
    is_function_pointer: bool
    is_array: bool
    array_dimensions: list[str]
    confidence: str
```

役割:

- 戻り値型と引数型の共通表現
- 型定義の完全解決ではなく、テスト設計に使える粗い分類を保持する

### 5.4 ParameterInfo

```python
@dataclass
class ParameterInfo:
    index: int
    name: str | None
    type_info: TypeInfo
    raw: str
    direction_hint: str
    is_variadic: bool
    is_void: bool
    default_value: str | None
    confidence: str
    warnings: list[SignatureWarning]
```

`direction_hint` 候補:

| direction_hint | 意味 |
|---|---|
| `input` | 値渡し、const pointer など入力寄り |
| `output_candidate` | 非const pointer、配列など出力候補 |
| `input_output_candidate` | 読み書き両方の可能性 |
| `none` | voidなど |
| `unknown` | 判定不能 |

注意:

- Step 07 の direction_hint は本文解析なしのヒントである
- 実際の読み書き判定は Step 08 以降で行う

### 5.5 SignatureWarning

```python
@dataclass
class SignatureWarning:
    code: str
    message: str
    line_number: int | None = None
    column: int | None = None
    text: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `signature_not_found` | header_range からシグネチャを取得できない |
| `malformed_parameter_list` | 引数リストが壊れている |
| `unnamed_parameter` | 引数名がない |
| `complex_parameter` | 複雑な引数で詳細分類不能 |
| `function_pointer_parameter` | 関数ポインタ引数 |
| `old_style_parameter_unresolved` | K&R style の型宣言未解決 |
| `typedef_unresolved` | typedefらしい型を解決していない |
| `array_parameter_detected` | 配列引数を検出した |
| `variadic_parameter_detected` | `...` を検出した |
| `calling_convention_detected` | `__stdcall` 等を検出した |
| `macro_in_signature` | macroらしきtokenがシグネチャ内にある |

---

## 6. Signature Extractor 設計

### 6.1 基本アルゴリズム

処理フロー:

```text
extract_signature(request)
  1. function_location.selected_candidate を取得する
  2. selected_candidate.header_range から header_text を切り出す
  3. header_text を正規化する
  4. 関数名 token の位置を確認する
  5. 関数名直後の `(` と対応する `)` を探す
  6. `(` より前を return side として抽出する
  7. `(` と `)` の内側を parameter side として抽出する
  8. return side から storage class / calling convention / return type を抽出する
  9. parameter side をトップレベル comma で分割する
 10. 各 parameter を TypeInfo + name へ分解する
 11. K&R style の場合は `)` 後から `{` 前までの宣言列を使って型を補完する
 12. warnings / confidence を付与する
 13. FunctionSignature を返す
```

### 6.2 ANSI style 基本形

対象:

```c
static int Control_Update(int mode, int sensor)
```

抽出:

```json
{
  "storage_class": "static",
  "return_type": {
    "raw": "int",
    "base_type": "int",
    "pointer_level": 0
  },
  "parameters": [
    {
      "name": "mode",
      "type": "int",
      "direction_hint": "input"
    },
    {
      "name": "sensor",
      "type": "int",
      "direction_hint": "input"
    }
  ]
}
```

### 6.3 戻り値型抽出

return side の例:

```c
static const char * __stdcall GetName
```

関数名より前の token を以下に分類する。

- storage class: `static`, `extern`, `register` など
- qualifier: `const`, `volatile`
- calling convention: `__stdcall`, `__cdecl`, `__fastcall`, `CALLBACK`, `WINAPI` など
- type token: `char`, `int`, `struct Foo`, typedef-like name など
- pointer marker: `*`

方針:

- calling convention は return type から分離して保持する
- `const char *` は base_type `char`, qualifier `const`, pointer_level `1`
- `struct Foo *` は is_struct true, base_type `struct Foo`, pointer_level `1`
- typedef-like な型名は解決せず `is_typedef_like=true` とする

### 6.4 引数分割

parameter side はトップレベル comma で分割する。

以下の内部 comma は分割対象にしない。

- 関数ポインタ引数の `(*cb)(int, int)` 内
- 配列サイズmacro内の comma
- 括弧内の comma

初期方針:

- `(` / `)`、`[` / `]` のdepthを見てトップレベルのみ分割する
- それでも壊れる場合は raw parameter を `complex` とする

### 6.5 引数解析ルール

一般的な形:

```c
int mode
const char *name
struct Foo *foo
int values[]
unsigned long count
```

推定方針:

- 原則として最後の identifier を引数名候補にする
- `*name` のように `*` が名前側についても pointer_level に反映する
- `name[]` は is_array true とする
- `const` がある pointer は direction_hint `input` 寄り
- 非const pointer / array は output_candidate または input_output_candidate とする
- typedef-like な先頭識別子は解決せず raw として保持する

### 6.6 void parameter

対象:

```c
int f(void)
```

方針:

- parameter list が `void` のみなら parameters は空リスト、または `is_void=true` のParameterInfo 1件のどちらかに統一する
- Step 07 では `parameters=[]` を標準とする
- report には `takes_no_parameters=true` を出してもよい

### 6.7 variadic parameter

対象:

```c
int log_printf(const char *fmt, ...)
```

方針:

- `...` は `is_variadic=true` のParameterInfo として扱う
- warning `variadic_parameter_detected` を付与する
- テスト自動生成では扱いに注意が必要なため、明示的に残す

### 6.8 function pointer parameter

対象:

```c
int RegisterCallback(int (*callback)(int code))
```

方針:

- `(*callback)` pattern を検出する
- name は `callback` とする
- type_info.is_function_pointer = true
- rawを保持する
- 詳細な戻り値型・引数型は Step 07 では完全解析しない
- warning `function_pointer_parameter` を付与する
- confidence `medium` または `low`

### 6.9 array parameter

対象:

```c
int Sum(int values[], int count)
int Read(char buffer[256])
```

方針:

- `[]` または `[N]` を検出する
- type_info.is_array = true
- array_dimensions に `""` または `"256"` を保持する
- direction_hint は `input_output_candidate` または `output_candidate`
- warning `array_parameter_detected` を付与してもよい

### 6.10 K&R style 旧式定義

対象:

```c
int Control_Update(mode, sensor)
int mode;
int sensor;
{
    return 0;
}
```

処理:

1. 関数名後の `(...)` 内を名前リストとして抽出する
2. `)` 後から `{` 前までを旧式引数宣言ブロックとして扱う
3. `int mode;` のような宣言から型と名前を対応付ける
4. 未対応の名前があれば warning `old_style_parameter_unresolved`
5. style `knr`, confidence `medium` とする

制約:

- 複数変数宣言 `int a, b;` は対応候補とするが、複雑な pointer 混在は confidence を下げる
- macro を含む宣言は raw保持に留める

---

## 7. Direction Hint 設計

Step 07 では、本文を見ないため、引数が本当に入力か出力かは確定しない。
ただし、テスト設計の下準備として方向ヒントを付与する。

| 条件 | direction_hint |
|---|---|
| scalar value | `input` |
| `const T *` | `input` |
| `T *` | `input_output_candidate` |
| `T *out` / `pOut` など名前ヒントあり | `output_candidate` |
| array | `input_output_candidate` |
| function pointer | `input` |
| void | `none` |
| unknown / complex | `unknown` |

名前ヒント:

- `out`
- `output`
- `pOut`
- `result`
- `buffer`
- `buf`

注意:

- direction_hint は仕様ではない
- Step 08 以降で本文の read / write を解析して補正する
- report では review required として扱う

---

## 8. CLI 接続設計

### 8.1 analyze-function の Step 07 接続

Step 07 では、`analyze-function` をシグネチャ抽出まで進める。

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
4. Step 07 の Signature Extractor を実行する
5. `function_signature.json` を生成する
6. `function_signature.md` を生成する
7. Step 08 の Global Access Analyzer が必要であることを message に含める
8. シグネチャ抽出に成功した場合、status `partial` または `signature_extracted` を返す

### 8.2 extract-signature コマンド案

開発・debug 用に以下の独立コマンドを検討する。

```bat
unit-test-runner extract-signature ^
  --source D:\work\product\src\control.c ^
  --function-location D:\work\unit_test_workspace\Control_Update\reports\function_location.json ^
  --source-digest D:\work\unit_test_workspace\Control_Update\reports\source_digest.json ^
  --out D:\work\unit_test_workspace\Control_Update\reports\function_signature.json
```

扱い:

- 公開コマンドにするかは実装時判断とする
- Step 07 計画では必須ではない
- 必須なのは internal usecase と `analyze-function` 接続である

---

## 9. Report 設計

### 9.1 function_signature.json

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
    "status": "parsed",
    "style": "ansi",
    "confidence": "high",
    "storage_class": "static",
    "calling_convention": null,
    "return_type": {
      "raw": "int",
      "normalized": "int",
      "base_type": "int",
      "qualifiers": [],
      "pointer_level": 0,
      "is_struct": false,
      "is_typedef_like": false,
      "confidence": "high"
    },
    "parameters": [
      {
        "index": 0,
        "name": "mode",
        "raw": "int mode",
        "type": {
          "raw": "int",
          "base_type": "int",
          "pointer_level": 0
        },
        "direction_hint": "input",
        "confidence": "high"
      },
      {
        "index": 1,
        "name": "sensor",
        "raw": "int sensor",
        "type": {
          "raw": "int",
          "base_type": "int",
          "pointer_level": 0
        },
        "direction_hint": "input",
        "confidence": "high"
      }
    ]
  },
  "warnings": []
}
```

### 9.2 function_signature.md

内容例:

```markdown
# Function Signature Report

## Target

- Source: D:/work/product/src/control.c
- Function: Control_Update
- Status: parsed
- Style: ansi
- Confidence: high

## Signature

```c
static int Control_Update(int mode, int sensor)
```

## Return Type

| Item | Value |
|---|---|
| Raw | int |
| Base Type | int |
| Pointer Level | 0 |
| Qualifiers | なし |

## Parameters

| Index | Name | Raw Type | Pointer | Array | Direction Hint | Confidence |
|---:|---|---|---:|---|---|---|
| 0 | mode | int | 0 | no | input | high |
| 1 | sensor | int | 0 | no | input | high |

## Warnings

なし
```

---

## 10. テスト計画

### 10.1 fixture 構成

```text
tests/
  fixtures/
    c_sources/
      signatures/
        simple_signature.c
        static_signature.c
        const_pointer.c
        struct_pointer.c
        array_parameter.c
        function_pointer_parameter.c
        void_parameter.c
        variadic_parameter.c
        multiline_signature.c
        old_style_signature.c
        calling_convention.c
        unnamed_parameter.c
        malformed_signature.c
        macro_in_signature.c
```

### 10.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| SIG-001 | simple | `int f(int a)` | return int, param a int |
| SIG-002 | static | `static int f(void)` | storage_class static |
| SIG-003 | pointer return | `char *f(void)` | return pointer_level 1 |
| SIG-004 | const pointer param | `const char *s` | qualifier const, pointer_level 1 |
| SIG-005 | struct pointer | `struct Foo *p` | is_struct true |
| SIG-006 | typedef-like | `DWORD value` | is_typedef_like true |
| SIG-007 | array param | `int values[]` | is_array true |
| SIG-008 | fixed array | `char buf[256]` | array_dimensions 256 |
| SIG-009 | function pointer param | `int (*cb)(int)` | is_function_pointer true |
| SIG-010 | void param | `void` | parameters empty |
| SIG-011 | variadic | `...` | variadic parameter warning |
| SIG-012 | multiline | 複数行signature | parsed high/medium |
| SIG-013 | calling convention | `__stdcall` | calling_convention detected |
| SIG-014 | WINAPI macro | `WINAPI` | calling_convention detected or macro warning |
| SIG-015 | K&R style | old style | style knr, params resolved |
| SIG-016 | K&R unresolved | old style missing declaration | warning old_style_parameter_unresolved |
| SIG-017 | unnamed parameter | `int` | unnamed_parameter warning |
| SIG-018 | malformed | 壊れた括弧 | status malformed |
| SIG-019 | macro in signature | `API int f` | macro_in_signature warning or calling convention |
| SIG-020 | direction scalar | `int a` | direction input |
| SIG-021 | direction nonconst ptr | `int *p` | input_output_candidate |
| SIG-022 | direction output name | `int *outValue` | output_candidate |
| SIG-023 | json output | function_signature.json | JSON parse 可能 |
| SIG-024 | markdown output | function_signature.md | expected sectionあり |
| SIG-025 | analyze-function integration | Step04+05+06+07 | function_signature生成 |

### 10.3 テスト方針

- Signature Extractor 単体テストでは Step 06 の FunctionLocation fixture を使う
- 型分解ロジックは小さな文字列単位でもテストする
- parameter split は括弧・配列・関数ポインタを重点的にテストする
- K&R style は専用fixtureで検証する
- JSONは `json.loads()` で検証する
- Markdownは主要sectionの存在を検証する
- direction_hint は仕様ではなくヒントなので、過度に複雑な推定はしない

---

## 11. 実装タスク分解

### Task 07-01: Signature model 定義

成果物:

- `src/unit_test_runner/c_analyzer/signature_models.py`
- `FunctionSignatureRequest`
- `FunctionSignature`
- `TypeInfo`
- `ParameterInfo`
- `SignatureWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 07-02: Signature source builder

成果物:

- `src/unit_test_runner/c_analyzer/signature_source.py`
- header_range から raw header text 切り出し
- normalized header生成
- K&R declaration blockの切り出し

完了条件:

- simple / multiline / K&R fixture で header text を取得できる

### Task 07-03: Parameter list splitter

成果物:

- top-level comma split
- parentheses / brackets depth handling
- function pointer parameter対応

完了条件:

- SIG-007 / SIG-008 / SIG-009 が通る

### Task 07-04: Return type extractor

成果物:

- storage class抽出
- qualifier抽出
- calling convention抽出
- pointer level抽出
- typedef-like判定

完了条件:

- SIG-001 から SIG-006、SIG-013、SIG-014 が通る

### Task 07-05: Parameter extractor

成果物:

- parameter raw分解
- name抽出
- type_info生成
- unnamed warning
- void / variadic handling

完了条件:

- SIG-004 から SIG-012、SIG-017、SIG-018 が通る

### Task 07-06: K&R style extractor

成果物:

- old style name list抽出
- declaration block解析
- name/type対応付け
- unresolved warning

完了条件:

- SIG-015 / SIG-016 が通る

### Task 07-07: Direction hint classifier

成果物:

- scalar / const pointer / nonconst pointer / array / output name hint
- direction_hint付与

完了条件:

- SIG-020 / SIG-021 / SIG-022 が通る

### Task 07-08: Signature writer

成果物:

- `src/unit_test_runner/c_analyzer/signature_writer.py`
- `function_signature.json`
- `reports/function_signature_markdown.py`

完了条件:

- SIG-023 / SIG-024 が通る

### Task 07-09: analyze-function 接続

成果物:

- Step 04 source membership取得
- Step 05 source_digest生成
- Step 06 function_location生成
- Step 07 function_signature生成
- CLI `analyze-function` の出力更新

完了条件:

- SIG-025 が通る

### Task 07-10: fixture / test 整備

成果物:

- `tests/fixtures/c_sources/signatures/...`
- `tests/unit/test_signature_source.py`
- `tests/unit/test_parameter_splitter.py`
- `tests/unit/test_return_type_extractor.py`
- `tests/unit/test_parameter_extractor.py`
- `tests/unit/test_signature_writer.py`
- `tests/unit/test_analyze_function_partial_signature.py`

完了条件:

- SIG-001 から SIG-025 が通る

---

## 12. 受け入れ基準

Step 07 は、以下をすべて満たしたら完了とする。

1. Step 06 の `header_range` からシグネチャ文字列を取得できる
2. 複数行シグネチャを扱える
3. 戻り値型 raw / normalized / base_type を抽出できる
4. storage class を抽出できる
5. qualifier を抽出できる
6. calling convention を抽出または warning として保持できる
7. pointer return を分類できる
8. 引数リストをトップレベルcommaで分割できる
9. 引数名と引数型を抽出できる
10. `void` 引数を引数なしとして扱える
11. `...` 可変長引数を扱える
12. pointer / const pointer / array parameter を分類できる
13. struct / union / enum 引数を分類できる
14. typedef-like な型を未解決のまま保持できる
15. function pointer parameter を complex として保持できる
16. K&R style の旧式引数定義を medium confidence で扱える
17. 解析不能箇所を warning と raw text として保持できる
18. direction_hint を保守的に付与できる
19. `function_signature.json` を生成できる
20. `function_signature.md` を生成できる
21. `analyze-function` が Step 07 時点では signature 抽出まで進み、Step 08 が必要である旨を返せる
22. Step 08 の Global Access Analyzer に渡せる return / parameter model がある
23. 本文の読み書き解析へ踏み込みすぎていない

---

## 13. 成果物

Step 07 の成果物は以下とする。

```text
src/
  unit_test_runner/
    c_analyzer/
      signature_models.py
      signature_source.py
      signature_extractor.py
      parameter_splitter.py
      type_classifier.py
      signature_writer.py
    reports/
      function_signature_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    c_sources/
      signatures/
        simple_signature.c
        static_signature.c
        const_pointer.c
        struct_pointer.c
        array_parameter.c
        function_pointer_parameter.c
        void_parameter.c
        variadic_parameter.c
        multiline_signature.c
        old_style_signature.c
        calling_convention.c
        unnamed_parameter.c
        malformed_signature.c
        macro_in_signature.c
  unit/
    test_signature_source.py
    test_parameter_splitter.py
    test_return_type_extractor.py
    test_parameter_extractor.py
    test_signature_writer.py
    test_analyze_function_partial_signature.py
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/c_analyzer/function_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/function_locator.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/tokens.py` 必要な場合のみ

---

## 14. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| C型構文の複雑さ | ポインタ、配列、関数ポインタ、修飾子で分解が難しい | 完全解決を狙わず raw と confidence を保持する |
| typedef未解決 | includeを辿らないため実体型が不明 | `is_typedef_like` として保持し、Step後続で必要なら拡張する |
| 関数ポインタ引数 | 詳細解析が難しい | `is_function_pointer` と raw を保持し、warningを付ける |
| K&R style | 古い定義で型対応が崩れやすい | medium confidence とし、未解決引数warningを出す |
| calling convention | `WINAPI` や macro形式が多い | 既知リストで検出し、不明macroは warning と raw保持 |
| direction_hintの過信 | 本文を見ないため実際の入出力は未確定 | reportでhint扱いにし、Step08以降で補正する |
| header_rangeの過不足 | Step06の範囲推定に依存する | raw headerを保持し、異常時は warning として返す |
| Step08責務の侵食 | 本文を見て読み書き判定したくなる | Step07はヘッダ情報に限定する |

---

## 15. Step 08 への接続

Step 07 完了後、Step 08 では Global Access Analyzer を実装する。
Step 08 は、Step 07 の `FunctionSignature` と Step 06 の `function_location.body_range` を使い、関数本文中のグローバル変数候補、file scope static、extern変数候補、引数経由の副作用候補を抽出する。

想定接続:

```python
function_signature = extract_signature(source_digest, function_location)
global_access = analyze_global_access(
    source_digest=source_digest,
    function_location=function_location,
    function_signature=function_signature,
)
```

Step 08 で使う情報:

- function body range
- return type
- parameter list
- pointer / array / const分類
- direction_hint
- token stream
- conditional context

Step 07 の責務は、Global Access Analyzer が「何が引数で、何が戻り値か」を理解できるモデルを渡すことである。

---

## 16. まとめ

Step 07 は、Step 06 で特定した対象関数のヘッダ範囲から、関数単位テスト設計に必要なインターフェース情報を抽出するステップである。

このステップにより、対象関数の戻り値型、引数、ポインタ・配列・const、呼び出し規約、K&R style の有無、可変長引数、複雑な引数の warning を `function_signature` として整理できる。

ただし、Step 07 は関数本文を解析して実際の入出力や副作用を確定する段階ではない。
本文解析は Step 08 以降に委ね、Step 07 では保守的な型・引数モデルを作ることを完了条件とする。

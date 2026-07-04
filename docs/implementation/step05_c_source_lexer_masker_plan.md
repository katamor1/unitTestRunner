# Step 05: C Source Lexer / Masker 実装計画

作成日: 2026-07-04  
状態: Draft v0.1  
対象リポジトリ: `katamor1/unitTestRunner`  
製造担当想定: CODEX  
前提文書:

- `docs/adr/0001-cli-layer-language-selection.md`
- `docs/implementation/step02_cli_entry_point_plan.md`
- `docs/implementation/step03_dsw_parser_plan.md`
- `docs/implementation/step04_dsp_parser_plan.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第5ステップとして **C Source Lexer / Masker** を実装するための計画である。

Step 04 では、`.dsw` / `.dsp` から対象 `.c` の所属プロジェクト、構成、define、include directory、forced include、PCH などの `build_context` を得る計画を定義した。
Step 05 では、その `build_context` を受け取り、対象 `.c` を関数解析しやすい形へ前処理する。

Step 05 は、C関数ロケータやシグネチャ解析そのものではない。
それらは Step 06 以降で実装する。

Step 05 の主な責務は以下である。

- Cソースを読み込む
- コメントをマスクする
- 文字列リテラルと文字定数をマスクする
- 行番号を保持する
- プリプロセッサ行を抽出する
- `#if` / `#ifdef` / `#ifndef` / `#else` / `#elif` / `#endif` の構造を粗く把握する
- `#include` と `#define` を抽出する
- 後続の関数ロケータが安全に波括弧や識別子を見られる状態を作る

---

## 2. 目的

Step 05 の目的は、VC6 / C90 世代の C ソースに対して、後続の関数単位解析が壊れにくくなる **軽量字句解析・マスク処理基盤** を作ることである。

具体的には、以下を実現する。

- `.c` / `.h` ファイルを encoding fallback 付きで読み込める
- コメント内の `{` / `}` / `(` / `)` / `;` などを関数解析対象から除外できる
- 文字列リテラル内の `{` / `}` / `//` / `/*` などを誤認しない
- 文字定数内の `\'` や `\\` を誤認しない
- マスク後も元ソースと同じ行数・列位置に近い情報を保持できる
- 後続処理が元の行番号でエビデンスを出せる
- プリプロセッサ directive を一覧化できる
- include / define / conditional compilation の情報を `source_digest` として出力できる
- Step 06 の Function Locator が使う `masked_source` を提供できる

---

## 3. スコープ

### 3.1 実装対象

Step 05 で実装するもの:

1. C source reader
   - encoding fallback
   - 改行保持
   - line number mapping
   - source hash 計算

2. Comment masker
   - `/* ... */`
   - `// ...`
   - 未終端コメント warning
   - コメント内改行保持

3. String / char literal masker
   - `"..."`
   - `'x'`
   - escape sequence
   - line continuation
   - 未終端 literal warning

4. Preprocessor scanner
   - `#include`
   - `#define`
   - `#undef`
   - `#if`
   - `#ifdef`
   - `#ifndef`
   - `#elif`
   - `#else`
   - `#endif`
   - `#pragma`
   - `#error`

5. Conditional block tracker
   - nest level
   - directive stack
   - malformed conditional warning
   - build_context defines を使った簡易 active/inactive 推定

6. Token extractor の下地
   - identifier
   - keyword
   - number
   - operator
   - punctuation
   - line / column

7. Reports
   - `source_digest.json`
   - `source_digest.md`
   - `masked_source.c` optional output

8. Tests
   - comments
   - strings
   - char literals
   - preprocessor
   - conditional compilation
   - line mapping
   - cp932 / shift_jis
   - VC6風コード fixture

### 3.2 対象外

Step 05 では以下を対象外とする。

- 関数範囲の確定
- 関数シグネチャ解析
- グローバル変数アクセス解析
- 外部呼び出し解析
- 分岐・条件網羅候補生成
- 境界値・同値クラス候補生成
- include ファイルの完全再帰展開
- Cプリプロセッサの完全実装
- macro 展開の完全実装
- typedef / struct / enum の意味解析
- VC6 compiler と同一の条件コンパイル判定

Step 05 では、後続解析に必要な安全な前処理情報を作ることに限定する。

---

## 4. 基本方針

### 4.1 完全なCコンパイラは作らない

本ツールの目的は、関数単位テスト支援に必要な情報を現実的に集めることである。
Step 05 では、完全な C front-end や preprocessor は作らない。

方針:

- 文字列・コメント・プリプロセッサで後続解析が壊れることを防ぐ
- C90 / VC6 の実用コードを壊れにくく扱う
- 不明なものは warning として残す
- 後続 Step で必要になった解析だけ増やす

### 4.2 行番号を最優先で保持する

テスト設計やエビデンスでは、元ソースの行番号が重要である。
そのため、mask処理では行数を変えない。

方針:

- コメントを空白へ置換しても改行は保持する
- 文字列を空白または placeholder へ置換しても列幅をできるだけ保持する
- token には source line / column を付与する
- report には元ファイルpath、hash、行番号を含める

### 4.3 build_context は使うが過信しない

Step 04 で得た `build_context` の define / include / forced include は、Step 05 の参考情報として使う。
ただし、VC6 と完全一致するプリプロセッサ評価は行わない。

利用する情報:

- defines
- include_dirs
- forced_includes
- pch_header
- raw compiler options

利用方針:

- `#ifdef NAME` は defines に存在すれば active 候補にする
- `#ifndef NAME` は defines に存在しなければ active 候補にする
- 複雑な `#if` 式は評価しないか、limited evaluation とする
- 判定不能箇所は `unknown_active_state` として残す

---

## 5. 入力と出力

### 5.1 入力

主入力:

- 対象 `.c` ファイル
- Step 04 の `build_context`

入力例:

```json
{
  "source": "D:/work/product/src/control.c",
  "configuration": "Control - Win32 Debug",
  "compiler": {
    "defines": ["WIN32", "_DEBUG", "_CONSOLE"],
    "include_dirs": [
      {
        "raw": ".\\include",
        "absolute": "D:/work/product/include",
        "exists": true
      }
    ],
    "forced_includes": [],
    "precompiled_header": {
      "mode": "use",
      "header": "stdafx.h"
    },
    "raw_options": []
  }
}
```

### 5.2 出力

Step 05 の主要出力は `source_digest` と `masked_source` である。

```text
workspace/
  Control_Update/
    reports/
      source_digest.json
      source_digest.md
    intermediate/
      masked_source.c
      token_stream.json
```

`source_digest.json` は Step 06 以降の入力になる。

---

## 6. データモデル設計

### 6.1 SourceReadResult

```python
@dataclass
class SourceReadResult:
    path: Path
    encoding: str
    text: str
    newline: str | None
    sha256: str
    line_count: int
    warnings: list[SourceWarning]
```

役割:

- ソース読み込み結果を保持する
- encoding と hash をエビデンスとして残す

### 6.2 MaskedSource

```python
@dataclass
class MaskedSource:
    original_path: Path
    original_text: str
    masked_text: str
    line_map: list[LineMapEntry]
    masked_ranges: list[MaskedRange]
    warnings: list[SourceWarning]
```

役割:

- 後続解析用の `masked_text` を提供する
- 元テキストとの対応を保持する

### 6.3 MaskedRange

```python
@dataclass
class MaskedRange:
    kind: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int
    preview: str | None
```

`kind` 候補:

| kind | 内容 |
|---|---|
| `block_comment` | `/* ... */` |
| `line_comment` | `// ...` |
| `string_literal` | `"..."` |
| `char_literal` | `'x'` |
| `line_continuation` | `\` による継続 |

### 6.4 LineMapEntry

```python
@dataclass
class LineMapEntry:
    original_line: int
    masked_line: int
    original_start_offset: int
    masked_start_offset: int
```

役割:

- token や warning を元ソース行へ戻す
- Markdown report の根拠行に使う

### 6.5 PreprocessorDirective

```python
@dataclass
class PreprocessorDirective:
    kind: str
    line_number: int
    column: int
    raw: str
    argument: str
    active_state: str
    nesting_level: int
```

`kind` 候補:

- `include`
- `define`
- `undef`
- `if`
- `ifdef`
- `ifndef`
- `elif`
- `else`
- `endif`
- `pragma`
- `error`
- `unknown`

`active_state` 候補:

| active_state | 意味 |
|---|---|
| `active` | build_context から有効と推定 |
| `inactive` | build_context から無効と推定 |
| `unknown` | 判定不能 |
| `not_evaluated` | 評価対象外 |

### 6.6 MacroDefinition

```python
@dataclass
class MacroDefinition:
    name: str
    value: str | None
    parameters: list[str] | None
    line_number: int
    is_function_like: bool
    active_state: str
```

役割:

- `#define` の一覧を保持する
- Step 06 以降で function-like macro による関数定義誤認を避けるために使う

### 6.7 IncludeDirective

```python
@dataclass
class IncludeDirective:
    target: str
    style: str
    line_number: int
    resolved_candidates: list[Path]
    exists: bool | None
    active_state: str
```

`style` 候補:

- `quote`: `#include "file.h"`
- `angle`: `#include <stdio.h>`
- `macro`: `#include CONFIG_HEADER`
- `unknown`

### 6.8 LexToken

```python
@dataclass
class LexToken:
    kind: str
    value: str
    line_number: int
    column: int
    start_offset: int
    end_offset: int
```

`kind` 候補:

- `identifier`
- `keyword`
- `number`
- `operator`
- `punctuation`
- `preprocessor`
- `unknown`

Step 05 では token stream は最小限でよい。
Step 06 の Function Locator が必要とする `{` / `}` / `(` / `)` / `;` / identifier を安定して拾えることを優先する。

### 6.9 SourceDigest

```python
@dataclass
class SourceDigest:
    source: SourceReadResult
    masked_source_path: Path | None
    directives: list[PreprocessorDirective]
    includes: list[IncludeDirective]
    macros: list[MacroDefinition]
    tokens: list[LexToken]
    warnings: list[SourceWarning]
```

### 6.10 SourceWarning

```python
@dataclass
class SourceWarning:
    code: str
    message: str
    line_number: int | None = None
    column: int | None = None
    text: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `encoding_fallback` | 文字コードfallbackが発生した |
| `unterminated_block_comment` | `/*` が閉じていない |
| `unterminated_string_literal` | 文字列リテラルが閉じていない |
| `unterminated_char_literal` | 文字定数が閉じていない |
| `malformed_preprocessor_directive` | `#` 行を解釈できない |
| `conditional_stack_underflow` | `#endif` などの対応が崩れている |
| `conditional_stack_unclosed` | `#if` 系が閉じていない |
| `unknown_active_state` | 条件コンパイルの有効性を判定できない |
| `include_not_found` | include候補が見つからない |
| `macro_redefinition` | macro再定義候補 |
| `non_ascii_identifier_candidate` | 非ASCII識別子候補 |

---

## 7. Masker 設計

### 7.1 状態機械

Comment / string / char masking は、正規表現だけで処理しない。
Cソースを1文字ずつ走査する state machine とする。

状態候補:

| state | 内容 |
|---|---|
| `normal` | 通常コード |
| `line_comment` | `//` コメント内 |
| `block_comment` | `/* ... */` コメント内 |
| `string_literal` | `"..."` 内 |
| `char_literal` | `'x'` 内 |
| `escape_in_string` | 文字列内escape直後 |
| `escape_in_char` | 文字定数内escape直後 |

### 7.2 マスク方針

- 改行はそのまま残す
- コメント本文は空白へ置換する
- 文字列本文は空白または `""` 相当へ置換する
- 文字定数本文は空白または `' '` 相当へ置換する
- 元の長さを可能な限り維持する
- マスク範囲は `MaskedRange` に記録する

例:

入力:

```c
if (x == '{') { /* comment } */
    printf("}");
}
```

masked:

```c
if (x == ' ') {                
    printf(" ");
}
```

これにより、コメントや文字列内の `}` を波括弧対応に使わない。

### 7.3 line continuation

Cプリプロセッサでは、行末 `\` による継続がある。
Step 05 では以下を扱う。

- preprocessor directive の継続行
- string literal の継続行
- macro定義の継続行

方針:

- 元の行は保持する
- logical line と physical line の対応を `LineMapEntry` または directive metadata に保持する
- macro定義の解析では continuation を考慮する

---

## 8. Preprocessor Scanner 設計

### 8.1 directive 抽出

コメント・文字列をマスクした後、行頭の `#` を探す。

対象例:

```c
#include "control.h"
#include <stdio.h>
#define MAX_VALUE 100
#define IS_VALID(x) ((x) > 0)
#ifdef _DEBUG
#ifndef PRODUCT
#if defined(WIN32) && !defined(NDEBUG)
#else
#endif
```

抽出する情報:

- directive kind
- raw line
- argument
- line number
- nesting level
- active_state

### 8.2 include 解決

Step 05 では include の完全再帰展開はしない。
ただし include directive の候補解決は行う。

方針:

- quote include は、まず対象ソースのディレクトリを探索する
- 次に build_context.include_dirs を探索する
- angle include は build_context.include_dirs を探索するが、標準ヘッダは存在確認不能でも warningにしすぎない
- macro include は resolved unknown として扱う
- forced include は `source_digest` に別枠で記録してもよい

### 8.3 define 抽出

`#define` は以下に分類する。

| 種別 | 例 |
|---|---|
| object-like | `#define MAX 10` |
| function-like | `#define MIN(a,b) ((a)<(b)?(a):(b))` |
| empty | `#define FEATURE_ENABLED` |
| multiline | `#define MACRO(x) \\` |

Step 05 では macro の完全展開は行わない。
ただし function-like macro は Step 06 以降で関数定義と誤認しやすいため、必ず一覧化する。

### 8.4 conditional compilation の簡易評価

`build_context.defines` を使って、以下を限定的に評価する。

対応するもの:

- `#ifdef NAME`
- `#ifndef NAME`
- `#if defined(NAME)`
- `#if !defined(NAME)`
- `#if 0`
- `#if 1`

対応しない、または unknown とするもの:

- 複雑な算術式
- macro関数を含む式
- include済みヘッダのdefineに依存する式
- VC6固有macroの評価

active_state の方針:

- 確実に判定できる場合のみ active / inactive
- それ以外は unknown
- unknown部分のコードは完全除外せず、後続で注意できるよう metadata を付与する

---

## 9. Token Extractor 設計

### 9.1 目的

Step 05 の token extractor は、完全なC lexerではない。
Step 06 の Function Locator が以下を安定して使えるようにするための下地である。

- identifier
- keyword
- `(` / `)`
- `{` / `}`
- `;`
- `,`
- `*`
- `[` / `]`
- operator

### 9.2 キーワード候補

C90 / VC6 を考慮し、以下を keyword とする。

```text
auto break case char const continue default do double else enum extern float for goto if int long register return short signed sizeof static struct switch typedef union unsigned void volatile while
```

VC6で見かける可能性がある拡張語は `identifier` または `extension_keyword` として扱う。

例:

- `__inline`
- `__declspec`
- `__stdcall`
- `__cdecl`
- `__fastcall`
- `BOOL`
- `DWORD`

この段階では意味解析しない。

### 9.3 token 出力制限

大きなソースでは token stream が巨大になる。
そのため、既定では `source_digest.json` に全tokenを入れすぎない。

方針:

- 内部処理では token stream を保持する
- JSON出力では `--emit-token-stream` 相当の指定がある場合のみ全tokenを出す
- 通常の `source_digest.json` には token summary を入れる

---

## 10. CLI 接続設計

### 10.1 analyze-function への partial 接続

Step 05 では、`analyze-function` の完全実装はまだ行わない。
ただし、Step 04 の source membership と Step 05 の source digest を使って、以下の partial 出力を返せるようにする。

```bat
unit-test-runner analyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Control - Win32 Debug" ^
  --out D:\work\unit_test_workspace\Control_Update
```

Step 05 の応答方針:

- `.dsw` / `.dsp` から source membership を取得する
- build_context を取得する
- 対象 `.c` を読み込む
- masked_source と source_digest を生成する
- 関数 `Control_Update` の探索は Step 06 と明記する
- status は `partial` とする
- exit code は `0` とする

### 10.2 開発者向け inspect-source コマンド案

正式CLIに追加するかは実装時判断とするが、開発中は以下のような内部コマンドがあると便利である。

```bat
unit-test-runner inspect-source ^
  --source D:\work\product\src\control.c ^
  --build-context D:\work\unit_test_workspace\Control_Update\reports\build_context.json ^
  --out D:\work\unit_test_workspace\Control_Update\reports\source_digest.json
```

扱い:

- 公開コマンドにする場合は Step 02 の CLI コマンド体系へ追記する
- 非公開にする場合は `tests` と内部 usecase のみで使う
- VS Code adapter から直接使う予定があるなら公開を検討する

Step 05 計画では、`inspect-source` は必須ではない。
必須なのは内部 usecase と `analyze-function` partial 接続である。

---

## 11. Report 設計

### 11.1 source_digest.json

例:

```json
{
  "schema_version": "0.1",
  "source": {
    "path": "D:/work/product/src/control.c",
    "encoding": "cp932",
    "sha256": "...",
    "line_count": 240
  },
  "masking": {
    "masked_source_path": "intermediate/masked_source.c",
    "masked_ranges": [
      {
        "kind": "block_comment",
        "start_line": 12,
        "start_column": 1,
        "end_line": 14,
        "end_column": 3
      }
    ]
  },
  "preprocessor": {
    "includes": [
      {
        "target": "control.h",
        "style": "quote",
        "line_number": 1,
        "exists": true,
        "active_state": "active"
      }
    ],
    "macros": [
      {
        "name": "MAX_VALUE",
        "value": "100",
        "line_number": 10,
        "is_function_like": false,
        "active_state": "active"
      }
    ],
    "directives": []
  },
  "token_summary": {
    "identifier_count": 120,
    "keyword_count": 40,
    "punctuation_count": 180
  },
  "warnings": []
}
```

### 11.2 source_digest.md

内容例:

```markdown
# Source Digest Report

## Source

- Path: D:/work/product/src/control.c
- Encoding: cp932
- Line Count: 240
- SHA-256: ...

## Masking Summary

| Kind | Count |
|---|---:|
| block_comment | 4 |
| line_comment | 18 |
| string_literal | 22 |
| char_literal | 3 |

## Includes

| Line | Target | Style | Exists | Active |
|---:|---|---|---|---|
| 1 | control.h | quote | yes | active |

## Macros

| Line | Name | Kind | Active |
|---:|---|---|---|
| 10 | MAX_VALUE | object-like | active |

## Conditional Compilation

| Line | Directive | Nesting | Active |
|---:|---|---:|---|
| 20 | ifdef _DEBUG | 1 | active |

## Warnings

なし
```

### 11.3 masked_source.c

`masked_source.c` は中間生成物であり、本番コードではない。

用途:

- Function Locator の入力確認
- CODEX / 開発者による debug
- テスト fixture の期待値確認

注意:

- masked source はビルド対象ではない
- masked source を本番リポジトリへ出力しない
- 外部ワークスペース配下にのみ生成する

---

## 12. テスト計画

### 12.1 fixture 構成

```text
tests/
  fixtures/
    c_sources/
      comments/
        block_comment.c
        line_comment.c
        unterminated_block_comment.c
      literals/
        string_literal.c
        char_literal.c
        escaped_literal.c
        line_continuation_string.c
      preprocessor/
        includes.c
        defines.c
        conditional_simple.c
        conditional_nested.c
        conditional_malformed.c
      vc6_style/
        windows_types.c
        calling_convention.c
        pch_include.c
      encoding/
        cp932_comments.c
      integration/
        control_sample.c
```

### 12.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| SRC-001 | block comment | `/* } */` | `}` が masked_text に残らない |
| SRC-002 | line comment | `// }` | `}` が masked_text に残らない |
| SRC-003 | comment newline | 複数行comment | 行数が変わらない |
| SRC-004 | unterminated comment | `/*` 未終端 | warning `unterminated_block_comment` |
| SRC-005 | string literal | `"}"` | `}` が構文tokenにならない |
| SRC-006 | escaped quote | `"a\"b"` | string範囲を正しく認識 |
| SRC-007 | char literal | `'}'` | `}` が構文tokenにならない |
| SRC-008 | escaped char | `'\\''` | char範囲を正しく認識 |
| SRC-009 | line continuation | `#define X \\` | logical directive として扱える |
| SRC-010 | include quote | `#include "a.h"` | IncludeDirective style quote |
| SRC-011 | include angle | `#include <stdio.h>` | IncludeDirective style angle |
| SRC-012 | define object | `#define A 1` | MacroDefinition object-like |
| SRC-013 | define function | `#define F(x)` | MacroDefinition function-like |
| SRC-014 | ifdef active | build_context definesあり | active_state active |
| SRC-015 | ifndef inactive | build_context definesあり | active_state inactive |
| SRC-016 | if 0 | `#if 0` | active_state inactive |
| SRC-017 | nested conditional | nested ifdef | nesting level を保持 |
| SRC-018 | malformed endif | `#endif` 過多 | warning `conditional_stack_underflow` |
| SRC-019 | unclosed conditional | `#if` 未close | warning `conditional_stack_unclosed` |
| SRC-020 | token punctuation | `{}` | punctuation token 抽出 |
| SRC-021 | token identifier | `static int f` | identifier / keyword 抽出 |
| SRC-022 | cp932 | 日本語コメント | 読み込み成功、encoding記録 |
| SRC-023 | line map | 任意fixture | original line と masked line が対応 |
| SRC-024 | source digest json | integration | JSON parse 可能 |
| SRC-025 | analyze-function partial | dsw/dsp/source | source_digest 生成、status partial |

### 12.3 テスト方針

- Masker は小さな文字列入力で単体テストする
- file reader は fixture file でテストする
- preprocessor scanner は masked_text を入力にしてテストする
- token extractor は comment/string 除去後のテキストでテストする
- integration test では Step 04 の build_context fixture と組み合わせる
- JSON は `json.loads()` で検証する
- 行番号は snapshot ではなく明示assertで検証する

---

## 13. 実装タスク分解

### Task 05-01: Source model 定義

成果物:

- `src/unit_test_runner/c_analyzer/source_models.py`
- `SourceReadResult`
- `MaskedSource`
- `MaskedRange`
- `LineMapEntry`
- `SourceDigest`
- `SourceWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 05-02: Source reader

成果物:

- `src/unit_test_runner/c_analyzer/source_reader.py`
- encoding fallback
- newline検出
- sha256計算
- line_count計算

完了条件:

- utf-8 / cp932 fixture を読み込める
- `SourceReadResult` を返せる

### Task 05-03: Comment masker

成果物:

- `src/unit_test_runner/c_analyzer/masker.py`
- block comment masking
- line comment masking
- warning生成
- line number保持

完了条件:

- SRC-001 から SRC-004 が通る

### Task 05-04: String / char literal masker

成果物:

- string literal masking
- char literal masking
- escape handling
- unterminated literal warning

完了条件:

- SRC-005 から SRC-008 が通る

### Task 05-05: Line continuation handling

成果物:

- logical line helper
- directive continuation handling
- macro continuation handling

完了条件:

- SRC-009 が通る

### Task 05-06: Preprocessor scanner

成果物:

- `src/unit_test_runner/c_analyzer/preprocessor.py`
- directive 抽出
- include 抽出
- define 抽出
- directive model 化

完了条件:

- SRC-010 から SRC-013 が通る

### Task 05-07: Conditional block tracker

成果物:

- ifdef / ifndef / if 0 / if 1 の簡易評価
- nesting level
- stack warning
- active_state 付与

完了条件:

- SRC-014 から SRC-019 が通る

### Task 05-08: Token extractor

成果物:

- `src/unit_test_runner/c_analyzer/tokens.py`
- identifier / keyword / punctuation / operator 抽出
- line / column 付与

完了条件:

- SRC-020 から SRC-021 が通る

### Task 05-09: Source digest writer

成果物:

- `src/unit_test_runner/c_analyzer/source_digest.py`
- `reports/source_digest_markdown.py`
- `source_digest.json`
- `source_digest.md`
- optional `masked_source.c`

完了条件:

- SRC-024 が通る

### Task 05-10: analyze-function partial 接続

成果物:

- Step 04 の source membership / build_context と接続
- source digest 生成
- status `partial`
- Step 06 が必要である旨の message

完了条件:

- SRC-025 が通る

### Task 05-11: fixture / test 整備

成果物:

- `tests/fixtures/c_sources/...`
- `tests/unit/test_source_reader.py`
- `tests/unit/test_masker.py`
- `tests/unit/test_preprocessor.py`
- `tests/unit/test_tokens.py`
- `tests/unit/test_source_digest.py`
- `tests/unit/test_analyze_function_partial_source_digest.py`

完了条件:

- SRC-001 から SRC-025 が通る

---

## 14. 受け入れ基準

Step 05 は、以下をすべて満たしたら完了とする。

1. `.c` ファイルを encoding fallback 付きで読み込める
2. source hash、encoding、line count を記録できる
3. block comment / line comment を行番号を壊さず mask できる
4. string literal / char literal を escape 考慮付きで mask できる
5. コメント・文字列内の `{` / `}` を後続解析用tokenから除外できる
6. 未終端コメント・未終端literalを warning として返せる
7. `#include` を抽出できる
8. `#define` を object-like / function-like として抽出できる
9. `#ifdef` / `#ifndef` / `#if 0` / `#if 1` の簡易active_stateを付与できる
10. conditional nesting level を保持できる
11. conditional stack 不整合を warning として返せる
12. identifier / keyword / punctuation token を抽出できる
13. token に line / column を付与できる
14. `source_digest.json` を生成できる
15. `source_digest.md` を生成できる
16. optionalで `masked_source.c` を生成できる
17. Step 04 の `build_context` を入力として利用できる
18. `analyze-function` が Step 05 時点では source digest 生成まで進み、status `partial` を返せる
19. Step 06 の Function Locator に渡せる `masked_text` / token stream がある
20. C関数範囲確定やシグネチャ解析へ踏み込みすぎていない

---

## 15. 成果物

Step 05 の成果物は以下とする。

```text
src/
  unit_test_runner/
    c_analyzer/
      __init__.py
      source_models.py
      source_reader.py
      masker.py
      preprocessor.py
      tokens.py
      source_digest.py
    reports/
      source_digest_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    c_sources/
      comments/
      literals/
      preprocessor/
      vc6_style/
      encoding/
      integration/
  unit/
    test_source_reader.py
    test_masker.py
    test_preprocessor.py
    test_tokens.py
    test_source_digest.py
    test_analyze_function_partial_source_digest.py
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/vc6/source_membership.py` 必要な場合のみ
- `src/unit_test_runner/utils/encoding.py` 必要な場合のみ
- `src/unit_test_runner/utils/paths.py` 必要な場合のみ

---

## 16. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| 正規表現だけで壊れる | コメント・文字列・escapeが複雑 | state machine で1文字ずつ走査する |
| 行番号がずれる | コメント削除やlogical line化でエビデンス行がずれる | 改行保持を必須にし、LineMapEntryを持つ |
| `//` コメントの扱い | C90では標準外だがVC6コードでは使われる可能性がある | VC6実用コードとして対応する |
| 条件コンパイル評価の誤判定 | 完全なpreprocessorではない | active/inactiveは限定評価し、不明はunknownにする |
| macro展開要求が膨らむ | function-like macro 展開までやりたくなる | Step05では抽出のみ、展開はしない |
| token stream巨大化 | 大規模ファイルでJSONが重くなる | 既定ではsummaryのみ、詳細token出力は任意にする |
| 日本語コメント | cp932 / shift_jis で読み込みに失敗する | encoding fallbackとfixtureを用意する |
| Step06責務の侵食 | 関数ロケータまで実装したくなる | Step05は前処理・mask・token下地に限定する |

---

## 17. Step 06 への接続

Step 05 完了後、Step 06 では Function Locator を実装する。
Step 06 は、Step 05 の `masked_text` と token stream を利用して、指定関数の範囲を特定する。

想定接続:

```python
source_digest = build_source_digest(source_path, build_context)
function_location = locate_function(
    masked_text=source_digest.masked_source.masked_text,
    tokens=source_digest.tokens,
    function_name="Control_Update",
)
```

Step 06 で使う情報:

- masked_text
- token stream
- line map
- function-like macro一覧
- conditional active_state
- source warnings

Step 05 の責務は、Function Locator がコメントや文字列に惑わされず、元ソース行番号へ戻れる材料を作ることである。

---

## 18. まとめ

Step 05 は、C関数解析そのものではなく、関数解析の前段となる C Source Lexer / Masker である。

このステップにより、コメント、文字列、文字定数、プリプロセッサ、条件コンパイル、include、define、token下地、行番号対応を整理し、Step 06 の Function Locator が安全に動作できる状態を作る。

VC6 / C90 の実用コードを壊れにくく扱うため、完全なCコンパイラを作るのではなく、限定的かつ保守的な解析を行い、判定不能箇所は warning として残す。

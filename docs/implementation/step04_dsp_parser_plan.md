# Step 04: DSP Parser 実装計画

作成日: 2026-07-04  
状態: Draft v0.1  
対象リポジトリ: `katamor1/unitTestRunner`  
製造担当想定: CODEX  
前提文書:

- `docs/adr/0001-cli-layer-language-selection.md`
- `docs/implementation/step02_cli_entry_point_plan.md`
- `docs/implementation/step03_dsw_parser_plan.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第4ステップとして **VC6 Project File `.dsp` を解析する DSP Parser** を実装するための計画である。

Step 03 では、`.dsw` から `.dsp` プロジェクト参照、プロジェクト名、プロジェクト間依存関係、`.dsp` 絶対パス候補を抽出した。
Step 04 では、Step 03 で得た `.dsp` 群を解析し、対象 `.c` がどの VC6 プロジェクト・構成に所属するかを判定し、関数単位テストの前提となる build context を取得する。

Step 04 で主に実処理化するコマンドは以下である。

```bat
unit-test-runner map-source ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c

unit-test-runner discover-projects ^
  --workspace D:\work\product ^
  --out D:\work\unit_test_workspace\reports\projects.json
```

`analyze-function` は Step 04 ではまだ本格実装しない。
ただし、Step 04 の成果である `source_membership` と `build_context` を使って、Step 05 以降で関数解析へ進める状態を作る。

---

## 2. 目的

Step 04 の目的は、`.dsp` ファイルから **対象 `.c` の所属プロジェクトと構成別ビルド条件** を取得することである。

具体的には、以下を実現する。

- `.dsp` ファイルを読み込める
- `.dsp` のプロジェクト名を抽出できる
- 構成名、例: `Win32 Debug` / `Win32 Release` を抽出できる
- source file list と header/resource file list を抽出できる
- 対象 `.c` がどの `.dsp` に含まれるか判定できる
- 構成別の `# ADD CPP` / `# ADD BASE CPP` 行を抽出できる
- `/D` define を抽出できる
- `/I` include directory を抽出できる
- `/FI` forced include を抽出できる
- `/Yu` / `/Yc` precompiled header 設定を抽出できる
- `/ML` / `/MT` / `/MD` 系 runtime library 指定を抽出できる
- `/W` warning level、`/Od` / `/O2` など主要 compiler option を保持できる
- `.dsw` + `.dsp` の情報から `map-source` を実用レベルにできる
- Step 05 以降の C function analyzer に渡す `build_context` を定義できる

---

## 3. スコープ

### 3.1 実装対象

Step 04 で実装するもの:

1. DSP Parser 本体
   - `.dsp` テキスト読み込み
   - エンコーディング fallback
   - project name 抽出
   - configuration block 抽出
   - source file entry 抽出
   - group 情報の粗抽出
   - compiler option 行抽出
   - per-configuration build settings 抽出

2. Build Context 抽出
   - defines
   - include directories
   - forced includes
   - precompiled header settings
   - runtime library option
   - warning level
   - optimization/debug related option
   - raw compiler options
   - unresolved macro variables

3. Source Membership 判定
   - `.c` がどの `.dsp` に含まれるか判定
   - 相対パス、絶対パス、大文字小文字差異を吸収
   - 同一 `.c` が複数 `.dsp` に所属する場合は複数候補として返す
   - 構成別 build context を紐付ける

4. CLI 接続
   - `map-source` の partial 実装を実用実装へ更新
   - `discover-projects` の出力に DSP 概要を追加できるようにする
   - `analyze-function` から将来使うための内部 usecase を用意する

5. レポート出力
   - JSON
   - Markdown
   - 標準出力サマリ

6. テスト
   - 最小 `.dsp` fixture
   - Debug / Release 構成 fixture
   - include / define fixture
   - forced include / PCH fixture
   - source membership fixture
   - 複数プロジェクト所属 fixture
   - 空白パス fixture
   - macro variable fixture
   - malformed fixture

### 3.2 対象外

Step 04 では以下を対象外とする。

- C 関数ロケータ
- 関数シグネチャ解析
- グローバル変数アクセス解析
- 分岐・条件解析
- 境界値・同値クラス候補生成
- テストハーネス生成
- スタブ生成
- VC6 / nmake / cl.exe 実行
- `.vcproj` 以降の Visual Studio project 解析
- MFC resource の詳細解析
- custom build step の完全再現

ただし、将来の build-probe で必要になるため、custom build step の存在は warning または metadata として保持する。

---

## 4. DSP ファイルの扱い

### 4.1 想定する基本構造

VC6 の `.dsp` は、概ね以下のようなテキスト構造を持つ。

```text
# Microsoft Developer Studio Project File - Name="Control" - Package Owner=<4>
# Microsoft Developer Studio Generated Build File, Format Version 6.00

!MESSAGE This is not a valid makefile. To build this project using NMAKE,
!MESSAGE use the Export Makefile command and run
!MESSAGE NMAKE /f "Control.mak".

# TARGTYPE "Win32 (x86) Console Application" 0x0103

CFG=Control - Win32 Debug
!MESSAGE Possible choices for configuration are:
!MESSAGE "Control - Win32 Release" (based on "Win32 (x86) Console Application")
!MESSAGE "Control - Win32 Debug" (based on "Win32 (x86) Console Application")

!IF  "$(CFG)" == "Control - Win32 Release"

# ADD BASE CPP /nologo /W3 /GX /O2 /D "WIN32" /D "NDEBUG" /D "_CONSOLE" /YX /FD /c
# ADD CPP /nologo /W3 /GX /O2 /I ".\include" /D "WIN32" /D "NDEBUG" /D "_CONSOLE" /FD /c

!ELSEIF  "$(CFG)" == "Control - Win32 Debug"

# ADD BASE CPP /nologo /W3 /Gm /GX /ZI /Od /D "WIN32" /D "_DEBUG" /D "_CONSOLE" /YX /FD /GZ /c
# ADD CPP /nologo /W3 /Gm /GX /ZI /Od /I ".\include" /D "WIN32" /D "_DEBUG" /D "_CONSOLE" /Yu"stdafx.h" /FD /GZ /c

!ENDIF

# Begin Target

# Name "Control - Win32 Release"
# Name "Control - Win32 Debug"

# Begin Group "Source Files"

# Begin Source File
SOURCE=.\src\control.c
# End Source File

# Begin Source File
SOURCE=.\src\helper.c
# End Source File

# End Group

# Begin Group "Header Files"

# Begin Source File
SOURCE=.\include\control.h
# End Source File

# End Group

# End Target
```

Step 04 では、このうち以下を主に解析する。

- Project File header
- `CFG=`
- `!MESSAGE "..."` による possible configuration
- `!IF "$(CFG)" == "..."`
- `!ELSEIF "$(CFG)" == "..."`
- `# ADD CPP`
- `# ADD BASE CPP`
- `# Begin Group`
- `# Begin Source File`
- `SOURCE=`
- `# Name "..."`

### 4.2 DSP 解析の基本方針

`.dsp` は makefile 風のテキストであるが、完全な makefile parser は作らない。
VC6 が生成する典型的な `.dsp` を実用的に解析する。

方針:

- 行単位 parser と状態管理で実装する
- configuration block ごとに compiler option を保持する
- source file entry は group context とともに保持する
- 未知行は原則無視するが、解析に影響しそうな行は warning に残す
- raw line と line number を保持して、後から解析ルールを改善できるようにする
- 失敗時に即停止せず、可能な限り partial result を返す

---

## 5. データモデル設計

### 5.1 DspProject

```python
@dataclass
class DspProject:
    name: str
    path: Path
    root_dir: Path
    format_version: str | None
    target_type: str | None
    configurations: list[DspConfiguration]
    files: list[DspFileEntry]
    warnings: list[DspParseWarning]
```

役割:

- `.dsp` 全体の解析結果を保持する
- source membership と build context の入力になる

### 5.2 DspConfiguration

```python
@dataclass
class DspConfiguration:
    full_name: str
    project_name: str | None
    platform: str | None
    name: str | None
    compiler_base_options: list[str]
    compiler_options: list[str]
    build_settings: DspBuildSettings
    line_number: int | None
```

例:

- full_name: `Control - Win32 Debug`
- project_name: `Control`
- platform: `Win32`
- name: `Debug`

### 5.3 DspBuildSettings

```python
@dataclass
class DspBuildSettings:
    defines: list[str]
    include_dirs: list[PathLikeValue]
    forced_includes: list[str]
    pch_mode: str | None
    pch_header: str | None
    runtime_library: str | None
    warning_level: str | None
    optimization: str | None
    debug_info: str | None
    raw_options: list[str]
    unresolved_macros: list[str]
```

`PathLikeValue` は raw / normalized / absolute を保持できる小さなモデルとする。

```python
@dataclass
class PathLikeValue:
    raw: str
    normalized: str
    absolute: Path | None
    exists: bool | None
```

### 5.4 DspFileEntry

```python
@dataclass
class DspFileEntry:
    source_raw: str
    source_path: Path
    source_path_absolute: Path
    file_kind: str
    group: str | None
    exists: bool
    line_number: int
```

`file_kind` の候補:

| file_kind | 条件 |
|---|---|
| `source` | `.c`, `.cpp`, `.cxx`, `.cc` |
| `header` | `.h`, `.hpp`, `.inl` |
| `resource` | `.rc`, `.ico`, `.bmp`, `.cur` |
| `def` | `.def` |
| `other` | その他 |

本プロジェクトでは C90 / VC6 の `.c` を主対象にするが、`.dsp` には `.cpp` や resource が混在し得るため、分類だけは保持する。

### 5.5 DspParseWarning

```python
@dataclass
class DspParseWarning:
    code: str
    message: str
    line_number: int | None = None
    line_text: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `encoding_fallback` | 文字コードfallbackが発生した |
| `malformed_project_header` | project header を解析できない |
| `malformed_configuration` | configuration 行を解析できない |
| `compiler_options_without_configuration` | 構成外に compiler option が見つかった |
| `malformed_source_entry` | SOURCE 行を解析できない |
| `missing_source_file` | SOURCE 参照先が存在しない |
| `unresolved_macro` | `$(VAR)` など未解決macroがある |
| `custom_build_step_detected` | custom build step が存在する |
| `unknown_line` | 未知行を検出した |

### 5.6 SourceMembership

```python
@dataclass
class SourceMembership:
    source: Path
    matches: list[SourceMembershipMatch]
    warnings: list[DspParseWarning]
```

```python
@dataclass
class SourceMembershipMatch:
    dsw_path: Path | None
    dsp_path: Path
    project_name: str
    source_entry: DspFileEntry
    configurations: list[DspConfiguration]
```

役割:

- `map-source` の中核出力になる
- 同一 `.c` が複数 `.dsp` に所属する状況を表現できる

---

## 6. パーサ設計

### 6.1 実装ファイル

```text
src/
  unit_test_runner/
    vc6/
      __init__.py
      dsp_models.py
      dsp_parser.py
      dsp_options.py
      source_membership.py
    reports/
      dsp_markdown.py
      source_membership_markdown.py
    cli/
      commands.py
```

既存または同時利用するファイル:

```text
src/
  unit_test_runner/
    vc6/
      dsw_models.py
      dsw_parser.py
    utils/
      encoding.py
      paths.py
```

### 6.2 処理フロー

```text
parse_dsp(path)
  1. path を絶対パス化
  2. ファイル存在確認
  3. encoding fallback 付きで読み込み
  4. 行単位に分割
  5. project header から project name を抽出
  6. format version を抽出
  7. target type を抽出
  8. possible configuration を抽出
  9. !IF / !ELSEIF の CFG block を検出
 10. # ADD BASE CPP / # ADD CPP を抽出
 11. compiler options を token 化
 12. DspBuildSettings に変換
 13. # Begin Group / # End Group で current group を保持
 14. SOURCE= 行を DspFileEntry として抽出
 15. source path を dsp root 基準で絶対化
 16. source file の存在確認
 17. warnings を整理
 18. DspProject を返す
```

### 6.3 configuration 抽出

対象行例:

```text
!MESSAGE "Control - Win32 Release" (based on "Win32 (x86) Console Application")
!MESSAGE "Control - Win32 Debug" (based on "Win32 (x86) Console Application")
!IF  "$(CFG)" == "Control - Win32 Release"
!ELSEIF  "$(CFG)" == "Control - Win32 Debug"
# Name "Control - Win32 Debug"
```

方針:

- `!IF` / `!ELSEIF` の CFG 条件を最も信頼する
- `# Name` は補助情報として使う
- `!MESSAGE` の possible choices は補助情報として使う
- 同じ configuration 名が複数箇所に出ても重複排除する

configuration 名の分割方針:

```text
Control - Win32 Debug
```

- ` - ` の左側を project_name 候補とする
- 右側の先頭 token を platform 候補、残りを name 候補とする
- 分割不能な場合は full_name のみ保持する

### 6.4 compiler option tokenization

対象行例:

```text
# ADD CPP /nologo /W3 /Gm /GX /ZI /Od /I ".\include" /I "..\common\include" /D "WIN32" /D "_DEBUG" /D "_CONSOLE" /FI"config.h" /Yu"stdafx.h" /FD /GZ /c
```

token化の注意点:

- quote された値を壊さない
- `/I ".\include"` と `/I".\include"` の両方を扱う
- `/D "WIN32"` と `/DWIN32` と `/D "NAME=VALUE"` を扱う
- `/FI"config.h"` と `/FI "config.h"` を扱う
- `/Yu"stdafx.h"` と `/Yu "stdafx.h"` を扱う
- `/Yc"stdafx.h"` と `/Yc "stdafx.h"` を扱う
- `$(VAR)` を含む場合は unresolved macro として保持する

Python実装では、まず `shlex.split(..., posix=False)` の利用を検討する。
ただし Windows command line と完全一致しない場合があるため、fixture で確認し、必要なら専用 tokenizer を実装する。

### 6.5 option 抽出ルール

| option | 抽出先 | 例 |
|---|---|---|
| `/D` | defines | `/D "WIN32"`, `/DDEBUG=1` |
| `/I` | include_dirs | `/I ".\include"` |
| `/FI` | forced_includes | `/FI"config.h"` |
| `/Yu` | pch_mode / pch_header | `/Yu"stdafx.h"` |
| `/Yc` | pch_mode / pch_header | `/Yc"stdafx.h"` |
| `/YX` | pch_mode | automatic PCH |
| `/ML` `/MLd` `/MT` `/MTd` `/MD` `/MDd` | runtime_library | runtime setting |
| `/W0` `/W1` `/W2` `/W3` `/W4` | warning_level | warning level |
| `/Od` `/O1` `/O2` `/Ox` | optimization | optimization |
| `/Zi` `/ZI` `/Zd` | debug_info | debug information |

抽出できない option は捨てずに `raw_options` に保持する。

### 6.6 source file 抽出

対象行例:

```text
# Begin Group "Source Files"
# Begin Source File
SOURCE=.\src\control.c
# End Source File
# End Group
```

方針:

- current group を保持する
- `SOURCE=` 行を file entry として扱う
- path は `.dsp` 所在ディレクトリ基準で解決する
- 拡張子で file_kind を分類する
- `.c` は `source` として扱う
- `SOURCE=".\My File.c"` のようなquoteも扱う
- ファイルが存在しない場合は warning を付けるが、entry は残す

---

## 7. Source Membership 設計

### 7.1 map-source の実用化

Step 04 で `map-source` は実用実装にする。

入力例:

```bat
unit-test-runner map-source ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c
```

処理:

1. `.dsw` を解析する
2. `.dsw` から得た各 `.dsp` を解析する
3. 各 `.dsp` の `files` から対象 `.c` と一致する entry を探す
4. 一致した `.dsp` を membership match として返す
5. 一致しなかった場合は候補 `.dsp` 一覧と warning を返す
6. 複数一致した場合は全候補を返す
7. `--project` 指定があれば project_name で絞り込む
8. `--configuration` 指定があれば configuration を絞り込む
9. `--out` 指定があれば JSON または Markdown を保存する
10. `--json` 指定時は stdout に JSON のみを出す

### 7.2 パス一致ルール

対象 `.c` の指定には以下があり得る。

- `src\control.c`
- `.\src\control.c`
- `D:\work\product\src\control.c`
- `../product/src/control.c`
- 大文字小文字違い

一致判定の方針:

1. 可能なら絶対パスで比較する
2. Windows想定として、大文字小文字は区別しない比較も併用する
3. slash / backslash 差異を正規化する
4. `Path.resolve()` が失敗する場合は normalized string で比較する
5. それでも不明な場合は file name のみ一致を low confidence candidate として返すか検討する

Step 04 では、file name のみ一致は既定では match にしない。
ただし `warnings` に `filename_only_candidate` として残してよい。

### 7.3 map-source JSON 出力例

```json
{
  "schema_version": "0.1",
  "command": "map-source",
  "status": "ok",
  "source": {
    "input": "src/control.c",
    "absolute": "D:/work/product/src/control.c"
  },
  "matches": [
    {
      "project_name": "Control",
      "dsp_path": "D:/work/product/Control/Control.dsp",
      "source_entry": {
        "source_path": "src/control.c",
        "group": "Source Files",
        "file_kind": "source"
      },
      "configurations": [
        {
          "full_name": "Control - Win32 Debug",
          "defines": ["WIN32", "_DEBUG", "_CONSOLE"],
          "include_dirs": ["D:/work/product/Control/include"],
          "forced_includes": [],
          "pch": {
            "mode": "use",
            "header": "stdafx.h"
          }
        }
      ]
    }
  ],
  "warnings": []
}
```

### 7.4 複数所属時の方針

同じ `.c` が複数 `.dsp` に含まれる場合、勝手に1つへ決めない。

方針:

- `matches` に全候補を返す
- status は `multiple_matches` としてもよい
- CLI通常出力では、`--project` または `--configuration` で絞るよう促す
- Step 05 の `analyze-function` では、複数候補がある場合にユーザー指定を必須にする

---

## 8. discover-projects への拡張

Step 03 の `discover-projects` は `.dsw` から `.dsp` 参照を発見するところまでだった。
Step 04 では、必要に応じて `--with-dsp-details` オプションを追加する。

```bat
unit-test-runner discover-projects ^
  --workspace D:\work\product ^
  --with-dsp-details ^
  --out D:\work\unit_test_workspace\reports\projects.json
```

`--with-dsp-details` 指定時に追加する情報:

- configurations
- source file count
- header file count
- resource file count
- defines summary
- include dirs summary
- warnings

既定では Step 03 と同じ軽量出力を維持する。
巨大な workspace で全 `.dsp` 解析が重くなる可能性があるためである。

---

## 9. Build Context 出力設計

Step 04 では、Step 05 以降で使う build context の形式を決める。

### 9.1 build_context.json 例

```json
{
  "schema_version": "0.1",
  "source": "src/control.c",
  "project": {
    "name": "Control",
    "dsp_path": "D:/work/product/Control/Control.dsp"
  },
  "configuration": {
    "full_name": "Control - Win32 Debug",
    "platform": "Win32",
    "name": "Debug"
  },
  "compiler": {
    "defines": ["WIN32", "_DEBUG", "_CONSOLE"],
    "include_dirs": [
      {
        "raw": ".\\include",
        "absolute": "D:/work/product/Control/include",
        "exists": true
      }
    ],
    "forced_includes": [],
    "precompiled_header": {
      "mode": "use",
      "header": "stdafx.h"
    },
    "runtime_library": "/MDd",
    "warning_level": "/W3",
    "optimization": "/Od",
    "debug_info": "/ZI",
    "raw_options": []
  },
  "warnings": []
}
```

### 9.2 build context の利用先

- Step 05: C source lexer / masker
- Step 06: function locator
- Step 07: signature extractor
- Step 08以降: global / call / branch analyzer
- Step 12以降: build-probe
- VS Code adapter: ユーザーへの構成候補提示

---

## 10. レポート設計

### 10.1 JSON レポート

主出力は JSON とする。

用途:

- `map-source` の機械処理
- VS Code adapter での候補表示
- Step 05 以降の入力
- fixture と回帰テスト

### 10.2 Markdown レポート

`map-source --out result.md` または将来の `--format md` で Markdown を出力する。

内容例:

```markdown
# Source Membership Report

## Source

- Input: src/control.c
- Absolute: D:/work/product/src/control.c

## Matches

| Project | DSP | Configuration Count |
|---|---|---:|
| Control | Control/Control.dsp | 2 |

## Build Context: Control - Win32 Debug

### Defines

- WIN32
- _DEBUG
- _CONSOLE

### Include Directories

| Raw | Absolute | Exists |
|---|---|---|
| .\include | D:/work/product/Control/include | yes |

### PCH

- Mode: use
- Header: stdafx.h

## Warnings

なし
```

### 10.3 標準出力サマリ

通常モードでは短いサマリを出す。

```text
Source mapped: src\control.c
Matches: 1
Project: Control
Configurations: 2
Warnings: 0
```

複数一致時:

```text
Source mapped: src\control.c
Matches: 3
Multiple projects contain this source. Specify --project or --configuration.
```

---

## 11. テスト計画

### 11.1 fixture 構成

```text
tests/
  fixtures/
    vc6_dsp/
      minimal/
        Control.dsp
        src/
          control.c
      debug_release/
        Control.dsp
        src/
          control.c
      include_define/
        Control.dsp
        include/
          control.h
        src/
          control.c
      pch_forced_include/
        Control.dsp
        stdafx.h
        config.h
        src/
          control.c
      spaces_in_path/
        My Project.dsp
        My Source/
          control file.c
      macro_variables/
        Control.dsp
        src/
          control.c
      missing_source/
        Control.dsp
      malformed/
        Broken.dsp
    vc6_workspace/
      source_membership/
        Product.dsw
        Control/
          Control.dsp
          src/
            control.c
      multiple_membership/
        Product.dsw
        ProductA/
          ProductA.dsp
          src/
            shared.c
        ProductB/
          ProductB.dsp
          src/
            shared.c
```

### 11.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| DSP-001 | project header | minimal dsp | project name を抽出 |
| DSP-002 | format version | minimal dsp | 6.00 を抽出 |
| DSP-003 | configuration | Debug/Release | 2構成を抽出 |
| DSP-004 | ADD CPP | Debug config | compiler_options を抽出 |
| DSP-005 | defines | `/D "WIN32"` | defines に WIN32 |
| DSP-006 | define value | `/D "SIZE=10"` | `SIZE=10` を保持 |
| DSP-007 | include | `/I ".\include"` | include_dirs を抽出 |
| DSP-008 | include attached | `/I".\include"` | include_dirs を抽出 |
| DSP-009 | forced include | `/FI"config.h"` | forced_includes を抽出 |
| DSP-010 | PCH use | `/Yu"stdafx.h"` | pch mode use |
| DSP-011 | PCH create | `/Yc"stdafx.h"` | pch mode create |
| DSP-012 | runtime | `/MDd` | runtime_library を抽出 |
| DSP-013 | source files | SOURCE 行 | DspFileEntry を抽出 |
| DSP-014 | group | Source Files | group を保持 |
| DSP-015 | header files | Header Files | file_kind header |
| DSP-016 | resource files | Resource Files | file_kind resource |
| DSP-017 | missing source | 存在しない SOURCE | warning `missing_source_file` |
| DSP-018 | unresolved macro | `$(OUTDIR)` | warning `unresolved_macro` |
| DSP-019 | malformed | 壊れた行 | warning を返し partial result |
| DSP-020 | source membership | dsw + dsp + source | match 1件 |
| DSP-021 | multiple membership | 同一source複数dsp | match 複数件 |
| DSP-022 | map-source json | `--json map-source` | stdout が JSON のみ |
| DSP-023 | map-source project filter | `--project Control` | Control のみに絞る |
| DSP-024 | map-source config filter | `--configuration "Win32 Debug"` | Debug のみに絞る |
| DSP-025 | discover with details | `--with-dsp-details` | dsp summary を含む |

### 11.3 テスト方針

- DSP Parser 単体テストでは CLI を通さない
- source membership テストでは Step 03 の DSW Parser と結合する
- CLIテストでは `main(argv)` を直接呼ぶ
- JSONは `json.loads()` で検証する
- path比較は helper で正規化する
- Windows path文字列と空白pathをfixtureに含める
- option tokenization は個別に細かくテストする

---

## 12. 実装タスク分解

### Task 04-01: DSP model 定義

成果物:

- `src/unit_test_runner/vc6/dsp_models.py`
- `DspProject`
- `DspConfiguration`
- `DspBuildSettings`
- `DspFileEntry`
- `DspParseWarning`
- `PathLikeValue`
- JSON変換 helper

完了条件:

- 各modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 04-02: DSP text reader

成果物:

- encoding fallback 対応
- 行番号保持
- `encoding_fallback` warning

完了条件:

- utf-8 / cp932 fixture を読み込める

### Task 04-03: Project header / metadata parser

成果物:

- project name 抽出
- format version 抽出
- target type 抽出

完了条件:

- DSP-001 / DSP-002 が通る

### Task 04-04: Configuration parser

成果物:

- `!IF "$(CFG)" == ...` 抽出
- `!ELSEIF "$(CFG)" == ...` 抽出
- `# Name` 補助抽出
- Debug / Release などの configuration model 化

完了条件:

- DSP-003 が通る

### Task 04-05: Compiler option tokenizer

成果物:

- quote保持 tokenization
- `/I value` と `/Ivalue` の両対応
- `/D value` と `/Dvalue` の両対応
- `/FI` `/Yu` `/Yc` の両対応

完了条件:

- DSP-004 から DSP-012 が通る

### Task 04-06: Build settings extractor

成果物:

- defines 抽出
- include_dirs 抽出
- forced_includes 抽出
- PCH設定抽出
- runtime/warning/optimization/debug option 抽出
- unresolved macro 検出

完了条件:

- build settings のJSON出力が期待通りになる

### Task 04-07: Source file parser

成果物:

- group 状態管理
- SOURCE 行抽出
- path normalization
- file_kind 分類
- missing_source warning

完了条件:

- DSP-013 から DSP-019 が通る

### Task 04-08: Source membership usecase

成果物:

- `source_membership.py`
- `.dsw` 解析結果から `.dsp` を解析
- 対象 `.c` の所属判定
- multiple membership 対応
- project/configuration filter 対応

完了条件:

- DSP-020 から DSP-024 が通る

### Task 04-09: map-source CLI 更新

成果物:

- `map-source` を実用実装へ変更
- JSON / Markdown / stdout summary
- `--project` / `--configuration` 対応

完了条件:

- CLIから source membership を取得できる
- `--json` stdout がJSONのみ

### Task 04-10: discover-projects details 拡張

成果物:

- `--with-dsp-details`
- dsp summary 出力
- source/header/resource count
- configuration summary

完了条件:

- DSP-025 が通る

### Task 04-11: Markdown レポート

成果物:

- `reports/dsp_markdown.py`
- `reports/source_membership_markdown.py`
- snapshot test

完了条件:

- Markdown report が期待形式で生成される

### Task 04-12: fixture / test 整備

成果物:

- `tests/fixtures/vc6_dsp/...`
- `tests/fixtures/vc6_workspace/...`
- `tests/unit/test_dsp_parser.py`
- `tests/unit/test_dsp_options.py`
- `tests/unit/test_source_membership.py`
- `tests/unit/test_map_source_cli.py`

完了条件:

- DSP-001 から DSP-025 が通る

---

## 13. 受け入れ基準

Step 04 は、以下をすべて満たしたら完了とする。

1. `.dsp` ファイルから project name を抽出できる
2. `.dsp` ファイルから configuration 一覧を抽出できる
3. configuration 別に `# ADD CPP` / `# ADD BASE CPP` を抽出できる
4. `/D` define を抽出できる
5. `/I` include directory を抽出できる
6. `/FI` forced include を抽出できる
7. `/Yu` / `/Yc` / `/YX` precompiled header 設定を抽出できる
8. runtime / warning / optimization / debug option を抽出または raw option として保持できる
9. `.dsp` 内の source/header/resource file entry を抽出できる
10. source file path を `.dsp` 所在ディレクトリ基準で絶対化できる
11. missing source file を warning として返せる
12. `map-source --dsw <dsw> --source <c>` が対象 `.c` の所属 `.dsp` を返せる
13. 同一 `.c` が複数 `.dsp` に所属する場合に複数候補を返せる
14. `--project` / `--configuration` で候補を絞れる
15. `--json map-source` の stdout がJSONのみになる
16. `discover-projects --with-dsp-details` が DSP summary を返せる
17. Step 05 以降へ渡せる `build_context` 形式が定義されている
18. Parser単体テスト、option tokenizerテスト、source membershipテスト、CLI接続テストがある
19. Step 02 のCLI方針、Step 03 のDSW Parser modelを壊していない
20. `.dsp` 詳細解析を超えて C 関数解析へ踏み込んでいない

---

## 14. 成果物

Step 04 の成果物は以下とする。

```text
src/
  unit_test_runner/
    vc6/
      dsp_models.py
      dsp_parser.py
      dsp_options.py
      source_membership.py
    reports/
      dsp_markdown.py
      source_membership_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    vc6_dsp/
      minimal/
      debug_release/
      include_define/
      pch_forced_include/
      spaces_in_path/
      macro_variables/
      missing_source/
      malformed/
    vc6_workspace/
      source_membership/
      multiple_membership/
  unit/
    test_dsp_parser.py
    test_dsp_options.py
    test_source_membership.py
    test_map_source_cli.py
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/vc6/dsw_models.py` 必要な場合のみ
- `src/unit_test_runner/vc6/dsw_parser.py` 必要な場合のみ
- `src/unit_test_runner/utils/encoding.py` 必要な場合のみ
- `src/unit_test_runner/utils/paths.py` 必要な場合のみ

---

## 15. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| DSP形式の揺れ | VC6生成、手修正、MFC、DLL、LIBなどで行構造が変わる | fixtureを増やし、未知行はwarningとして保持する |
| compiler option tokenization の難しさ | quote、空白、`/Ixxx`、`/I xxx` が混在する | tokenizer単体テストを厚くし、raw_optionsを必ず保持する |
| macro variable 未解決 | `$(OUTDIR)`、`$(INTDIR)`、環境変数が含まれる | 既知macroだけ展開し、不明macroは unresolved として保持する |
| include path 解決ミス | dsp基準、workspace基準、絶対pathが混ざる | raw/normalized/absolute を全て保持し、存在確認をwarning化する |
| PCH依存 | `/Yu"stdafx.h"` により後続build-probeで失敗しやすい | pch情報を明示的に build_context に残す |
| 同一source複数所属 | 構成やdefineが異なる可能性がある | 複数候補を返し、勝手に選ばない |
| Step05責務の侵食 | 関数解析までStep04で始めたくなる | Step04は `.dsp` と build context までに限定する |
| 大規模workspace性能 | 全 `.dsp` 解析が重い場合がある | `discover-projects` は既定で軽量、詳細は `--with-dsp-details` 指定時のみ |

---

## 16. Step 05 への接続

Step 04 完了後、Step 05 では C source lexer / masker を実装する。
Step 05 は、Step 04 の `build_context` を受け取り、以下に進む。

```python
membership = map_source(dsw_path, source_path)
selected = select_membership(membership, project="Control", configuration="Control - Win32 Debug")
build_context = selected.to_build_context()
masked_source = mask_c_source(source_path, build_context)
```

Step 05 で扱う予定の情報:

- `source` path
- defines
- include dirs
- forced includes
- PCH header
- raw compiler options
- encoding

Step 04 の責務は、ここへ正しい build context を渡せるようにすることである。

---

## 17. まとめ

Step 04 は、`.dsp` から source membership と build context を取得するステップである。

このステップにより、ユーザーが指定した `.c` ファイルについて、どの VC6 プロジェクトに属し、どの構成で、どの define / include / PCH 条件のもとでコンパイルされるかを明らかにできる。

関数単位テストの実装そのものにはまだ進まないが、Step 05 以降の C 関数解析、function dossier 生成、build-probe の土台となる重要な情報をここで確定する。

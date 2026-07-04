# Step 03: DSW Parser 実装計画

作成日: 2026-07-04  
状態: Draft v0.1  
対象リポジトリ: `katamor1/unitTestRunner`  
製造担当想定: CODEX  
前提文書:

- `docs/adr/0001-cli-layer-language-selection.md`
- `docs/implementation/step02_cli_entry_point_plan.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第3ステップとして **VC6 Workspace File `.dsw` を解析する DSW Parser** を実装するための計画である。

Step 02 では、`unit-test-runner` の CLI Entry Point、サブコマンド、終了コード、JSON出力、未実装stubを定義した。
Step 03 では、そのうち以下のコマンドに最初の実処理を接続する。

```bat
unit-test-runner discover-projects --workspace D:\work\product --out reports\projects.json
unit-test-runner map-source --dsw D:\work\product\Product.dsw --source src\control.c
```

ただし、Step 03 の主対象は `.dsw` の解析であり、`.dsp` の詳細解析は Step 04 に残す。
Step 03 では、`.dsw` から参照される `.dsp` ファイル、プロジェクト名、プロジェクト間依存関係、相対パス解決の基準情報を取得する。

---

## 2. 目的

Step 03 の目的は、VC6 workspace から後続解析の入口となる **Project Discovery 情報** を安定して取得することである。

具体的には、以下を実現する。

- `.dsw` ファイルを読み込める
- `.dsw` に含まれる `.dsp` プロジェクト参照を抽出できる
- プロジェクト名と `.dsp` 相対パスを対応付けられる
- プロジェクト間依存関係を抽出できる
- `.dsw` 所在ディレクトリを基準に `.dsp` の絶対パス候補を解決できる
- 解析不能行や未知形式を警告として保持できる
- `discover-projects` コマンドから JSON / Markdown レポートを出力できる
- Step 04 の DSP Parser に渡せるデータモデルを定義できる

---

## 3. スコープ

### 3.1 実装対象

Step 03 で実装するもの:

1. DSW Parser 本体
   - `.dsw` テキスト読み込み
   - エンコーディング推定
   - project block 抽出
   - `.dsp` パス抽出
   - dependency block 抽出
   - unknown / unsupported 行の保持

2. データモデル
   - `DswWorkspace`
   - `DswProject`
   - `DswDependency`
   - `DswParseWarning`
   - `DswParseResult`

3. CLI 接続
   - `discover-projects` の stub を実処理へ置換
   - `map-source` は Step 03 では限定実装または `partially_implemented` とする

4. レポート出力
   - JSON 出力
   - Markdown 出力
   - 標準出力サマリ

5. テスト
   - 最小 `.dsw` fixture
   - 複数 `.dsp` fixture
   - プロジェクト依存関係 fixture
   - パスに空白を含む fixture
   - 不正または未知形式 fixture
   - 日本語パスまたは cp932 想定 fixture

### 3.2 対象外

Step 03 では以下を対象外とする。

- `.dsp` 内の source file list 抽出
- `.dsp` 内の define / include / compiler option 抽出
- `.c` ファイルがどの `.dsp` に属するかの完全判定
- VC6 構成名の完全抽出
- C 関数解析
- `function_dossier.json` 生成
- VC6 / nmake / cl.exe の起動
- VS Code extension 実装

ただし、Step 04 以降で使えるように、`.dsp` パスの正規化と存在確認までは行う。

---

## 4. DSW ファイルの扱い

### 4.1 想定する基本構造

VC6 の `.dsw` は、概ね以下のようなテキスト構造を持つ。

```text
Microsoft Developer Studio Workspace File, Format Version 6.00

###############################################################################

Project: "Control"=.\Control\Control.dsp - Package Owner=<4>

Package=<5>
{{{
}}}

Package=<4>
{{{
    Begin Project Dependency
    Project_Dep_Name Common
    End Project Dependency
}}}

###############################################################################

Project: "Common"=.\Common\Common.dsp - Package Owner=<4>

Package=<5>
{{{
}}}

Package=<4>
{{{
}}}

###############################################################################

Global:

Package=<5>
{{{
}}}

Package=<3>
{{{
}}}
```

Step 03 では、このうち以下に注目する。

- `Project:` 行
- `Package=<4>` 内の `Begin Project Dependency` ブロック
- `Project_Dep_Name` 行
- `Global:` 以降

### 4.2 Project 行の解析

対象形式:

```text
Project: "Control"=.\Control\Control.dsp - Package Owner=<4>
```

抽出結果:

```json
{
  "name": "Control",
  "dsp_path_raw": ".\\Control\\Control.dsp",
  "dsp_path_normalized": "Control/Control.dsp",
  "dsp_path_absolute": "D:/work/product/Control/Control.dsp",
  "package_owner": "4"
}
```

考慮する揺れ:

- パスが `..\Project\Project.dsp` である
- パスに空白を含む
- プロジェクト名に空白を含む
- `.DSP` のように拡張子大文字である
- `Package Owner=<4>` の前後空白が異なる
- 行末改行が CRLF / LF のどちらでもある

### 4.3 Dependency ブロックの解析

対象形式:

```text
Begin Project Dependency
Project_Dep_Name Common
End Project Dependency
```

抽出結果:

```json
{
  "from_project": "Control",
  "to_project": "Common",
  "kind": "project_dependency"
}
```

依存関係は「現在の Project block に対して、`Project_Dep_Name` の対象プロジェクトへ依存する」と解釈する。

### 4.4 Unknown 行の扱い

`.dsw` は案件ごとに微妙な差異があり得るため、未知行を即エラーにしない。

方針:

- 解析に必要な行以外は原則無視する
- ただし project block 内の未知行は warning に残す
- dependency block の構造が壊れている場合は warning に残す
- Project 行が不完全な場合は error に近い warning として残す
- 解析結果には `warnings` を含める

---

## 5. データモデル設計

### 5.1 DswWorkspace

```python
@dataclass
class DswWorkspace:
    path: Path
    root_dir: Path
    format_version: str | None
    projects: list[DswProject]
    dependencies: list[DswDependency]
    warnings: list[DswParseWarning]
```

役割:

- `.dsw` 全体の解析結果を保持する
- Step 04 の DSP Parser へプロジェクト一覧を渡す
- JSON / Markdown レポートの入力になる

### 5.2 DswProject

```python
@dataclass
class DswProject:
    name: str
    dsp_path_raw: str
    dsp_path: Path
    dsp_path_absolute: Path
    package_owner: str | None
    exists: bool
    line_number: int
```

役割:

- `.dsw` 内の1プロジェクトを表す
- `.dsp` が存在するかどうかも保持する
- パス解決の失敗を warning として扱えるようにする

### 5.3 DswDependency

```python
@dataclass
class DswDependency:
    from_project: str
    to_project: str
    line_number: int
```

役割:

- プロジェクト間依存関係を表す
- Step 04 以降で build context の優先順位や関連プロジェクト候補の参考にする

### 5.4 DswParseWarning

```python
@dataclass
class DswParseWarning:
    code: str
    message: str
    line_number: int | None = None
    line_text: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `unknown_line` | 無視された未知行 |
| `malformed_project_line` | Project 行の解析失敗 |
| `missing_dsp_file` | 参照先 `.dsp` が存在しない |
| `dependency_without_project` | Project block 外で dependency が見つかった |
| `dependency_unknown_project` | 依存先プロジェクト名が project list に存在しない |
| `encoding_fallback` | 文字コード推定で fallback した |

---

## 6. パーサ設計

### 6.1 実装ファイル

```text
src/
  unit_test_runner/
    vc6/
      __init__.py
      dsw_parser.py
      dsw_models.py
    reports/
      dsw_markdown.py
    cli/
      commands.py
```

必要に応じて、既存の `utils/encoding.py`、`utils/paths.py` を使う。
未実装であれば Step 03 の中で最小実装してよい。

### 6.2 処理フロー

```text
parse_dsw(path)
  1. path を絶対パス化
  2. ファイル存在確認
  3. エンコーディング候補で読み込み
  4. 行単位に分割
  5. Format Version を検出
  6. Project 行を検出
  7. Project block の現在位置を保持
  8. Dependency block を検出
  9. Project_Dep_Name を依存関係として保存
 10. dsp path を root_dir 基準で解決
 11. dsp ファイル存在確認
 12. 依存先未定義を warning 化
 13. DswWorkspace を返す
```

### 6.3 エンコーディング方針

読み込み候補:

1. `utf-8-sig`
2. `utf-8`
3. `cp932`
4. `shift_jis`

方針:

- 最初に成功したエンコーディングを採用する
- fallback が発生した場合は warning に残す
- 解析結果 JSON に `encoding` を含めるかは、Step 03 では任意とする
- 将来的には `ParseMetadata` として統一する

### 6.4 正規表現方針

Project 行の初期正規表現案:

```python
PROJECT_RE = re.compile(
    r'^Project:\s+"(?P<name>.+?)"\s*=\s*(?P<path>.+?)\s+-\s+Package\s+Owner=<(?P<owner>[^>]+)>\s*$'
)
```

Dependency 行の初期正規表現案:

```python
DEP_RE = re.compile(r'^\s*Project_Dep_Name\s+(?P<name>.+?)\s*$')
```

注意:

- 完全な文法解析ではなく、VC6 `.dsw` の実用解析を優先する
- パスに ` - ` が含まれる特殊ケースは低頻度とみなし、fixture が出た段階で補正する
- 正規表現に失敗した行は warning として残す

---

## 7. CLI 接続設計

### 7.1 discover-projects

Step 03 で `discover-projects` を実処理化する。

入力例:

```bat
unit-test-runner discover-projects ^
  --workspace D:\work\product ^
  --out D:\work\unit_test_workspace\reports\projects.json
```

処理:

1. `--workspace` が `.dsw` ファイルなら、そのファイルを解析する
2. `--workspace` がディレクトリなら、配下の `.dsw` を探索する
3. `.dsw` が1つなら自動選択する
4. `.dsw` が複数なら、全て解析し `workspaces` 配列として出力する
5. `.dsw` が0件なら exit `2` とする
6. `--out` が指定されていれば JSON を保存する
7. 標準出力にはサマリを出す
8. `--json` 指定時は stdout に JSON のみを出す

出力JSON例:

```json
{
  "schema_version": "0.1",
  "command": "discover-projects",
  "status": "ok",
  "workspaces": [
    {
      "dsw_path": "D:/work/product/Product.dsw",
      "root_dir": "D:/work/product",
      "format_version": "6.00",
      "projects": [
        {
          "name": "Control",
          "dsp_path": "Control/Control.dsp",
          "dsp_path_absolute": "D:/work/product/Control/Control.dsp",
          "exists": true
        }
      ],
      "dependencies": [
        {
          "from_project": "Control",
          "to_project": "Common"
        }
      ],
      "warnings": []
    }
  ]
}
```

### 7.2 map-source

Step 03 では `map-source` の完全実装は行わない。
ただし、`.dsw` 解析ができたことを利用して、以下の限定応答を返す。

```bat
unit-test-runner map-source ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c
```

Step 03 の応答方針:

- `.dsw` を解析する
- `.dsp` 候補一覧を返す
- `.c` がどの `.dsp` に属するかは Step 04 で判定すると明記する
- status は `partial` とする
- exit code は `20` ではなく `0` としてよい。ただし `partial` を明示する

JSON例:

```json
{
  "status": "partial",
  "command": "map-source",
  "message": "DSW parsed. DSP source membership requires Step 04.",
  "source": "src/control.c",
  "candidate_projects": [
    {
      "name": "Control",
      "dsp_path": "Control/Control.dsp"
    }
  ]
}
```

---

## 8. レポート設計

### 8.1 JSON レポート

主出力は JSON とする。

用途:

- Step 04 DSP Parser の入力
- VS Code adapter からの機械処理
- CODEX による後続実装の fixture
- ユーザーへの確認

### 8.2 Markdown レポート

`--out` の拡張子が `.md` の場合、または将来の `--format md` 指定時に Markdown を出力する。
Step 03 では必須ではないが、実装できるなら対応する。

内容:

```markdown
# DSW Project Discovery Report

## Workspace

- Path: D:/work/product/Product.dsw
- Format Version: 6.00

## Projects

| Project | DSP Path | Exists |
|---|---|---|
| Control | Control/Control.dsp | yes |
| Common | Common/Common.dsp | yes |

## Dependencies

| From | To |
|---|---|
| Control | Common |

## Warnings

なし
```

### 8.3 標準出力サマリ

通常モードでは、以下のような短いサマリを stdout に出す。

```text
DSW parsed: D:\work\product\Product.dsw
Projects: 2
Dependencies: 1
Warnings: 0
Output: D:\work\unit_test_workspace\reports\projects.json
```

---

## 9. テスト計画

### 9.1 fixture 構成

```text
tests/
  fixtures/
    vc6_dsw/
      minimal/
        Product.dsw
        Control/
          Control.dsp
      multiple_projects/
        Product.dsw
        Control/
          Control.dsp
        Common/
          Common.dsp
      dependencies/
        Product.dsw
        Control/
          Control.dsp
        Common/
          Common.dsp
      spaces_in_path/
        Product With Space.dsw
        My Project/
          My Project.dsp
      missing_dsp/
        Product.dsw
      malformed/
        Broken.dsw
      cp932/
        JapaneseProject.dsw
```

### 9.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| DSW-001 | 最小DSW | 1 project | project 1件を抽出 |
| DSW-002 | 複数project | 2 projects | project 2件を抽出 |
| DSW-003 | 依存関係 | Control depends Common | dependency 1件を抽出 |
| DSW-004 | 相対パス | `.\Control\Control.dsp` | 絶対パス解決できる |
| DSW-005 | 親ディレクトリ | `..\Common\Common.dsp` | root基準で解決できる |
| DSW-006 | 空白パス | `My Project\My Project.dsp` | project名とpathを保持できる |
| DSW-007 | 大文字拡張子 | `.DSP` | dspとして扱う |
| DSW-008 | missing dsp | 参照先なし | warning `missing_dsp_file` |
| DSW-009 | malformed project line | 壊れたProject行 | warning `malformed_project_line` |
| DSW-010 | unknown dependency target | 依存先未定義 | warning `dependency_unknown_project` |
| DSW-011 | discover-projects file | `--workspace Product.dsw` | exit 0, JSON出力 |
| DSW-012 | discover-projects dir single | `--workspace dir` | `.dsw` 1件を解析 |
| DSW-013 | discover-projects dir multiple | `--workspace dir` | 複数workspaceを出力 |
| DSW-014 | discover-projects no dsw | `.dsw`なし | exit 2 |
| DSW-015 | map-source partial | dsw + source | status `partial` |
| DSW-016 | json stdout purity | `--json discover-projects` | stdoutがJSONのみ |

### 9.3 テスト方針

- Parser単体テストでは CLI を通さない
- CLI接続テストでは `main(argv)` を直接呼ぶ
- JSONは `json.loads()` で検証する
- パス比較は `Path.resolve()` の差異を吸収する helper を使う
- Windows固有パス文字列は fixture として持つが、テスト実行OSに依存しすぎないよう注意する

---

## 10. 実装タスク分解

### Task 03-01: DSW model 定義

成果物:

- `src/unit_test_runner/vc6/dsw_models.py`
- model の `to_dict()` または JSON変換 helper
- 単体テスト

完了条件:

- `DswWorkspace` / `DswProject` / `DswDependency` / `DswParseWarning` を生成できる
- JSON変換できる

### Task 03-02: DSW text reader

成果物:

- encoding fallback 対応
- 改行保持または行番号保持
- warning `encoding_fallback`

完了条件:

- utf-8 / cp932 fixture を読み込める
- 行番号付きで parser に渡せる

### Task 03-03: Project line parser

成果物:

- Project 行正規表現
- project name 抽出
- dsp raw path 抽出
- package owner 抽出
- path normalization

完了条件:

- 最小DSW、複数project、空白path、大文字拡張子のfixtureが通る

### Task 03-04: Dependency parser

成果物:

- Begin / End Project Dependency の状態管理
- Project_Dep_Name 抽出
- from_project / to_project の対応付け

完了条件:

- dependency fixture で依存関係を抽出できる
- project block 外 dependency を warning 化できる

### Task 03-05: Warning / validation

成果物:

- missing dsp warning
- malformed project line warning
- dependency unknown project warning
- unknown line warning の扱い方整理

完了条件:

- malformed fixture と missing fixture が期待warningを返す

### Task 03-06: discover-projects CLI 接続

成果物:

- `discover-projects` handler の実処理化
- file / directory 両対応
- `--out` JSON保存
- `--json` stdout対応

完了条件:

- CLIテスト DSW-011 から DSW-014 が通る

### Task 03-07: map-source partial 実装

成果物:

- `.dsw` 解析結果から candidate_projects を返す
- source membership は Step 04 と明記

完了条件:

- CLIテスト DSW-015 が通る

### Task 03-08: Markdown レポート

成果物:

- `reports/dsw_markdown.py`
- project table
- dependency table
- warning list

完了条件:

- Markdown snapshot test が通る

### Task 03-09: fixture / test 整備

成果物:

- `tests/fixtures/vc6_dsw/...`
- `tests/unit/test_dsw_parser.py`
- `tests/unit/test_discover_projects_cli.py`
- `tests/unit/test_map_source_partial_cli.py`

完了条件:

- DSW-001 から DSW-016 が通る

---

## 11. 受け入れ基準

Step 03 は、以下をすべて満たしたら完了とする。

1. `.dsw` ファイルから project 一覧を抽出できる
2. project 名と `.dsp` 相対パスを抽出できる
3. `.dsp` 絶対パス候補を `.dsw` 所在ディレクトリ基準で解決できる
4. `.dsp` ファイル存在有無を判定できる
5. project 間 dependency を抽出できる
6. malformed / missing / unknown dependency を warning として返せる
7. `discover-projects --workspace <dsw>` が exit 0 で JSONを出力できる
8. `discover-projects --workspace <directory>` が配下の `.dsw` を探索できる
9. `.dsw` が存在しない場合は exit 2 になる
10. `--json discover-projects` の stdout がJSONのみになる
11. `--out` 指定時に JSON または Markdown を保存できる
12. `map-source` が Step 03 時点では `partial` として candidate_projects を返せる
13. Step 04 DSP Parser に渡せる model / dict が定義されている
14. Parser単体テストとCLI接続テストがある
15. Step 02 で定義した CLI方針、終了コード、JSON stdout 方針を壊していない

---

## 12. 成果物

Step 03 の成果物は以下とする。

```text
src/
  unit_test_runner/
    vc6/
      __init__.py
      dsw_models.py
      dsw_parser.py
    reports/
      dsw_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    vc6_dsw/
      minimal/
      multiple_projects/
      dependencies/
      spaces_in_path/
      missing_dsp/
      malformed/
      cp932/
  unit/
    test_dsw_parser.py
    test_discover_projects_cli.py
    test_map_source_partial_cli.py
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- 必要に応じて `src/unit_test_runner/utils/encoding.py`
- 必要に応じて `src/unit_test_runner/utils/paths.py`

---

## 13. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| DSW形式の揺れ | VC6生成以外、手修正、改行差分などで解析失敗する | unknown行をwarning化し、fixtureを増やして漸進対応する |
| パス解決ミス | `.dsw`基準、カレント基準、親ディレクトリ参照が混ざる | root_dirを`.dsw`所在ディレクトリに固定し、raw/normalized/absoluteを全て保持する |
| 日本語/Shift_JIS | 古いWindows環境でcp932の可能性がある | utf-8系の後にcp932/shift_jis fallbackを行う |
| 依存関係の向きの誤解 | from/to の意味を取り違える | 現在Projectが依存元、Project_Dep_Nameが依存先と明文化しテストする |
| Step04責務の侵食 | DSP内のsource解析までStep03でやりたくなる | Step03は`.dsp`参照抽出までに限定する |
| map-sourceの期待過多 | ユーザーが所属判定完了と誤解する | status `partial` と message でStep04が必要と明記する |

---

## 14. Step 04 への接続

Step 03 完了後、Step 04 の DSP Parser は `DswWorkspace.projects` を入力として、各 `.dsp` を解析する。

想定接続:

```python
workspace = parse_dsw(dsw_path)
for project in workspace.projects:
    dsp_result = parse_dsp(project.dsp_path_absolute)
```

Step 04 で追加される情報:

- `.dsp` 内の source file list
- header file list
- configuration list
- `# ADD CPP` 行
- `/D` define
- `/I` include directory
- `/FI` forced include
- `/Yu` / `/Yc` precompiled header
- compiler option

Step 03 では、これらを解析しない。
そのかわり、`.dsp` ファイルへ確実に到達するための project discovery 情報を安定して提供する。

---

## 15. まとめ

Step 03 は、VC6 workspace から `.dsp` プロジェクト群を発見するための基盤である。

このステップでは、`.dsw` から project 名、`.dsp` パス、project dependency、warning を抽出し、`discover-projects` コマンドで JSON / Markdown として出力できるようにする。

`.c` ファイルの所属判定や define / include の取得は Step 04 の DSP Parser で行う。
Step 03 では、その前段として `.dsp` 群へ安全に到達できる状態を作る。

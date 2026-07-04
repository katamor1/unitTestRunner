# Step 14: Build Workspace / Build Probe Generator 実装計画

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
- `docs/implementation/step13_stub_harness_skeleton_generator_plan.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第14ステップとして **Build Workspace / Build Probe Generator** を実装するための計画である。

Step 13 では、Step 12 の `test_case_draft` と Step 09 の `stub_candidates` を使い、VC6 / C90 互換を意識したスタブ雛形、テストランナー雛形、テストケース関数雛形、target invocation雛形を外部ワークスペースへ生成する計画を定義した。

Step 14 では、Step 04 の `build_context` と Step 13 の `harness_skeleton_report` を使い、VC6 / nmake / cl.exe でビルド試行できる **build workspace** を構成し、最初の **build probe** を実行できる状態にする。

ここでのbuild probeは、本格的なテスト実行ではない。
主目的は、対象 `.c`、関連ヘッダ、生成スタブ、生成ハーネス、include path、define、PCH情報、VC6 compiler option を組み合わせ、コンパイル・リンクに進めるかを確認し、不足ファイル・未解決シンボル・PCH問題・VC6非互換生成コードをレポートすることである。

Step 14 の主な責務は以下である。

- 外部ワークスペースにビルド用ディレクトリを作る
- 対象 `.c` と必要ヘッダを抽出または参照できる形にする
- Step 13 の生成Cコードをビルド対象へ組み込む
- Step 04 の define / include directory / compiler option / PCH情報を反映する
- VC6 / nmake 用の Makefile または build script 雛形を生成する
- build probe を実行するためのコマンドを生成する
- cl.exe / link.exe / nmake のログを収集する
- include不足、コンパイルエラー、リンクエラー、未解決外部参照を分類する
- build result report を出力する
- Step 15 の Build Error Analyzer / Stub Completion Loop に渡せる診断情報を整理する

---

## 2. 目的

Step 14 の目的は、Step 13 で生成したスタブ・ハーネス雛形を、VC6ビルド検証可能なワークスペースへ配置し、最初のビルド試行とログ収集を行えるようにすることである。

具体的には、以下を実現する。

- 本番リポジトリを変更せず、外部ワークスペースにビルド用ファイル構成を作れる
- Step 04 の `build_context` から define / include directory / compiler option を反映できる
- Step 13 の generated files をビルド対象に含められる
- 対象 `.c` と必要ヘッダを workspace にコピーまたは参照できる
- VC6 / nmake 用 Makefile 相当を生成できる
- cl.exe / link.exe / nmake の呼び出しコマンドを生成できる
- build probe をオプションで実行できる
- build log / compile log / link log を保存できる
- include不足を検出できる
- 未解決外部参照を抽出できる
- PCH関連エラーを検出できる
- VC6非互換な生成コードの疑いを検出できる
- `build_workspace_report.json` / Markdown を生成できる
- `build_probe_report.json` / Markdown を生成できる
- `analyze-function` を Step 14 時点で「ハーネス雛形生成 + build workspace生成 + build probe実行または準備」まで進められる

---

## 3. スコープ

### 3.1 実装対象

Step 14 で実装するもの:

1. Build workspace model
   - build workspace request
   - generated source list
   - extracted source list
   - include path list
   - define list
   - compiler option list
   - build command
   - build artifact metadata
   - warning / diagnostic

2. Workspace layout generator
   - `build/`
   - `obj/`
   - `bin/`
   - `logs/`
   - `extracted/`
   - `generated/`
   - `reports/`
   - relative path mapping

3. Source / header extractor
   - 対象 `.c` のcopyまたはreference
   - 直接includeヘッダのcopy候補
   - forced include / PCH header候補
   - generated harness / stubs / tests のcopyまたは配置確認
   - source hash記録

4. VC6 build file generator
   - nmake Makefile雛形
   - compile command list
   - link command list
   - include path反映
   - define反映
   - output object path反映
   - runtime / debug option反映

5. Build probe runner
   - nmake実行
   - cl.exe直接実行オプション
   - dry-run mode
   - timeout設定
   - environment capture
   - stdout / stderr log保存

6. Log parser / diagnostic extractor
   - fatal error C1083 include不足
   - syntax error / compiler error
   - warning抽出
   - LNK2001 / LNK2019 unresolved external symbol
   - PCH関連エラー
   - duplicate symbol候補
   - VC6非互換構文候補

7. Reports
   - `build_workspace_report.json`
   - `build_workspace_report.md`
   - `build_probe_report.json`
   - `build_probe_report.md`
   - `build.log`
   - `compile.log`
   - `link.log`

8. CLI 接続
   - `build-probe` を実用実装へ更新する
   - `analyze-function` からbuild workspace生成まで進める
   - build実行は `--run-build-probe` のような明示オプションで制御する
   - status `partial` / `build_workspace_generated` / `build_probe_failed` / `build_probe_succeeded` を返す
   - Step 15 の Build Error Analyzer / Stub Completion Loop が必要である旨をmessageに含める

9. Tests
   - workspace layout
   - Makefile generation
   - include / define option generation
   - generated file inclusion
   - dry-run build command
   - log parser
   - unresolved symbol parser
   - include missing parser
   - PCH warning
   - JSON / Markdown report

### 3.2 対象外

Step 14 では以下を対象外とする。

- ビルドエラーの自動修正
- 未解決シンボルからの追加スタブ自動生成
- include不足ファイルの再帰的な完全探索
- VC6 IDE `.dsp` の自動生成
- 本番 `.dsp` / `.dsw` の変更
- 本番リポジトリへの生成物追加
- 実行可能テストの実行
- テスト結果判定
- カバレッジ実測
- 32ms時間制約や疑似時間対応
- ハードウェア割込・I/O再現
- CI runner構築

Step 14 では、ビルド試行の準備と最初のbuild probe、ログ収集、診断情報生成に限定する。

---

## 4. 入力と出力

### 4.1 入力

主入力:

- Step 04 の `build_context`
- Step 05 の `source_digest`
- Step 06 の `function_location`
- Step 13 の `harness_skeleton_report`
- 対象 `.c` ファイル
- 生成先 workspace path
- VC6環境情報、任意

入力イメージ:

```json
{
  "source": "D:/work/product/src/control.c",
  "function": "Control_Update",
  "build_context": "reports/build_context.json",
  "source_digest": "reports/source_digest.json",
  "harness_skeleton_report": "reports/harness_skeleton_report.json",
  "output_root": "D:/work/unit_test_workspace/Control_Update",
  "vc6": {
    "vcvars32_bat": "C:/Program Files/Microsoft Visual Studio/VC98/Bin/VCVARS32.BAT",
    "nmake_path": null,
    "cl_path": null,
    "link_path": null
  }
}
```

### 4.2 出力

Step 14 の主要出力は build workspace と build probe report である。

```text
workspace/
  Control_Update/
    extracted/
      src/
        control.c
      include/
        control.h
    generated/
      include/
      harness/
      stubs/
      tests/
    build/
      Makefile
      build.bat
      clean.bat
      compile_commands.txt
    obj/
    bin/
    logs/
      build.log
      compile.log
      link.log
    reports/
      build_workspace_report.json
      build_workspace_report.md
      build_probe_report.json
      build_probe_report.md
```

`build_probe_report.json` は Step 15 以降の入力になる。

---

## 5. Build Workspace 方針

### 5.1 本番リポジトリ非侵襲

Step 14 でも本番リポジトリは読み取り専用入力として扱う。

方針:

- 本番リポジトリ内に生成物を置かない
- 本番 `.dsw` / `.dsp` を編集しない
- 本番ソースを直接改変しない
- 外部ワークスペース内でcopyまたはreferenceを使う
- copyした場合は元ファイルpathとhashを記録する

### 5.2 copy vs reference

初期方針はcopy優先とする。

理由:

- build workspaceを再現しやすい
- 生成物と抽出物を同じroot配下に置ける
- 後続のbuild probeログとsource hashを紐付けやすい
- 本番ソースへの誤書き込みを避けやすい

ただし、大規模ソースや容量の問題が出た場合はreference modeを追加する。

### 5.3 抽出対象

Step 14で必須扱いするもの:

- 対象 `.c`
- Step 13 generated files
- forced include header
- PCH header候補
- 直接includeヘッダ候補

Step 14で任意またはwarning扱いにするもの:

- include先の再帰的ヘッダ
- 外部ライブラリ
- 本番プロジェクト依存先の `.c`
- resource file
- custom build step生成物

---

## 6. データモデル設計

### 6.1 BuildWorkspaceRequest

```python
@dataclass
class BuildWorkspaceRequest:
    output_root: Path
    source_path: Path
    build_context: BuildContext
    source_digest: SourceDigest
    harness_report: HarnessSkeletonReport
    vc6_environment: VC6Environment | None
    generation_policy: BuildWorkspacePolicy
```

### 6.2 BuildWorkspacePolicy

```python
@dataclass
class BuildWorkspacePolicy:
    copy_sources: bool
    copy_headers: bool
    generate_makefile: bool
    generate_build_bat: bool
    run_build_probe: bool
    stop_on_compile_error: bool
    overwrite_existing: bool
    build_timeout_seconds: int
    keep_intermediate_files: bool
```

既定方針:

- `copy_sources = true`
- `copy_headers = true`
- `generate_makefile = true`
- `generate_build_bat = true`
- `run_build_probe = false`
- `stop_on_compile_error = false`
- `overwrite_existing = false`
- `build_timeout_seconds = 120`
- `keep_intermediate_files = true`

### 6.3 VC6Environment

```python
@dataclass
class VC6Environment:
    vcvars32_bat: Path | None
    cl_path: Path | None
    link_path: Path | None
    nmake_path: Path | None
    include_env: str | None
    lib_env: str | None
    path_env: str | None
    detected: bool
    warnings: list[BuildDiagnostic]
```

### 6.4 BuildWorkspaceReport

```python
@dataclass
class BuildWorkspaceReport:
    source_path: Path
    function_name: str
    status: str
    output_root: Path
    copied_files: list[WorkspaceFile]
    referenced_files: list[WorkspaceFile]
    generated_build_files: list[WorkspaceFile]
    compile_units: list[CompileUnit]
    link_units: list[Path]
    include_dirs: list[BuildPathEntry]
    defines: list[str]
    compiler_options: list[str]
    build_commands: list[BuildCommand]
    diagnostics: list[BuildDiagnostic]
```

`status` 候補:

| status | 意味 |
|---|---|
| `generated` | build workspace生成が完了した |
| `partial` | 一部不足があるが主要ファイルを生成した |
| `blocked` | 必須情報不足で生成できない |
| `skipped` | 既存ファイル保護などで生成しなかった |

### 6.5 WorkspaceFile

```python
@dataclass
class WorkspaceFile:
    source_path: Path | None
    workspace_path: Path
    file_kind: str
    sha256: str | None
    copied: bool
    generated: bool
    required: bool
    exists: bool
    warnings: list[BuildDiagnostic]
```

`file_kind` 候補:

- `target_source`
- `target_header`
- `forced_include`
- `pch_header`
- `generated_stub_source`
- `generated_stub_header`
- `generated_harness_source`
- `generated_harness_header`
- `generated_test_source`
- `makefile`
- `build_script`
- `log`
- `report`

### 6.6 CompileUnit

```python
@dataclass
class CompileUnit:
    source_file: Path
    object_file: Path
    include_dirs: list[BuildPathEntry]
    defines: list[str]
    compiler_options: list[str]
    command: str
    required: bool
```

### 6.7 BuildPathEntry

```python
@dataclass
class BuildPathEntry:
    raw: str
    workspace_path: Path | None
    original_path: Path | None
    exists: bool
    source: str
```

`source` 候補:

- `dsp_include`
- `generated_include`
- `extracted_include`
- `forced_include`
- `manual`

### 6.8 BuildCommand

```python
@dataclass
class BuildCommand:
    command_id: str
    command_kind: str
    working_directory: Path
    command_line: str
    log_file: Path | None
    dry_run: bool
```

`command_kind` 候補:

- `vcvars`
- `compile`
- `link`
- `nmake`
- `clean`
- `build_bat`

### 6.9 BuildProbeReport

```python
@dataclass
class BuildProbeReport:
    source_path: Path
    function_name: str
    status: str
    executed: bool
    exit_code: int | None
    started_at: str | None
    finished_at: str | None
    duration_ms: int | None
    commands: list[BuildCommandResult]
    diagnostics: list[BuildDiagnostic]
    missing_includes: list[MissingInclude]
    unresolved_symbols: list[UnresolvedSymbol]
    pch_issues: list[PchIssue]
    vc6_compatibility_issues: list[VC6CompatibilityIssue]
    log_files: list[Path]
```

`status` 候補:

| status | 意味 |
|---|---|
| `not_run` | build probeは実行していない |
| `succeeded` | build probe成功 |
| `failed` | build probe失敗 |
| `timeout` | build probe timeout |
| `environment_missing` | VC6環境が見つからない |
| `partial` | 一部コマンドのみ実行 |

### 6.10 BuildCommandResult

```python
@dataclass
class BuildCommandResult:
    command_id: str
    command_kind: str
    command_line: str
    exit_code: int
    stdout_log: Path | None
    stderr_log: Path | None
    combined_log: Path | None
    diagnostics: list[BuildDiagnostic]
```

### 6.11 BuildDiagnostic

```python
@dataclass
class BuildDiagnostic:
    code: str
    severity: str
    message: str
    file: Path | None
    line_number: int | None
    raw: str | None
```

warning / error code 例:

| code | 意味 |
|---|---|
| `missing_vc6_environment` | VC6環境が見つからない |
| `missing_include_dir` | include directoryが存在しない |
| `missing_source_file` | source fileが存在しない |
| `missing_generated_file` | Step 13生成物が見つからない |
| `c1083_include_not_found` | fatal error C1083 |
| `compiler_error` | Cコンパイルエラー |
| `compiler_warning` | Cコンパイル警告 |
| `lnk2001_unresolved_symbol` | LNK2001 |
| `lnk2019_unresolved_symbol` | LNK2019 |
| `pch_required` | PCHが必要そう |
| `pch_mismatch` | PCH設定不一致 |
| `vc6_incompatible_syntax` | VC6非互換構文疑い |
| `command_timeout` | コマンドtimeout |

### 6.12 MissingInclude

```python
@dataclass
class MissingInclude:
    include_name: str
    included_from: Path | None
    line_number: int | None
    diagnostic_raw: str
    candidate_dirs: list[Path]
```

### 6.13 UnresolvedSymbol

```python
@dataclass
class UnresolvedSymbol:
    symbol_name: str
    referenced_from: str | None
    diagnostic_code: str
    diagnostic_raw: str
    stub_candidate: bool
    related_call_name: str | None
```

### 6.14 PchIssue

```python
@dataclass
class PchIssue:
    issue_kind: str
    header: str | None
    diagnostic_raw: str
    suggested_action: str
```

### 6.15 VC6CompatibilityIssue

```python
@dataclass
class VC6CompatibilityIssue:
    issue_kind: str
    file: Path | None
    line_number: int | None
    diagnostic_raw: str
    suggested_action: str
```

---

## 7. Build File 生成設計

### 7.1 Makefile 方針

初期はnmake向けMakefileを生成する。

方針:

- target source、generated harness、generated stubs、generated testsをcompile unitにする
- objectは `obj/` 配下へ出力する
- executableは `bin/utr_probe.exe` とする
- include pathは generated include、extracted include、DSP include の順にする
- defineはDSP由来 + harness用defineを追加する
- PCHは初期では無効化できるなら無効化を試みる。ただし本番sourceがPCH前提の場合はwarningを出す

### 7.2 compile option 方針

Step 04 の compiler optionsをそのまま使うと、PCHや本番出力先などが混ざる可能性がある。
そのため、Step 14ではbuild probe向けに安全なoptionへ正規化する。

保持候補:

- `/nologo`
- `/W3` などwarning level
- `/D` define
- `/I` include
- `/Od` などoptimization
- `/Zi` / `/ZI` などdebug info
- `/MD` / `/MDd` / `/MT` / `/MTd` などruntime

除外または置換候補:

- `/Fo` 出力先
- `/Fd` PDB出力先
- `/Fp` PCH出力先
- `/Yu` / `/Yc` PCH関連。初期は扱いに注意
- 本番固有のpost build / custom build相当

### 7.3 build.bat 方針

`build.bat` には環境セットアップとnmake実行をまとめる。

例:

```bat
@echo off
setlocal

rem generated build probe script
rem review required

if exist "C:\Program Files\Microsoft Visual Studio\VC98\Bin\VCVARS32.BAT" call "C:\Program Files\Microsoft Visual Studio\VC98\Bin\VCVARS32.BAT"

nmake /f Makefile > ..\logs\build.log 2>&1
set BUILD_EXIT=%ERRORLEVEL%
exit /b %BUILD_EXIT%
```

方針:

- vcvars32 pathは設定で受け取る
- 未指定なら環境PATHにあるnmake / clを使う
- JSON modeのstdoutを汚さないよう、build logはfileへ出す

### 7.4 compile_commands.txt

正式なclang互換のcompile_commands.jsonではなく、Step 14では人間確認用の `compile_commands.txt` を生成する。

理由:

- VC6 / nmake 向けの実行コマンド確認が主目的
- compile_commands.jsonは後続で必要になれば追加する

---

## 8. Build Probe 実行設計

### 8.1 dry-run と run

既定では build workspace生成のみ行い、build probeは実行しない。

理由:

- VC6環境がない開発者環境でも使えるようにする
- build実行は環境依存が大きい
- `analyze-function` の基本動作を重くしない

実行する場合:

```bat
unit-test-runner build-probe --workspace D:\work\unit_test_workspace\Control_Update --run
```

または:

```bat
unit-test-runner analyze-function ... --run-build-probe
```

### 8.2 実行時の注意

- timeoutを必ず設定する
- stdout / stderr はlogs配下へ保存する
- JSON modeではstdoutにJSONのみを出す
- build失敗はツール失敗ではなく `build_probe_failed` として扱う
- VC6環境が見つからない場合は `environment_missing` としてreportを生成する

### 8.3 戻り値方針

CLI終了コード案:

| 状況 | exit code |
|---|---:|
| workspace生成成功、probe未実行 | 0 |
| build probe成功 | 0 |
| build probe失敗、診断抽出成功 | 7 |
| VC6環境なし | 30 |
| 入力不正 | 1 |
| 内部エラー | 10 |

Step 02 の終了コード体系を壊さない範囲で、既存の `7 build-probe failed` を使う。

---

## 9. Log Parser 設計

### 9.1 include不足

対象例:

```text
fatal error C1083: Cannot open include file: 'foo.h': No such file or directory
```

抽出:

- include name: `foo.h`
- diagnostic code: `C1083`
- included from file / line, 取れる場合のみ
- candidate include dirs

### 9.2 unresolved external symbol

対象例:

```text
error LNK2001: unresolved external symbol _ReadSensor
error LNK2019: unresolved external symbol _WritePort referenced in function _Control_Update
```

抽出:

- symbol name
- diagnostic code
- referenced from
- related call name, `_` prefixを除いた候補
- Step 09 call_report.stub_candidatesとの照合

### 9.3 PCH問題

対象例:

```text
fatal error C1010: unexpected end of file while looking for precompiled header directive
fatal error C1853: precompiled header file is from a previous version of the compiler
```

抽出:

- issue kind
- header候補
- suggested action

方針:

- Step 14では自動修正しない
- `/Yu` 無効化や `stdafx.h` forced include などの案をsuggested actionに出す

### 9.4 VC6非互換構文疑い

対象例:

- `error C2065` が `for` 初期化変数に関係する
- `error C2143` syntax error around `{` / `}` / declaration
- `stdint.h` not found
- `stdbool.h` not found
- `inline` unknown

方針:

- 生成ファイル内で発生した場合はVC6 compatibility issueとして高優先度にする
- 本番source側で発生した場合はbuild context不足やPCH不足の可能性もあるためwarningにする

---

## 10. CLI 接続設計

### 10.1 build-probe の実用化

Step 02でstubだった `build-probe` を実用化する。

入力例:

```bat
unit-test-runner build-probe ^
  --workspace D:\work\unit_test_workspace\Control_Update ^
  --run
```

または明示入力:

```bat
unit-test-runner build-probe ^
  --build-context reports\build_context.json ^
  --source-digest reports\source_digest.json ^
  --harness-report reports\harness_skeleton_report.json ^
  --out D:\work\unit_test_workspace\Control_Update ^
  --run
```

オプション案:

```text
--workspace PATH
--build-context PATH
--source-digest PATH
--harness-report PATH
--out PATH
--vcvars PATH
--run
--dry-run
--timeout SECONDS
--overwrite
--json
```

### 10.2 analyze-function の Step 14 接続

Step 14 では、`analyze-function` をbuild workspace生成まで進める。
build probe実行は明示オプションでのみ行う。

```bat
unit-test-runner analyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Control - Win32 Debug" ^
  --out D:\work\unit_test_workspace\Control_Update ^
  --run-build-probe
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
10. Step 13 の harness_skeleton を生成または読み込む
11. Step 14 の build workspaceを生成する
12. `--run-build-probe` 指定時のみbuild probeを実行する
13. `build_workspace_report.json` / md を生成する
14. `build_probe_report.json` / md を生成する
15. Step 15 の Build Error Analyzer / Stub Completion Loop が必要であることを message に含める

---

## 11. Report 設計

### 11.1 build_workspace_report.json

例:

```json
{
  "schema_version": "0.1",
  "function": {
    "name": "Control_Update",
    "status": "generated"
  },
  "output_root": "D:/work/unit_test_workspace/Control_Update",
  "copied_files": [
    {
      "source_path": "D:/work/product/src/control.c",
      "workspace_path": "extracted/src/control.c",
      "file_kind": "target_source",
      "copied": true,
      "required": true
    }
  ],
  "generated_build_files": [
    {
      "workspace_path": "build/Makefile",
      "file_kind": "makefile",
      "generated": true
    },
    {
      "workspace_path": "build/build.bat",
      "file_kind": "build_script",
      "generated": true
    }
  ],
  "compile_units": [
    {
      "source_file": "extracted/src/control.c",
      "object_file": "obj/control.obj",
      "required": true
    },
    {
      "source_file": "generated/stubs/stub_ReadSensor.c",
      "object_file": "obj/stub_ReadSensor.obj",
      "required": true
    }
  ],
  "include_dirs": [
    {
      "raw": "generated/include",
      "exists": true,
      "source": "generated_include"
    }
  ],
  "defines": ["WIN32", "_DEBUG", "_CONSOLE"],
  "diagnostics": []
}
```

### 11.2 build_probe_report.json

例:

```json
{
  "schema_version": "0.1",
  "function": {
    "name": "Control_Update",
    "status": "failed"
  },
  "executed": true,
  "exit_code": 2,
  "duration_ms": 1234,
  "missing_includes": [
    {
      "include_name": "platform.h",
      "diagnostic_raw": "fatal error C1083: Cannot open include file: 'platform.h': No such file or directory"
    }
  ],
  "unresolved_symbols": [
    {
      "symbol_name": "ReadAdValue",
      "diagnostic_code": "LNK2001",
      "stub_candidate": true,
      "related_call_name": "ReadAdValue"
    }
  ],
  "pch_issues": [],
  "vc6_compatibility_issues": [],
  "log_files": [
    "logs/build.log"
  ]
}
```

### 11.3 Markdown report

`build_workspace_report.md`:

```markdown
# Build Workspace Report

## Target

- Function: Control_Update
- Output Root: D:/work/unit_test_workspace/Control_Update

## Compile Units

| Source | Object | Required |
|---|---|---|
| extracted/src/control.c | obj/control.obj | yes |
| generated/stubs/stub_ReadSensor.c | obj/stub_ReadSensor.obj | yes |

## Include Dirs

| Path | Source | Exists |
|---|---|---|
| generated/include | generated_include | yes |

## Diagnostics

なし
```

`build_probe_report.md`:

```markdown
# Build Probe Report

## Status

- Executed: yes
- Status: failed
- Exit Code: 2

## Missing Includes

| Include | Diagnostic |
|---|---|
| platform.h | fatal error C1083 ... |

## Unresolved Symbols

| Symbol | Related Call | Stub Candidate |
|---|---|---|
| ReadAdValue | ReadAdValue | yes |

## PCH Issues

なし

## VC6 Compatibility Issues

なし
```

---

## 12. テスト計画

### 12.1 fixture 構成

```text
tests/
  fixtures/
    build_workspace/
      simple_function/
        build_context.json
        source_digest.json
        harness_skeleton_report.json
      include_define/
      pch_required/
      missing_generated_file/
      no_vc6_environment/
      logs/
        c1083_missing_include.log
        lnk2001_unresolved.log
        lnk2019_unresolved.log
        pch_error.log
        vc6_incompatible.log
```

### 12.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| BLD-001 | workspace layout | simple | build/obj/bin/logs生成 |
| BLD-002 | copy target source | source_digest | extracted/srcへcopy |
| BLD-003 | include dirs | build_context | include option生成 |
| BLD-004 | defines | build_context | /D option生成 |
| BLD-005 | generated files | harness_report | compile_unitsに追加 |
| BLD-006 | Makefile | compile_units | Makefile生成 |
| BLD-007 | build.bat | vcvarsあり | build.bat生成 |
| BLD-008 | dry run | run=false | command生成、実行なし |
| BLD-009 | env missing | VC6なし | environment_missing report |
| BLD-010 | missing generated | harness file missing | diagnostic生成 |
| BLD-011 | C1083 parser | missing include log | MissingInclude抽出 |
| BLD-012 | LNK2001 parser | unresolved log | UnresolvedSymbol抽出 |
| BLD-013 | LNK2019 parser | unresolved log | referenced_from抽出 |
| BLD-014 | PCH parser | pch error log | PchIssue抽出 |
| BLD-015 | VC6 syntax issue | incompatible log | VC6CompatibilityIssue抽出 |
| BLD-016 | report json | build reports | JSON parse可能 |
| BLD-017 | report md | build reports | expected sectionあり |
| BLD-018 | build-probe cli dry-run | explicit inputs | workspace生成 |
| BLD-019 | build-probe cli run env missing | no VC6 | exit 30 or status environment_missing |
| BLD-020 | analyze-function integration | Step04-14 | build workspace生成 |

### 12.3 テスト方針

- build file generatorは文字列完全一致ではなく重要なoptionの存在を検証する
- log parserはfixture logから抽出結果を検証する
- build probe実行はunit testでは実際のVC6を要求しない
- 実行系はmock process runnerで検証する
- JSONは `json.loads()` で検証する
- Markdownは主要sectionの存在を検証する
- Windows path、空白path、quoteを重点的にテストする

---

## 13. 実装タスク分解

### Task 14-01: Build model 定義

成果物:

- `src/unit_test_runner/build/build_models.py`
- `BuildWorkspaceRequest`
- `BuildWorkspacePolicy`
- `VC6Environment`
- `BuildWorkspaceReport`
- `WorkspaceFile`
- `CompileUnit`
- `BuildPathEntry`
- `BuildCommand`
- `BuildProbeReport`
- `BuildCommandResult`
- `BuildDiagnostic`
- `MissingInclude`
- `UnresolvedSymbol`
- `PchIssue`
- `VC6CompatibilityIssue`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 14-02: Workspace layout generator

成果物:

- `src/unit_test_runner/build/workspace_layout.py`
- build / obj / bin / logs / extracted / generated / reports作成
- overwrite policy対応

完了条件:

- BLD-001 が通る

### Task 14-03: Source / generated file collector

成果物:

- `src/unit_test_runner/build/file_collector.py`
- target source copy
- generated file確認
- hash記録
- missing generated diagnostic

完了条件:

- BLD-002 / BLD-005 / BLD-010 が通る

### Task 14-04: Build option normalizer

成果物:

- `src/unit_test_runner/build/option_normalizer.py`
- `/D` define生成
- `/I` include生成
- unsafe output option除外
- PCH option整理

完了条件:

- BLD-003 / BLD-004 が通る

### Task 14-05: Makefile generator

成果物:

- `src/unit_test_runner/build/makefile_generator.py`
- nmake Makefile生成
- compile / link rule生成
- obj / bin path生成

完了条件:

- BLD-006 が通る

### Task 14-06: Build script generator

成果物:

- `src/unit_test_runner/build/build_script_generator.py`
- build.bat生成
- clean.bat生成
- vcvars対応

完了条件:

- BLD-007 が通る

### Task 14-07: Build command runner

成果物:

- `src/unit_test_runner/build/process_runner.py`
- dry-run
- timeout
- stdout/stderr log保存
- environment_missing扱い

完了条件:

- BLD-008 / BLD-009 が通る

### Task 14-08: Build log parser

成果物:

- `src/unit_test_runner/build/log_parser.py`
- C1083 parser
- LNK2001 parser
- LNK2019 parser
- compiler error/warning parser
- PCH parser
- VC6 compatibility issue parser

完了条件:

- BLD-011 から BLD-015 が通る

### Task 14-09: Build workspace generator統合

成果物:

- `src/unit_test_runner/build/build_workspace_generator.py`
- layout / file collector / option normalizer / makefile / build script統合
- build_workspace_report生成

完了条件:

- representative fixtureでworkspace reportが生成される

### Task 14-10: Build probe runner統合

成果物:

- `src/unit_test_runner/build/build_probe_runner.py`
- workspace生成済み環境でprobe実行またはdry-run
- build_probe_report生成

完了条件:

- dry-run / env missing / mock failureが扱える

### Task 14-11: Build report writer

成果物:

- `src/unit_test_runner/build/build_report_writer.py`
- `reports/build_workspace_markdown.py`
- `reports/build_probe_markdown.py`
- JSON / Markdown出力

完了条件:

- BLD-016 / BLD-017 が通る

### Task 14-12: build-probe CLI 実装

成果物:

- `build-probe` の実用化
- `--workspace`
- `--build-context`
- `--source-digest`
- `--harness-report`
- `--run` / `--dry-run`
- `--vcvars`
- `--timeout`

完了条件:

- BLD-018 / BLD-019 が通る

### Task 14-13: analyze-function 接続

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
- Step 14 build workspace生成
- `--run-build-probe` 指定時のprobe実行
- CLI `analyze-function` の出力更新

完了条件:

- BLD-020 が通る

### Task 14-14: fixture / test 整備

成果物:

- `tests/fixtures/build_workspace/...`
- `tests/unit/test_workspace_layout.py`
- `tests/unit/test_file_collector.py`
- `tests/unit/test_option_normalizer.py`
- `tests/unit/test_makefile_generator.py`
- `tests/unit/test_build_script_generator.py`
- `tests/unit/test_build_log_parser.py`
- `tests/unit/test_build_probe_cli.py`
- `tests/unit/test_analyze_function_partial_build_workspace.py`

完了条件:

- BLD-001 から BLD-020 が通る

---

## 14. 受け入れ基準

Step 14 は、以下をすべて満たしたら完了とする。

1. 外部workspaceにbuild / obj / bin / logs / extracted / generated / reportsを構成できる
2. 対象sourceをcopyまたはreferenceとしてworkspaceに配置できる
3. Step 13 generated filesをcompile unitとして扱える
4. Step 04 build_contextのdefineをcompile optionへ反映できる
5. Step 04 build_contextのinclude directoryをcompile optionへ反映できる
6. PCH情報をwarningまたはbuild hintとして保持できる
7. nmake向けMakefileを生成できる
8. build.bat / clean.batを生成できる
9. build probe dry-runでbuild commandを確認できる
10. 明示指定時のみbuild probeを実行できる
11. VC6環境がない場合にenvironment_missingとしてreportできる
12. build.log / compile.log / link.logを保存できる
13. C1083 include不足を抽出できる
14. LNK2001 / LNK2019 unresolved symbolを抽出できる
15. PCH関連エラーを抽出できる
16. VC6非互換生成コード疑いを抽出できる
17. `build_workspace_report.json` を生成できる
18. `build_workspace_report.md` を生成できる
19. `build_probe_report.json` を生成できる
20. `build_probe_report.md` を生成できる
21. `build-probe` が明示入力からworkspace生成またはprobe実行できる
22. `analyze-function` が Step 14 時点では build workspace生成まで進み、必要に応じてbuild probeを実行できる
23. Step 15 の Build Error Analyzer / Stub Completion Loop に渡せるdiagnosticsがある
24. ビルドエラーの自動修正へ踏み込みすぎていない
25. テスト実行や実測coverageへ踏み込みすぎていない

---

## 15. 成果物

Step 14 の成果物は以下とする。

```text
src/
  unit_test_runner/
    build/
      __init__.py
      build_models.py
      workspace_layout.py
      file_collector.py
      option_normalizer.py
      makefile_generator.py
      build_script_generator.py
      process_runner.py
      log_parser.py
      build_workspace_generator.py
      build_probe_runner.py
      build_report_writer.py
    reports/
      build_workspace_markdown.py
      build_probe_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    build_workspace/
      simple_function/
      include_define/
      pch_required/
      missing_generated_file/
      no_vc6_environment/
      logs/
        c1083_missing_include.log
        lnk2001_unresolved.log
        lnk2019_unresolved.log
        pch_error.log
        vc6_incompatible.log
  unit/
    test_workspace_layout.py
    test_file_collector.py
    test_option_normalizer.py
    test_makefile_generator.py
    test_build_script_generator.py
    test_build_log_parser.py
    test_build_probe_cli.py
    test_analyze_function_partial_build_workspace.py
```

生成先workspace例:

```text
workspace/
  Control_Update/
    extracted/
    generated/
    build/
    obj/
    bin/
    logs/
    reports/
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/vc6/dsp_models.py` 必要な場合のみ
- `src/unit_test_runner/harness/harness_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/source_models.py` 必要な場合のみ

---

## 16. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| VC6環境がない | 開発PCにVC6が入っていない | dry-runを既定にし、environment_missing reportを出す |
| PCH依存 | 本番sourceが`stdafx.h`前提 | PCH issueとして検出し、Step15で対処方針を検討する |
| include不足 | DSP includeだけでは足りない | C1083からmissing includeを抽出し、Step15へ渡す |
| unresolved symbol多発 | まだstub不足がある | LNK2001/LNK2019を抽出し、Step15でstub completionへ渡す |
| Makefile非互換 | VC6/nmakeの細部差異で失敗 | build.batとcompile commandをreportし、fixtureを増やして補正する |
| 生成コードVC6非互換 | Step13生成物にC99構文混入 | VC6 compatibility issueとして検出し、Step13へfeedbackする |
| build実行が重い | analyze-functionが遅くなる | build probe実行は明示オプションのみにする |
| 本番汚染 | workspace生成先を誤る | output_root検証とreport明記で外部workspace運用を徹底する |
| Step15責務の侵食 | エラーをここで直したくなる | Step14は診断抽出まで。自動補完はStep15へ委譲する |

---

## 17. Step 15 への接続

Step 14 完了後、Step 15 では Build Error Analyzer / Stub Completion Loop を実装する。
Step 15 は、Step 14 の `build_probe_report` に含まれる missing include、unresolved symbols、PCH issues、VC6 compatibility issues を使い、追加include候補、追加スタブ候補、生成コード修正候補、手動対応候補を生成する。

想定接続:

```python
build_workspace = generate_build_workspace(
    build_context=build_context,
    harness_report=harness_report,
    target_source=source_path,
)
build_probe = run_build_probe(
    build_workspace=build_workspace,
    run=True,
)
completion_plan = analyze_build_errors(
    build_workspace_report=build_workspace,
    build_probe_report=build_probe,
    call_report=call_report,
)
```

Step 15 で使う情報:

- missing includes
- unresolved symbols
- PCH issues
- VC6 compatibility issues
- generated file list
- compile units
- call_report stub candidates
- harness skeleton report

Step 14 の責務は、Build Error Analyzer が自動補完や手動対応候補を作れるように、ビルド失敗を構造化された診断情報として渡すことである。

---

## 18. まとめ

Step 14 は、Step 13 のスタブ・ハーネス雛形を、VC6 / nmake / cl.exe によるビルド検証へ進めるためのworkspaceへ構成するステップである。

このステップにより、対象source、生成ハーネス、生成スタブ、include path、define、Makefile、build script、build log、diagnosticsを `build_workspace_report` と `build_probe_report` として整理できる。

ただし、Step 14 はビルドエラーの自動修正やテスト実行を行う段階ではない。
ビルド準備と最初のbuild probe、ログ診断に責務を絞り、Step 15 の Build Error Analyzer / Stub Completion Loop へ安全な入力を渡すことを完了条件とする。

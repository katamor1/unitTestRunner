# Step 15: Build Error Analyzer / Stub Completion Loop 実装計画

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
- `docs/implementation/step14_build_workspace_build_probe_generator_plan.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第15ステップとして **Build Error Analyzer / Stub Completion Loop** を実装するための計画である。

Step 14 では、Step 13 のスタブ・ハーネス雛形と Step 04 の `build_context` を使い、VC6 / nmake / cl.exe でビルド試行できる build workspace を構成し、最初の build probe とログ診断を行う計画を定義した。

Step 15 では、Step 14 の `build_probe_report` に含まれる **missing include、unresolved symbols、PCH issues、VC6 compatibility issues、compiler diagnostics** を分析し、追加include候補、追加スタブ候補、生成コード修正候補、手動対応候補を `build_completion_plan` として生成する。

また、安全に自動適用できる一部の補完、たとえば **未解決外部参照に対する追加スタブ雛形生成**、**include path候補の追加提案**、**PCH設定の回避案生成** を、明示オプション付きで外部ワークスペースに反映できるようにする。

Step 15 の主な責務は以下である。

- build probe の診断情報を原因別に分類する
- missing include からinclude path追加候補・header抽出候補を作る
- unresolved symbol から追加スタブ候補を作る
- Step 09 の call_report と未解決symbolを照合する
- Step 13 の generated files とVC6 compatibility issueを照合する
- PCH issueに対して設定変更候補を作る
- 安全に生成可能な追加スタブ雛形を生成する
- 補完後のbuild probe再実行ループを制御する
- 自動適用した補完と手動対応が必要な補完を分離する
- `build_completion_plan.json` / Markdown を生成する
- `build_completion_iteration_report.json` / Markdown を生成する
- Step 16 の Test Execution / Evidence Preparation へ進めるかどうかの判定材料を作る

---

## 2. 目的

Step 15 の目的は、Step 14 の build probe で得られたエラーを、次に何をすべきかが分かる形へ変換し、必要に応じて安全な補完を反復することである。

具体的には、以下を実現する。

- `C1083` の include不足を一覧化し、候補include directoryや抽出候補headerを提示できる
- `LNK2001` / `LNK2019` の未解決外部参照を一覧化し、追加スタブ候補を生成できる
- 未解決symbolと Step 09 の `stub_candidates` / `calls` を照合し、関連callを特定できる
- Step 09で検出できなかった未解決symbolも `unknown_dependency_stub_candidate` として保持できる
- PCH関連エラー、例: `C1010` / `C1853` に対してPCH無効化、forced include、stdafx.h抽出などの対応候補を提示できる
- 生成CコードのVC6非互換疑いを検出し、Step 13 へ戻すべき修正候補として分類できる
- 追加スタブ雛形を外部ワークスペースに生成できる
- 補完後に build probe を再実行できる。ただし上限回数を持つ
- 自動補完した内容、未適用の候補、手動対応が必要な項目を追跡できる
- build probe が成功した場合、Step 16へ進める状態としてreportできる
- build probe が失敗し続ける場合、停止理由と次の手動対応を明示できる
- 本番リポジトリを変更しない

---

## 3. スコープ

### 3.1 実装対象

Step 15 で実装するもの:

1. Build error analyzer
   - missing include分類
   - unresolved symbol分類
   - PCH issue分類
   - VC6 compatibility issue分類
   - duplicate symbol候補分類
   - compiler error分類

2. Include completion planner
   - include名から候補pathを探索する
   - build_context include dirs内の存在確認
   - source root配下の候補探索、上限付き
   - include directory追加案
   - header copy案
   - manual required案

3. Stub completion planner
   - unresolved symbolから関数名候補を復元する
   - Step 09 call_reportとの照合
   - return type unknown時の保守的stub案
   - void / int / pointer placeholder方針
   - additional stub skeleton spec生成

4. PCH completion planner
   - `/Yu` 無効化案
   - forced include追加案
   - stdafx.h抽出案
   - PCH関連option変更案
   - manual review案

5. VC6 compatibility feedback planner
   - 生成ファイル起因のVC6非互換issueをStep 13修正候補へ分類
   - 本番source起因のissueをbuild_context / PCH / include問題候補へ分類
   - 禁止構文ヒント生成

6. Safe completion applier
   - 追加スタブ雛形生成
   - Makefile / build script の追加stub反映
   - include path候補の一時追加、明示オプション時のみ
   - 既存生成物の上書き制御

7. Completion loop runner
   - max iteration制御
   - 各iterationでbuild probe実行
   - 改善有無判定
   - ループ停止条件
   - iteration report生成

8. Reports
   - `build_completion_plan.json`
   - `build_completion_plan.md`
   - `build_completion_iteration_report.json`
   - `build_completion_iteration_report.md`
   - `completion_history.json`

9. CLI 接続
   - `analyze-build-errors` コマンド案
   - `complete-build` コマンド案
   - `build-probe --analyze-errors` 拡張案
   - `analyze-function --run-build-completion-loop` 明示オプション
   - status `completion_plan_generated` / `completion_applied` / `build_probe_succeeded` / `manual_action_required` を返す

10. Tests
   - missing include planning
   - unresolved symbol to stub planning
   - unknown unresolved symbol
   - PCH issue planning
   - VC6 compatibility feedback
   - safe stub generation
   - loop max iteration
   - no progress detection
   - report generation

### 3.2 対象外

Step 15 では以下を対象外とする。

- 本番リポジトリへの変更
- 本番 `.c` / `.h` / `.dsp` / `.dsw` の変更
- 期待結果の確定
- テスト実行と判定
- 実測カバレッジ計測
- 複雑な型情報を完全復元したスタブ生成
- C++ name mangling の完全復元
- ライブラリ依存の完全解決
- custom build step の完全再現
- PCH問題の完全自動解決
- include不足の無制限探索
- 無制限の自動修正ループ
- AIによる自動修正の無審査適用
- 疑似時間・疑似割込・ハードウェアI/O再現

Step 15 では、ビルドエラーを構造化し、安全な補完候補を生成・限定適用することに責務を絞る。

---

## 4. 入力と出力

### 4.1 入力

主入力:

- Step 04 の `build_context`
- Step 09 の `call_report`
- Step 13 の `harness_skeleton_report`
- Step 14 の `build_workspace_report`
- Step 14 の `build_probe_report`
- build workspace path
- source root path、任意
- completion policy

入力イメージ:

```json
{
  "function": "Control_Update",
  "build_context": "reports/build_context.json",
  "call_report": "reports/call_report.json",
  "harness_skeleton_report": "reports/harness_skeleton_report.json",
  "build_workspace_report": "reports/build_workspace_report.json",
  "build_probe_report": "reports/build_probe_report.json",
  "workspace": "D:/work/unit_test_workspace/Control_Update",
  "source_root": "D:/work/product"
}
```

### 4.2 出力

Step 15 の主要出力は build completion plan と iteration report である。

```text
workspace/
  Control_Update/
    generated/
      stubs/
        stub_ReadAdValue.c
        stub_ReadAdValue.h
    build/
      Makefile
      build.bat
    logs/
      completion_iter_001_build.log
      completion_iter_002_build.log
    reports/
      build_completion_plan.json
      build_completion_plan.md
      build_completion_iteration_report.json
      build_completion_iteration_report.md
      completion_history.json
      build_probe_report.json
```

`build_completion_iteration_report.json` は Step 16 以降の入力になる。

---

## 5. 基本方針

### 5.1 安全な補完のみ自動適用する

Step 15 では、すべてのビルドエラーを自動修正しない。
自動適用できるのは、外部ワークスペース内で完結し、本番コードを変更せず、比較的安全な補完に限定する。

自動適用してよい候補:

- 未解決外部参照に対する追加スタブ雛形生成
- 生成Makefileへの追加stub source登録
- generated include pathの追加
- 明示されたinclude directoryの一時追加

自動適用しない候補:

- 本番ソース修正
- 本番ヘッダ修正
- 本番DSP/DSW修正
- PCH設定の強制変更
- 複雑な型の推測による危険なstub生成
- 期待値確定
- テストケース内容の自動変更

### 5.2 反復回数を制限する

補完ループには上限を設ける。

既定方針:

- max_iterations = 3
- 同じdiagnosticが連続して出る場合は停止
- unresolved symbol数が減らない場合は停止
- include不足が解決しない場合は停止
- 新しいdiagnosticが増えすぎる場合は停止

### 5.3 すべての補完を記録する

自動適用・未適用・手動対応のすべてをreportに残す。

記録するもの:

- 元diagnostic
- 提案したcompletion action
- 自動適用したか
- 生成または変更したファイル
- 再build probe結果
- 改善有無
- 停止理由

---

## 6. データモデル設計

### 6.1 BuildCompletionRequest

```python
@dataclass
class BuildCompletionRequest:
    workspace_root: Path
    build_context: BuildContext
    call_report: CallReport
    harness_report: HarnessSkeletonReport
    build_workspace_report: BuildWorkspaceReport
    build_probe_report: BuildProbeReport
    source_root: Path | None
    policy: BuildCompletionPolicy
```

### 6.2 BuildCompletionPolicy

```python
@dataclass
class BuildCompletionPolicy:
    apply_safe_completions: bool
    run_probe_after_apply: bool
    max_iterations: int
    search_include_candidates: bool
    include_search_max_results: int
    generate_unknown_symbol_stubs: bool
    overwrite_existing_generated_stubs: bool
    stop_on_no_progress: bool
    stop_on_new_error_growth: bool
```

既定方針:

- `apply_safe_completions = false`
- `run_probe_after_apply = false`
- `max_iterations = 3`
- `search_include_candidates = true`
- `include_search_max_results = 20`
- `generate_unknown_symbol_stubs = true`
- `overwrite_existing_generated_stubs = false`
- `stop_on_no_progress = true`
- `stop_on_new_error_growth = true`

### 6.3 BuildCompletionPlan

```python
@dataclass
class BuildCompletionPlan:
    source_path: Path
    function_name: str
    status: str
    completion_actions: list[CompletionAction]
    include_completion_candidates: list[IncludeCompletionCandidate]
    stub_completion_candidates: list[StubCompletionCandidate]
    pch_completion_candidates: list[PchCompletionCandidate]
    compatibility_feedback_items: list[CompatibilityFeedbackItem]
    manual_action_items: list[ManualActionItem]
    warnings: list[BuildCompletionWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `planned` | 補完計画を生成した |
| `no_action_needed` | 補完不要 |
| `manual_action_required` | 自動補完では進めない |
| `blocked` | 必須情報不足 |

### 6.4 CompletionAction

```python
@dataclass
class CompletionAction:
    action_id: str
    action_kind: str
    source_diagnostic_code: str
    source_diagnostic_raw: str
    description: str
    apply_mode: str
    safety_level: str
    target_files: list[Path]
    expected_effect: str
    applied: bool
    result: str | None
    review_required: bool
```

`action_kind` 候補:

| action_kind | 意味 |
|---|---|
| `add_include_dir` | include directory追加候補 |
| `copy_header` | header copy候補 |
| `generate_stub` | 追加stub生成 |
| `register_stub_in_makefile` | Makefileへstub追加 |
| `adjust_pch_option` | PCH option調整候補 |
| `feedback_harness_generator` | Step 13生成器への修正feedback |
| `manual_action` | 手動対応 |

`apply_mode` 候補:

- `auto_safe`
- `manual_review`
- `not_applicable`

`safety_level` 候補:

- `safe`
- `moderate`
- `risky`
- `unknown`

### 6.5 IncludeCompletionCandidate

```python
@dataclass
class IncludeCompletionCandidate:
    include_name: str
    missing_from: Path | None
    candidate_paths: list[Path]
    candidate_include_dirs: list[Path]
    selected_action_id: str | None
    confidence: str
    review_required: bool
```

### 6.6 StubCompletionCandidate

```python
@dataclass
class StubCompletionCandidate:
    symbol_name: str
    function_name_candidate: str
    related_call_name: str | None
    related_call_id: str | None
    return_type_strategy: str
    parameter_strategy: str
    stub_source_path: Path
    stub_header_path: Path
    makefile_registration_required: bool
    confidence: str
    review_required: bool
    warnings: list[BuildCompletionWarning]
```

`return_type_strategy` 候補:

- `from_call_report`
- `default_int`
- `default_void`
- `manual_required`
- `unknown`

`parameter_strategy` 候補:

- `from_call_arguments`
- `empty_parameter_list`
- `manual_required`
- `unknown`

### 6.7 PchCompletionCandidate

```python
@dataclass
class PchCompletionCandidate:
    issue_kind: str
    header: str | None
    suggested_action: str
    action_id: str | None
    safety_level: str
    review_required: bool
```

### 6.8 CompatibilityFeedbackItem

```python
@dataclass
class CompatibilityFeedbackItem:
    issue_kind: str
    file: Path | None
    line_number: int | None
    suspected_generator: str | None
    suggested_fix: str
    feedback_target_step: str
    review_required: bool
```

### 6.9 ManualActionItem

```python
@dataclass
class ManualActionItem:
    item_id: str
    item_kind: str
    description: str
    reason: str
    suggested_action: str
    related_diagnostic_raw: str | None
```

`item_kind` 候補:

- `include_path_review`
- `pch_review`
- `complex_stub_signature`
- `library_dependency`
- `generated_code_fix`
- `target_source_issue`
- `manual_header_extraction`

### 6.10 BuildCompletionIterationReport

```python
@dataclass
class BuildCompletionIterationReport:
    source_path: Path
    function_name: str
    status: str
    iterations: list[CompletionIteration]
    final_build_probe_status: str
    final_diagnostics_summary: DiagnosticsSummary
    stop_reason: str
    next_recommended_action: str
    warnings: list[BuildCompletionWarning]
```

### 6.11 CompletionIteration

```python
@dataclass
class CompletionIteration:
    iteration_index: int
    input_probe_report: Path
    completion_plan: Path
    applied_actions: list[str]
    skipped_actions: list[str]
    generated_files: list[Path]
    probe_executed: bool
    probe_report: Path | None
    diagnostics_before: DiagnosticsSummary
    diagnostics_after: DiagnosticsSummary | None
    progress: str
```

`progress` 候補:

- `improved`
- `unchanged`
- `regressed`
- `succeeded`
- `not_run`

### 6.12 DiagnosticsSummary

```python
@dataclass
class DiagnosticsSummary:
    missing_include_count: int
    unresolved_symbol_count: int
    pch_issue_count: int
    vc6_compatibility_issue_count: int
    compiler_error_count: int
    compiler_warning_count: int
```

### 6.13 BuildCompletionWarning

```python
@dataclass
class BuildCompletionWarning:
    code: str
    message: str
    related_action_id: str | None = None
    related_symbol: str | None = None
    related_file: Path | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `include_candidate_not_unique` | include候補が複数ある |
| `include_candidate_not_found` | include候補が見つからない |
| `unknown_symbol_stub_generated` | unknown symbolに対して仮stubを生成した |
| `stub_signature_incomplete` | stub signatureが不完全 |
| `pch_issue_requires_manual_review` | PCH対応にレビューが必要 |
| `generated_code_feedback_required` | 生成器へのfeedbackが必要 |
| `completion_loop_no_progress` | 反復しても改善しない |
| `completion_loop_stopped_max_iterations` | 最大反復回数で停止した |
| `unsafe_action_skipped` | 危険な補完をskipした |
| `manual_action_required` | 手動対応が必要 |

---

## 7. 補完設計

### 7.1 基本アルゴリズム

処理フロー:

```text
analyze_build_errors(request)
  1. build_probe_report を読み込む
  2. missing includes を分類する
  3. unresolved symbols を分類する
  4. PCH issues を分類する
  5. VC6 compatibility issues を分類する
  6. call_report / harness_report と照合する
  7. include completion candidates を生成する
  8. stub completion candidates を生成する
  9. pch completion candidates を生成する
 10. compatibility feedback items を生成する
 11. completion actions を安全度付きで生成する
 12. manual action items を生成する
 13. build_completion_plan を返す
```

### 7.2 Missing include 補完

入力例:

```text
fatal error C1083: Cannot open include file: 'platform.h': No such file or directory
```

候補生成:

- build_context include dirs に存在するか確認
- source root配下を上限付きで探索
- generated / extracted include配下を確認
- 同名候補が1つなら `add_include_dir` または `copy_header` 候補
- 複数なら `include_candidate_not_unique` warning
- 見つからなければ manual action

自動適用方針:

- 既にworkspace配下にある候補include dirの追加はsafe候補
- source root配下からのcopyはmoderate、明示オプション時のみ
- 複数候補は自動適用しない

### 7.3 Unresolved symbol 補完

入力例:

```text
error LNK2001: unresolved external symbol _ReadAdValue
```

処理:

1. symbol名から先頭 `_` を除去する
2. `@NN` などstdcall風suffixがあれば除去候補を作る
3. Step 09 の `call_report.calls` と照合する
4. 一致すればcall引数情報からstub signatureを推定する
5. 一致しなければunknown dependencyとして扱う
6. 追加stub skeletonを生成候補にする

自動生成方針:

- call_reportに一致するexternal callがある場合はsafe寄り
- signatureが不明な場合は `int Function(void)` のような仮stubを生成しない方針を基本とする
- ただし `generate_unknown_symbol_stubs=true` の場合、review_requiredなmanual stub templateを生成してよい
- 生成したstubは必ず `review required` コメントを含める

### 7.4 PCH issue 補完

入力例:

```text
fatal error C1010: unexpected end of file while looking for precompiled header directive
```

候補:

- `/Yu` を無効化する
- `stdafx.h` をforced includeする
- target sourceに必要なPCH headerを抽出する
- Makefile上でPCH作成compile unitを追加する

方針:

- PCHはプロジェクトごとの事情が強いため、初期では自動適用しない
- `PchCompletionCandidate` と manual actionにする
- Step 15ではsuggestion生成までを基本とする

### 7.5 VC6 compatibility feedback

入力例:

```text
error C2065: 'i' : undeclared identifier
```

生成ファイル内で、かつ `for (int i = 0; ... )` が疑われる場合:

- `feedback_target_step = Step 13`
- `suggested_fix = move variable declaration to block beginning`
- manual actionではなく generator feedback として扱う

方針:

- Step 15では生成器を直接修正しない
- compatibility feedback itemとしてreportする
- 後続でStep 13 generator修正タスクへ戻す

### 7.6 Completion loop

補完ループの処理:

```text
run_completion_loop(request)
  1. current build_probe_report を読む
  2. completion_plan を生成する
  3. apply_safe_completions=trueならsafe actionを適用する
  4. run_probe_after_apply=trueならbuild probeを再実行する
  5. diagnostics summaryを比較する
  6. 成功なら終了
  7. 改善なしならstop_on_no_progressに従って停止
  8. max_iterations到達で停止
  9. iteration reportを生成する
```

progress判定:

- unresolved symbol countが減った → improved
- missing include countが減った → improved
- build succeeded → succeeded
- diagnostic総数が増えた → regressed候補
- 変化なし → unchanged

---

## 8. CLI 接続設計

### 8.1 analyze-build-errors コマンド案

build probe結果から補完計画だけを生成する。

```bat
unit-test-runner analyze-build-errors ^
  --build-workspace-report reports\build_workspace_report.json ^
  --build-probe-report reports\build_probe_report.json ^
  --call-report reports\call_report.json ^
  --harness-report reports\harness_skeleton_report.json ^
  --source-root D:\work\product ^
  --out reports\build_completion_plan.json
```

### 8.2 complete-build コマンド案

補完計画生成、safe補完適用、任意で再build probeを行う。

```bat
unit-test-runner complete-build ^
  --workspace D:\work\unit_test_workspace\Control_Update ^
  --apply-safe-completions ^
  --run-probe-after-apply ^
  --max-iterations 3
```

オプション案:

```text
--workspace PATH
--build-workspace-report PATH
--build-probe-report PATH
--call-report PATH
--harness-report PATH
--source-root PATH
--apply-safe-completions
--run-probe-after-apply
--max-iterations N
--generate-unknown-symbol-stubs
--overwrite-existing-generated-stubs
--json
```

### 8.3 analyze-function の Step 15 接続

Step 15 では、`analyze-function` からbuild completion loopまで進められるようにする。
ただし自動適用や再probeは明示オプションでのみ行う。

```bat
unit-test-runner analyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Control - Win32 Debug" ^
  --out D:\work\unit_test_workspace\Control_Update ^
  --run-build-probe ^
  --analyze-build-errors ^
  --apply-safe-completions
```

処理:

1. Step 04 から Step 14 までを実行または既存成果物を読み込む
2. Step 14 の build_probe_report を取得する
3. Step 15 の Build Error Analyzer を実行する
4. `build_completion_plan.json` / md を生成する
5. `--apply-safe-completions` 指定時のみsafe actionを適用する
6. `--run-probe-after-apply` 指定時のみ再build probeを実行する
7. `build_completion_iteration_report.json` / md を生成する
8. build probeが成功した場合は Step 16 に進める旨をmessageに含める
9. 失敗継続の場合はmanual action requiredをmessageに含める

---

## 9. Report 設計

### 9.1 build_completion_plan.json

例:

```json
{
  "schema_version": "0.1",
  "function": {
    "name": "Control_Update",
    "status": "planned"
  },
  "completion_actions": [
    {
      "action_id": "ACT_STUB_001",
      "action_kind": "generate_stub",
      "source_diagnostic_code": "LNK2001",
      "description": "Generate additional stub for ReadAdValue",
      "apply_mode": "auto_safe",
      "safety_level": "safe",
      "target_files": [
        "generated/stubs/stub_ReadAdValue.c",
        "generated/stubs/stub_ReadAdValue.h"
      ],
      "expected_effect": "Resolve unresolved external symbol ReadAdValue",
      "applied": false,
      "review_required": true
    }
  ],
  "stub_completion_candidates": [
    {
      "symbol_name": "_ReadAdValue",
      "function_name_candidate": "ReadAdValue",
      "related_call_name": "ReadAdValue",
      "return_type_strategy": "from_call_report",
      "parameter_strategy": "from_call_arguments",
      "confidence": "high",
      "review_required": true
    }
  ],
  "manual_action_items": [],
  "warnings": []
}
```

### 9.2 build_completion_plan.md

内容例:

```markdown
# Build Completion Plan

## Target

- Function: Control_Update
- Status: planned

## Completion Actions

| ID | Kind | Description | Apply Mode | Safety | Review |
|---|---|---|---|---|---|
| ACT_STUB_001 | generate_stub | Generate additional stub for ReadAdValue | auto_safe | safe | yes |

## Include Candidates

なし

## Stub Candidates

| Symbol | Function | Strategy | Confidence | Review |
|---|---|---|---|---|
| _ReadAdValue | ReadAdValue | from_call_report | high | yes |

## Manual Actions

なし
```

### 9.3 build_completion_iteration_report.json

例:

```json
{
  "schema_version": "0.1",
  "function": {
    "name": "Control_Update",
    "status": "manual_action_required"
  },
  "iterations": [
    {
      "iteration_index": 1,
      "applied_actions": ["ACT_STUB_001"],
      "generated_files": [
        "generated/stubs/stub_ReadAdValue.c",
        "generated/stubs/stub_ReadAdValue.h"
      ],
      "probe_executed": true,
      "progress": "improved",
      "diagnostics_before": {
        "unresolved_symbol_count": 3,
        "missing_include_count": 0
      },
      "diagnostics_after": {
        "unresolved_symbol_count": 2,
        "missing_include_count": 0
      }
    }
  ],
  "final_build_probe_status": "failed",
  "stop_reason": "manual action required for unresolved PCH issue",
  "next_recommended_action": "Review PCH settings and include stdafx.h strategy."
}
```

---

## 10. テスト計画

### 10.1 fixture 構成

```text
tests/
  fixtures/
    build_completion/
      missing_include/
        build_workspace_report.json
        build_probe_report.json
      unresolved_symbol_known_call/
        call_report.json
        build_probe_report.json
      unresolved_symbol_unknown/
      pch_issue/
      vc6_compatibility_generated/
      no_progress_loop/
      improved_loop/
      succeeded_after_completion/
```

### 10.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| CMP-001 | missing include plan | C1083 | include candidate生成 |
| CMP-002 | include multiple candidates | 同名複数 | warning include_candidate_not_unique |
| CMP-003 | include not found | 候補なし | manual action生成 |
| CMP-004 | unresolved known call | LNK + call_report一致 | stub candidate high |
| CMP-005 | unresolved unknown | LNKのみ | unknown stub candidate |
| CMP-006 | stdcall symbol | `_Foo@8` | Foo候補へ正規化 |
| CMP-007 | stub action | known call | generate_stub action生成 |
| CMP-008 | PCH C1010 | pch log | PCH candidate + manual review |
| CMP-009 | VC6 generated issue | generated file error | feedback Step13 |
| CMP-010 | apply safe stub | action safe | stub file生成 |
| CMP-011 | makefile registration | stub生成後 | Makefile更新候補 |
| CMP-012 | no overwrite | existing stub | skip + warning |
| CMP-013 | loop improved | unresolved減少 | progress improved |
| CMP-014 | loop no progress | 同一diagnostic | stop no progress |
| CMP-015 | loop max iterations | 上限到達 | stop max iterations |
| CMP-016 | build succeeded | second probe success | final succeeded |
| CMP-017 | report json | completion plan | JSON parse可能 |
| CMP-018 | report md | completion plan | expected sectionあり |
| CMP-019 | analyze-build-errors cli | explicit inputs | plan生成 |
| CMP-020 | complete-build cli dry-run | workspace | iteration report生成 |
| CMP-021 | analyze-function integration | Step04-15 | completion plan生成 |

### 10.3 テスト方針

- analyzerはfixture JSONのみで単体テストする
- applierは一時ディレクトリに対して生成結果を検証する
- completion loopはbuild probe runnerをmockする
- log parser自体はStep 14のfixtureを再利用する
- JSONは `json.loads()` で検証する
- Markdownは主要sectionの存在を検証する
- 本物のVC6環境はunit testでは要求しない

---

## 11. 実装タスク分解

### Task 15-01: Build completion model 定義

成果物:

- `src/unit_test_runner/build_completion/completion_models.py`
- `BuildCompletionRequest`
- `BuildCompletionPolicy`
- `BuildCompletionPlan`
- `CompletionAction`
- `IncludeCompletionCandidate`
- `StubCompletionCandidate`
- `PchCompletionCandidate`
- `CompatibilityFeedbackItem`
- `ManualActionItem`
- `BuildCompletionIterationReport`
- `CompletionIteration`
- `DiagnosticsSummary`
- `BuildCompletionWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 15-02: Diagnostic classifier

成果物:

- `src/unit_test_runner/build_completion/diagnostic_classifier.py`
- missing include / unresolved / PCH / compatibility分類
- diagnostics summary生成

完了条件:

- CMP-001 / CMP-004 / CMP-008 / CMP-009 が通る

### Task 15-03: Include completion planner

成果物:

- `src/unit_test_runner/build_completion/include_completion.py`
- include candidate探索
- include dir追加案
- manual action生成

完了条件:

- CMP-001 / CMP-002 / CMP-003 が通る

### Task 15-04: Symbol normalizer

成果物:

- `src/unit_test_runner/build_completion/symbol_normalizer.py`
- `_Foo` → `Foo`
- `_Foo@8` → `Foo`
- decoration候補保持

完了条件:

- CMP-006 が通る

### Task 15-05: Stub completion planner

成果物:

- `src/unit_test_runner/build_completion/stub_completion.py`
- unresolved symbolとcall_report照合
- known / unknown stub候補生成
- generate_stub action生成

完了条件:

- CMP-004 / CMP-005 / CMP-007 が通る

### Task 15-06: PCH completion planner

成果物:

- `src/unit_test_runner/build_completion/pch_completion.py`
- PCH issue候補生成
- manual review action生成

完了条件:

- CMP-008 が通る

### Task 15-07: Compatibility feedback planner

成果物:

- `src/unit_test_runner/build_completion/compatibility_feedback.py`
- generated file issue判定
- feedback target step判定

完了条件:

- CMP-009 が通る

### Task 15-08: Safe completion applier

成果物:

- `src/unit_test_runner/build_completion/completion_applier.py`
- additional stub skeleton生成
- Makefile registration候補反映
- overwrite policy対応

完了条件:

- CMP-010 / CMP-011 / CMP-012 が通る

### Task 15-09: Completion loop runner

成果物:

- `src/unit_test_runner/build_completion/completion_loop.py`
- max iteration
- no progress判定
- mock build probe runner連携
- iteration report生成

完了条件:

- CMP-013 / CMP-014 / CMP-015 / CMP-016 が通る

### Task 15-10: Build completion analyzer統合

成果物:

- `src/unit_test_runner/build_completion/build_completion_analyzer.py`
- classifier / planners統合
- build_completion_plan生成

完了条件:

- representative fixtureでcompletion planが生成される

### Task 15-11: Report writer

成果物:

- `src/unit_test_runner/build_completion/completion_report_writer.py`
- `reports/build_completion_markdown.py`
- `reports/build_completion_iteration_markdown.py`
- JSON / Markdown出力

完了条件:

- CMP-017 / CMP-018 が通る

### Task 15-12: analyze-build-errors CLI 実装

成果物:

- `analyze-build-errors` コマンド
- explicit input対応
- source_root対応
- JSON出力対応

完了条件:

- CMP-019 が通る

### Task 15-13: complete-build CLI 実装

成果物:

- `complete-build` コマンド
- `--apply-safe-completions`
- `--run-probe-after-apply`
- `--max-iterations`
- dry-run対応

完了条件:

- CMP-020 が通る

### Task 15-14: analyze-function 接続

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
- Step 14 build_workspace / build_probe生成
- Step 15 completion_plan生成
- 明示オプション時のみsafe completion適用
- CLI `analyze-function` の出力更新

完了条件:

- CMP-021 が通る

### Task 15-15: fixture / test 整備

成果物:

- `tests/fixtures/build_completion/...`
- `tests/unit/test_diagnostic_classifier.py`
- `tests/unit/test_include_completion.py`
- `tests/unit/test_symbol_normalizer.py`
- `tests/unit/test_stub_completion.py`
- `tests/unit/test_pch_completion.py`
- `tests/unit/test_completion_applier.py`
- `tests/unit/test_completion_loop.py`
- `tests/unit/test_completion_report_writer.py`
- `tests/unit/test_analyze_build_errors_cli.py`
- `tests/unit/test_complete_build_cli.py`
- `tests/unit/test_analyze_function_partial_completion.py`

完了条件:

- CMP-001 から CMP-021 が通る

---

## 12. 受け入れ基準

Step 15 は、以下をすべて満たしたら完了とする。

1. build_probe_reportからmissing includeを分類できる
2. missing includeに対してinclude candidate / manual actionを生成できる
3. unresolved symbolを分類できる
4. decorated symbolを関数名候補へ正規化できる
5. unresolved symbolとcall_reportを照合できる
6. known external callに対する追加stub candidateを生成できる
7. unknown symbolに対するmanualまたはreview_required stub candidateを生成できる
8. PCH issueに対する対応候補を生成できる
9. VC6 compatibility issueをStep 13等へのfeedbackとして分類できる
10. safe completion actionを区別できる
11. 明示オプション時のみsafe completionを適用できる
12. 追加stub skeletonを外部workspaceに生成できる
13. Makefile / build workspaceへ追加stubを反映する候補を生成できる
14. completion loopをmax iteration付きで実行できる
15. no progressを検出して停止できる
16. completion historyを記録できる
17. build_completion_plan.jsonを生成できる
18. build_completion_plan.mdを生成できる
19. build_completion_iteration_report.jsonを生成できる
20. build_completion_iteration_report.mdを生成できる
21. `analyze-build-errors` が明示入力からplanを生成できる
22. `complete-build` がsafe補完と任意probe再実行を制御できる
23. `analyze-function` が Step 15 時点では build completion plan生成まで進み、必要に応じてsafe completion loopを実行できる
24. Step 16 に進めるか、manual action requiredかをreportできる
25. 本番リポジトリを変更しない
26. 無制限の自動修正へ踏み込みすぎていない
27. テスト実行や期待結果確定へ踏み込みすぎていない

---

## 13. 成果物

Step 15 の成果物は以下とする。

```text
src/
  unit_test_runner/
    build_completion/
      __init__.py
      completion_models.py
      diagnostic_classifier.py
      include_completion.py
      symbol_normalizer.py
      stub_completion.py
      pch_completion.py
      compatibility_feedback.py
      completion_applier.py
      completion_loop.py
      build_completion_analyzer.py
      completion_report_writer.py
    reports/
      build_completion_markdown.py
      build_completion_iteration_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    build_completion/
      missing_include/
      unresolved_symbol_known_call/
      unresolved_symbol_unknown/
      pch_issue/
      vc6_compatibility_generated/
      no_progress_loop/
      improved_loop/
      succeeded_after_completion/
  unit/
    test_diagnostic_classifier.py
    test_include_completion.py
    test_symbol_normalizer.py
    test_stub_completion.py
    test_pch_completion.py
    test_completion_applier.py
    test_completion_loop.py
    test_completion_report_writer.py
    test_analyze_build_errors_cli.py
    test_complete_build_cli.py
    test_analyze_function_partial_completion.py
```

生成先workspace例:

```text
workspace/
  Control_Update/
    generated/
      stubs/
    logs/
    reports/
      build_completion_plan.json
      build_completion_plan.md
      build_completion_iteration_report.json
      build_completion_iteration_report.md
      completion_history.json
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/build/build_models.py` 必要な場合のみ
- `src/unit_test_runner/build/build_probe_runner.py` 必要な場合のみ
- `src/unit_test_runner/harness/stub_generator.py` 必要な場合のみ
- `src/unit_test_runner/harness/harness_models.py` 必要な場合のみ

---

## 14. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| 誤ったstub生成 | signature不明のsymbolに危険なstubを生成する | unknown symbolはreview_requiredにし、既定では保守的にmanual templateにする |
| include候補誤選択 | 同名headerが複数ある | 複数候補は自動適用せずmanual actionにする |
| PCH自動修正の危険 | PCHは案件依存が強い | 自動適用せずcandidateとmanual actionにする |
| ループ暴走 | 補完とprobeを繰り返し続ける | max_iterationsとno progress stopを必須にする |
| エラー増加 | 補完で新たなエラーが増える | diagnostics summaryでregressedを検出し停止する |
| 本番汚染 | 補完を本番側に適用してしまう | applierはworkspace配下のみ許可する |
| Step16責務の侵食 | build成功後にテスト実行まで進めたくなる | Step15はbuild completionまで。実行はStep16へ委譲する |
| 生成器feedbackの放置 | VC6非互換がStep13に戻らない | compatibility feedback itemにfeedback_target_stepを必ず持たせる |

---

## 15. Step 16 への接続

Step 15 完了後、Step 16 では Test Execution / Evidence Preparation を実装する。
Step 16 は、Step 15 の結果として build probe が成功した場合に、生成されたテストバイナリまたはprobe executableを実行し、test log、result csv、evidence markdownを作る。

想定接続:

```python
completion_report = run_completion_loop(
    build_workspace_report=build_workspace,
    build_probe_report=build_probe,
    call_report=call_report,
)
if completion_report.final_build_probe_status == "succeeded":
    evidence = prepare_test_execution_evidence(
        workspace=workspace,
        test_case_draft=test_case_draft,
        harness_report=harness_report,
        completion_report=completion_report,
    )
```

Step 16 で使う情報:

- build probe final status
- generated executable path
- test case draft
- harness skeleton report
- completion history
- unresolved placeholders
- manual action items

Step 15 の責務は、Step 16へ進める状態かどうかを明確にし、進めない場合はmanual action requiredとして理由を構造化することである。

---

## 16. まとめ

Step 15 は、Step 14 のbuild probeで得られた失敗情報を、次のアクションに変換するステップである。

このステップにより、include不足、未解決symbol、PCH問題、VC6非互換生成コードを分類し、追加スタブやinclude候補、PCH対処案、生成器feedback、手動対応項目を `build_completion_plan` として整理できる。

必要に応じてsafe completionを外部workspace内で適用し、build probeを反復できる。ただし、補完ループには上限を設け、本番リポジトリは変更しない。

Step 15 はテスト実行や期待結果確定を行う段階ではない。
ビルド補完と診断整理に責務を絞り、Step 16 の Test Execution / Evidence Preparation へ安全な入力を渡すことを完了条件とする。

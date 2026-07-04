# Step 16: Test Execution / Evidence Preparation 実装計画

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
- `docs/implementation/step15_build_error_analyzer_stub_completion_loop_plan.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第16ステップとして **Test Execution / Evidence Preparation** を実装するための計画である。

Step 15 では、Step 14 の build probe で得られた missing include、unresolved symbols、PCH issues、VC6 compatibility issues を分析し、安全な補完を限定的に適用し、Step 16 へ進めるかどうかを判定する計画を定義した。

Step 16 では、Step 15 の結果として build probe が成功した場合、またはユーザーが明示的に実行を許可した場合に、生成されたテスト実行ファイルを起動し、**test log、result csv、execution report、evidence package** を生成する。

ここでの実行は、本番アプリケーション全体の実行ではない。
Step 13 から Step 15 で生成・ビルドした関数単位テスト用の外部ワークスペース内バイナリを対象とする。

Step 16 の主な責務は以下である。

- build probe 成功後の実行可能ファイルを特定する
- 明示オプション指定時のみテスト実行する
- 実行コマンド、環境情報、開始時刻、終了時刻、終了コードを記録する
- stdout / stderr / combined log を保存する
- 生成runnerの出力を解析し、テスト件数、成功、失敗、skip、assert失敗を抽出する
- `test_result.json` / `test_result.csv` / `test_execution_report.md` を生成する
- `test_case_draft`、`harness_skeleton_report`、`build_probe_report`、`build_completion_iteration_report` と結果を関連付ける
- 未確定期待値placeholderを含むテストを review required として扱う
- 実行ログ、ビルドログ、入力条件、生成物一覧、hash情報をまとめた evidence package を生成する
- Step 17 の Function Dossier Finalizer / Review Workflow に渡せる成果物を整理する

---

## 2. 目的

Step 16 の目的は、関数単位テスト用に生成・ビルドした成果物を実行し、レビュー・監査・再現に使えるエビデンスを作ることである。

具体的には、以下を実現する。

- build probe 成功済みの workspace から実行対象バイナリを特定できる
- テスト実行を明示オプションで制御できる
- timeout付きでテスト実行できる
- stdout / stderr / combined log を保存できる
- runner出力からテスト結果を抽出できる
- assert失敗箇所、失敗test case、失敗messageを抽出できる
- `test_case_draft` の test case ID と実行結果を対応付けられる
- placeholderを含むテストを `review_required` または `inconclusive` として扱える
- result csv を生成し、レビュー表やExcelへ持ち出せる
- execution report Markdown を生成し、人間が結果を確認できる
- evidence manifest に入力ファイル、生成ファイル、ログ、hash、実行環境情報を記録できる
- build成功、test実行、test結果、未解決項目を1つの evidence package としてまとめられる
- 本番リポジトリを変更せず、外部ワークスペース内で完結できる

---

## 3. スコープ

### 3.1 実装対象

Step 16 で実装するもの:

1. Test execution model
   - execution request
   - execution policy
   - executable metadata
   - command result
   - parsed test result
   - evidence manifest
   - warning / diagnostic

2. Executable resolver
   - `build_probe_report` から生成バイナリ候補を取得する
   - `bin/utr_probe.exe` など既定名を探索する
   - 実行可能ファイルの存在確認
   - hash記録

3. Test execution runner
   - timeout付きプロセス実行
   - stdout / stderr 保存
   - combined log 保存
   - working directory指定
   - environment capture
   - dry-run mode

4. Runner output parser
   - total / passed / failed / skipped 抽出
   - test case ID 抽出
   - assert failure抽出
   - file / line 抽出
   - unknown output保持

5. Result mapper
   - `test_case_draft` と実行結果の対応付け
   - coverage target placeholderとの対応付け
   - stub call observation placeholderとの対応付け
   - unresolved / review_required項目の反映

6. Evidence package generator
   - evidence manifest
   - source hash一覧
   - generated file hash一覧
   - build log一覧
   - test log一覧
   - result csv
   - execution report
   - unresolved item一覧

7. Reports
   - `test_execution_report.json`
   - `test_execution_report.md`
   - `test_result.json`
   - `test_result.csv`
   - `evidence_manifest.json`
   - `evidence_package.md`

8. CLI 接続
   - `run-tests` コマンド案
   - `prepare-evidence` コマンド案
   - `analyze-function --run-tests` 明示オプション
   - `build-probe` / `complete-build` 後の成果物を利用する
   - status `test_executed` / `test_failed` / `test_inconclusive` / `evidence_prepared` を返す

9. Tests
   - executable resolver
   - dry-run execution
   - successful runner output parse
   - failed runner output parse
   - timeout handling
   - placeholder / review_required handling
   - result csv output
   - evidence manifest output
   - CLI integration

### 3.2 対象外

Step 16 では以下を対象外とする。

- 本番アプリケーション全体の実行
- 本番機ハードウェアI/Oの実行
- 32ms時間制約の評価
- 疑似時間・疑似割込の本格実装
- 実測カバレッジ計測
- coverage instrumentation埋め込み
- 期待結果の自動確定
- 失敗テストの自動修正
- スタブ動作仕様の自動変更
- ビルドエラー自動補完
- CI環境構築
- 本番リポジトリへのエビデンス格納
- PDFやExcelなどの正式帳票生成

Step 16 では、外部ワークスペース内の関数単位テスト実行とエビデンス準備に限定する。

---

## 4. 入力と出力

### 4.1 入力

主入力:

- Step 12 の `test_case_draft`
- Step 13 の `harness_skeleton_report`
- Step 14 の `build_workspace_report`
- Step 14 の `build_probe_report`
- Step 15 の `build_completion_iteration_report`
- 実行対象workspace path
- 実行ポリシー

入力イメージ:

```json
{
  "function": "Control_Update",
  "workspace": "D:/work/unit_test_workspace/Control_Update",
  "test_case_draft": "reports/test_case_draft.json",
  "harness_skeleton_report": "reports/harness_skeleton_report.json",
  "build_workspace_report": "reports/build_workspace_report.json",
  "build_probe_report": "reports/build_probe_report.json",
  "build_completion_iteration_report": "reports/build_completion_iteration_report.json",
  "execution": {
    "run_tests": true,
    "timeout_seconds": 60,
    "dry_run": false
  }
}
```

### 4.2 出力

Step 16 の主要出力は test execution report と evidence package である。

```text
workspace/
  Control_Update/
    bin/
      utr_probe.exe
    logs/
      test_stdout.log
      test_stderr.log
      test_execution.log
    reports/
      test_execution_report.json
      test_execution_report.md
      test_result.json
      test_result.csv
      evidence_manifest.json
      evidence_package.md
      unresolved_review_items.md
```

`evidence_manifest.json` と `evidence_package.md` は Step 17 以降の入力になる。

---

## 5. 基本方針

### 5.1 明示実行のみ

Step 16では、テスト実行は明示オプションが指定された場合のみ行う。

理由:

- 実行環境依存がある
- 生成テストには `TBD` placeholderが残る場合がある
- ユーザーが意図しないバイナリ実行を避ける
- VS Code連携時にも安全側に倒す

既定では evidence preparation の dry-run または実行準備確認までとする。

### 5.2 placeholderを成功扱いしない

期待値未確定の `TBD_EXPECTED_*` を含むテストが実行できても、仕様上の合格とは扱わない。

方針:

- `TBD` placeholderを検出したtest caseは `review_required` または `inconclusive`
- runner上はpassしても、evidence上は `pass_with_review_required` として扱えるようにする
- 期待結果が確定済みかどうかを evidence に明記する

### 5.3 実行ログを一次証跡として保持する

標準出力、標準エラー、combined log、実行コマンド、終了コード、実行時間を保存する。

方針:

- stdout / stderr は加工前ログを保存する
- parserで抽出した結果は別ファイルにする
- evidence manifestにはraw log hashを記録する
- 解析失敗時もraw logを残す

---

## 6. データモデル設計

### 6.1 TestExecutionRequest

```python
@dataclass
class TestExecutionRequest:
    workspace_root: Path
    test_case_draft: TestCaseDraftReport
    harness_report: HarnessSkeletonReport
    build_workspace_report: BuildWorkspaceReport
    build_probe_report: BuildProbeReport
    completion_iteration_report: BuildCompletionIterationReport | None
    policy: TestExecutionPolicy
```

### 6.2 TestExecutionPolicy

```python
@dataclass
class TestExecutionPolicy:
    run_tests: bool
    dry_run: bool
    timeout_seconds: int
    require_successful_build_probe: bool
    allow_placeholder_tests: bool
    treat_placeholder_as_inconclusive: bool
    capture_environment: bool
    overwrite_existing_logs: bool
```

既定方針:

- `run_tests = false`
- `dry_run = true`
- `timeout_seconds = 60`
- `require_successful_build_probe = true`
- `allow_placeholder_tests = true`
- `treat_placeholder_as_inconclusive = true`
- `capture_environment = true`
- `overwrite_existing_logs = false`

### 6.3 ExecutableInfo

```python
@dataclass
class ExecutableInfo:
    path: Path
    exists: bool
    sha256: str | None
    generated_from: str | None
    build_probe_status: str
    warnings: list[TestExecutionWarning]
```

### 6.4 TestExecutionReport

```python
@dataclass
class TestExecutionReport:
    source_path: Path | None
    function_name: str
    status: str
    executed: bool
    executable: ExecutableInfo | None
    command: ExecutionCommand | None
    command_result: ExecutionCommandResult | None
    parsed_result: TestResultSummary | None
    case_results: list[TestCaseExecutionResult]
    unresolved_review_items: list[ExecutionReviewItem]
    evidence_files: list[EvidenceFile]
    warnings: list[TestExecutionWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `not_run` | 実行していない |
| `executed` | 実行した |
| `passed` | 実行結果が全pass |
| `failed` | 失敗testあり |
| `inconclusive` | placeholder等により判定保留 |
| `timeout` | 実行timeout |
| `blocked` | 実行前提不足 |
| `environment_error` | 実行環境エラー |

### 6.5 ExecutionCommand

```python
@dataclass
class ExecutionCommand:
    command_line: str
    working_directory: Path
    environment_summary: dict[str, str]
    timeout_seconds: int
    dry_run: bool
```

### 6.6 ExecutionCommandResult

```python
@dataclass
class ExecutionCommandResult:
    exit_code: int | None
    started_at: str | None
    finished_at: str | None
    duration_ms: int | None
    stdout_log: Path | None
    stderr_log: Path | None
    combined_log: Path | None
    timed_out: bool
```

### 6.7 TestResultSummary

```python
@dataclass
class TestResultSummary:
    total: int
    passed: int
    failed: int
    skipped: int
    inconclusive: int
    assertion_failures: int
    parser_confidence: str
```

### 6.8 TestCaseExecutionResult

```python
@dataclass
class TestCaseExecutionResult:
    test_case_id: str | None
    generated_function_name: str | None
    status: str
    exit_related: bool
    assertions: list[AssertionResult]
    related_coverage_ids: list[str]
    review_required: bool
    evidence: str
    warnings: list[TestExecutionWarning]
```

`status` 候補:

- `passed`
- `failed`
- `skipped`
- `inconclusive`
- `not_found_in_output`
- `unknown`

### 6.9 AssertionResult

```python
@dataclass
class AssertionResult:
    assertion_kind: str
    status: str
    file: Path | None
    line_number: int | None
    expected: str | None
    actual: str | None
    expression: str | None
    message: str | None
```

### 6.10 ExecutionReviewItem

```python
@dataclass
class ExecutionReviewItem:
    item_id: str
    item_kind: str
    related_test_case_id: str | None
    description: str
    suggested_action: str
    severity: str
```

`item_kind` 候補:

- `placeholder_expected_value`
- `placeholder_input_value`
- `unmapped_test_output`
- `test_case_not_executed`
- `runner_output_parse_failed`
- `build_not_successful`
- `manual_result_review_required`

### 6.11 EvidenceManifest

```python
@dataclass
class EvidenceManifest:
    function_name: str
    workspace_root: Path
    created_at: str
    source_files: list[EvidenceFile]
    generated_files: list[EvidenceFile]
    build_reports: list[EvidenceFile]
    test_reports: list[EvidenceFile]
    logs: list[EvidenceFile]
    unresolved_items: list[ExecutionReviewItem]
    summary: EvidenceSummary
```

### 6.12 EvidenceFile

```python
@dataclass
class EvidenceFile:
    path: Path
    file_kind: str
    sha256: str | None
    required: bool
    description: str
```

`file_kind` 候補:

- `source`
- `generated_source`
- `build_report`
- `completion_report`
- `test_log`
- `test_result_json`
- `test_result_csv`
- `execution_report`
- `evidence_markdown`
- `manifest`

### 6.13 EvidenceSummary

```python
@dataclass
class EvidenceSummary:
    build_probe_status: str
    test_execution_status: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    inconclusive_tests: int
    unresolved_review_count: int
    ready_for_review: bool
```

### 6.14 TestExecutionWarning

```python
@dataclass
class TestExecutionWarning:
    code: str
    message: str
    related_test_case_id: str | None = None
    related_file: Path | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `build_probe_not_successful` | build probeが成功していない |
| `executable_not_found` | 実行ファイルが見つからない |
| `test_execution_timeout` | テスト実行がtimeoutした |
| `runner_output_parse_failed` | runner出力解析に失敗した |
| `placeholder_detected` | TBD placeholderが残っている |
| `test_case_not_mapped` | runner出力とtest_case_draftを対応付けられない |
| `unexpected_exit_code` | 予期しない終了コード |
| `environment_capture_failed` | 実行環境情報取得に失敗した |
| `evidence_file_missing` | evidence対象ファイルが見つからない |

---

## 7. 実行設計

### 7.1 基本アルゴリズム

処理フロー:

```text
prepare_test_execution_evidence(request)
  1. build_probe_report / completion_iteration_report を確認する
  2. 実行可能ファイルを解決する
  3. 実行前提を検証する
  4. run_tests=falseなら not_run report を生成する
  5. run_tests=trueなら timeout付きで実行する
  6. stdout / stderr / combined log を保存する
  7. runner output をparseする
  8. test_case_draft とcase resultを対応付ける
  9. placeholder / review_requiredを反映する
 10. test_result.json / csv を生成する
 11. test_execution_report.json / md を生成する
 12. evidence_manifest.json / evidence_package.md を生成する
```

### 7.2 実行前提検証

確認項目:

- build_probe_report.status が `succeeded` である
- 実行ファイルが存在する
- 実行ファイルのhashを取得できる
- test_case_draftが存在する
- harness_skeleton_reportが存在する
- unresolved placeholderが残っているか
- userがrun_testsを明示しているか

方針:

- `require_successful_build_probe=true` の場合、build成功していなければ実行しない
- placeholderが残っていても `allow_placeholder_tests=true` なら実行可。ただし結果はinconclusive候補
- 実行前提不足は `blocked` としてreportする

### 7.3 Runner output parser

初期runner出力の想定例:

```text
[ RUN      ] TC_Control_Update_001
[       OK ] TC_Control_Update_001
[ RUN      ] TC_Control_Update_002
[  FAILED  ] TC_Control_Update_002
assert failed: expected=0 actual=1 file=test_Control_Update.c line=120 expr=actual_return
[ SUMMARY  ] total=2 passed=1 failed=1 skipped=0
```

抽出:

- test case start
- OK / FAILED / SKIPPED
- assert failed line
- expected / actual
- file / line
- summary

方針:

- runner出力形式はStep 13 runnerに合わせる
- 解析不能な行は unknown output として保持する
- summaryがなくてもtest case行から可能な限り集計する
- parser confidenceを `high` / `medium` / `low` で持つ

### 7.4 Placeholder handling

検出対象:

- `TBD_EXPECTED_RETURN_INT`
- `TBD_EXPECTED_GLOBAL_*`
- `TBD_VALID_*`
- `review required` コメント由来のmetadata
- Step 12の `expected_result_not_determined`
- Step 13の `unresolved_placeholders`

方針:

- placeholderが関連するtest caseは `review_required=true`
- 実行上passしていても evidence summaryでは `inconclusive` に含めることができる
- `treat_placeholder_as_inconclusive=false` の場合のみrunner結果を優先する

### 7.5 Evidence package生成

Evidence package に含めるもの:

- source path / source hash
- build context summary
- generated file list / hash
- build workspace report
- build probe report
- completion iteration report
- test case draft
- test execution report
- test result json / csv
- raw logs
- unresolved review items

方針:

- すべてを1つのzipにする処理はStep 16では任意。初期はmanifestとMarkdownで整理する
- zip化が必要なら Step 17 以降で対応する
- evidence_manifestは機械処理向け
- evidence_package.mdはレビュー向け

---

## 8. CLI 接続設計

### 8.1 run-tests コマンド案

```bat
unit-test-runner run-tests ^
  --workspace D:\work\unit_test_workspace\Control_Update ^
  --run ^
  --timeout 60
```

明示入力形式:

```bat
unit-test-runner run-tests ^
  --test-case-draft reports\test_case_draft.json ^
  --harness-report reports\harness_skeleton_report.json ^
  --build-workspace-report reports\build_workspace_report.json ^
  --build-probe-report reports\build_probe_report.json ^
  --completion-report reports\build_completion_iteration_report.json ^
  --executable bin\utr_probe.exe ^
  --out D:\work\unit_test_workspace\Control_Update ^
  --run
```

オプション案:

```text
--workspace PATH
--executable PATH
--run
--dry-run
--timeout SECONDS
--allow-placeholder-tests
--treat-placeholder-as-inconclusive
--json
```

### 8.2 prepare-evidence コマンド案

テスト実行済みまたは未実行のworkspaceからevidence packageを作る。

```bat
unit-test-runner prepare-evidence ^
  --workspace D:\work\unit_test_workspace\Control_Update ^
  --out D:\work\unit_test_workspace\Control_Update\reports
```

用途:

- 実行を伴わず、既存ログとreportをまとめる
- 手動実行済みログを後から取り込む余地を残す
- evidence_manifestとevidence_package.mdを再生成する

### 8.3 analyze-function の Step 16 接続

Step 16 では、`analyze-function` からテスト実行とevidence準備まで進められるようにする。
ただし、テスト実行は明示オプションでのみ行う。

```bat
unit-test-runner analyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Control - Win32 Debug" ^
  --out D:\work\unit_test_workspace\Control_Update ^
  --run-build-probe ^
  --analyze-build-errors ^
  --apply-safe-completions ^
  --run-tests
```

処理:

1. Step 04 から Step 15 までを実行または既存成果物を読み込む
2. build probe最終状態を確認する
3. Step 16 の Test Execution Runner を実行する、またはdry-runする
4. `test_execution_report.json` / md を生成する
5. `test_result.json` / csv を生成する
6. `evidence_manifest.json` を生成する
7. `evidence_package.md` を生成する
8. Step 17 の Function Dossier Finalizer / Review Workflow が必要である旨をmessageに含める

---

## 9. Report 設計

### 9.1 test_execution_report.json

例:

```json
{
  "schema_version": "0.1",
  "function": {
    "name": "Control_Update",
    "status": "inconclusive"
  },
  "executed": true,
  "executable": {
    "path": "bin/utr_probe.exe",
    "exists": true,
    "sha256": "...",
    "build_probe_status": "succeeded"
  },
  "command_result": {
    "exit_code": 1,
    "duration_ms": 320,
    "stdout_log": "logs/test_stdout.log",
    "stderr_log": "logs/test_stderr.log",
    "combined_log": "logs/test_execution.log",
    "timed_out": false
  },
  "parsed_result": {
    "total": 2,
    "passed": 1,
    "failed": 1,
    "skipped": 0,
    "inconclusive": 1,
    "assertion_failures": 1,
    "parser_confidence": "high"
  },
  "case_results": [
    {
      "test_case_id": "TC_Control_Update_001",
      "status": "inconclusive",
      "review_required": true,
      "related_coverage_ids": ["BR_Control_Update_001_TRUE"],
      "evidence": "runner passed, but expected value placeholder remains"
    }
  ],
  "warnings": [
    {
      "code": "placeholder_detected",
      "message": "TBD expected value remains in generated test."
    }
  ]
}
```

### 9.2 test_result.csv

列案:

```csv
test_case_id,status,review_required,coverage_ids,assertion_failures,expected,actual,evidence,warnings
TC_Control_Update_001,inconclusive,true,BR_Control_Update_001_TRUE,0,,,runner passed but placeholder remains,placeholder_detected
TC_Control_Update_002,failed,true,BR_Control_Update_001_FALSE,1,0,1,assert failed at test_Control_Update.c:120,expected_result_not_determined
```

### 9.3 evidence_manifest.json

例:

```json
{
  "schema_version": "0.1",
  "function": "Control_Update",
  "workspace_root": "D:/work/unit_test_workspace/Control_Update",
  "created_at": "2026-07-04T00:00:00+09:00",
  "summary": {
    "build_probe_status": "succeeded",
    "test_execution_status": "inconclusive",
    "total_tests": 2,
    "passed_tests": 1,
    "failed_tests": 1,
    "inconclusive_tests": 1,
    "unresolved_review_count": 3,
    "ready_for_review": true
  },
  "logs": [
    {
      "path": "logs/test_execution.log",
      "file_kind": "test_log",
      "sha256": "...",
      "required": true
    }
  ],
  "test_reports": [
    {
      "path": "reports/test_execution_report.json",
      "file_kind": "execution_report",
      "sha256": "...",
      "required": true
    }
  ]
}
```

### 9.4 evidence_package.md

内容例:

```markdown
# Function Unit Test Evidence Package

## Target

- Function: Control_Update
- Workspace: D:/work/unit_test_workspace/Control_Update
- Build Probe Status: succeeded
- Test Execution Status: inconclusive

## Summary

| Item | Count |
|---|---:|
| Total Tests | 2 |
| Passed | 1 |
| Failed | 1 |
| Inconclusive | 1 |
| Review Items | 3 |

## Test Results

| Test Case | Status | Review | Coverage | Evidence |
|---|---|---|---|---|
| TC_Control_Update_001 | inconclusive | yes | BR_Control_Update_001_TRUE | runner passed but placeholder remains |
| TC_Control_Update_002 | failed | yes | BR_Control_Update_001_FALSE | assert failed at test_Control_Update.c:120 |

## Evidence Files

| File | Kind | SHA-256 |
|---|---|---|
| logs/test_execution.log | test_log | ... |
| reports/test_result.csv | test_result_csv | ... |
| reports/build_probe_report.json | build_report | ... |

## Unresolved Review Items

| Kind | Description | Suggested Action |
|---|---|---|
| placeholder_expected_value | TBD expected return remains | Review function specification |
```

---

## 10. テスト計画

### 10.1 fixture 構成

```text
tests/
  fixtures/
    test_execution/
      success_output/
        runner_output.log
        test_case_draft.json
      failure_output/
        runner_output.log
        test_case_draft.json
      placeholder_output/
      timeout_case/
      executable_missing/
      build_not_successful/
      evidence_package/
        build_probe_report.json
        harness_skeleton_report.json
        test_case_draft.json
        test_execution_report.json
```

### 10.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| EXE-001 | executable resolve | bin/utr_probe.exeあり | ExecutableInfo exists |
| EXE-002 | executable missing | なし | blocked + warning |
| EXE-003 | dry run | run_tests=false | status not_run |
| EXE-004 | build not successful | build failed | blocked |
| EXE-005 | successful output parse | runner OK | passed count抽出 |
| EXE-006 | failed output parse | assert failed | failure抽出 |
| EXE-007 | summary missing | summaryなし | medium confidence集計 |
| EXE-008 | timeout | mock timeout | status timeout |
| EXE-009 | placeholder detected | TBDあり | inconclusive |
| EXE-010 | map test case | TC IDあり | draftと対応付け |
| EXE-011 | unmapped output | unknown TC | review item生成 |
| EXE-012 | result json | test_result.json | JSON parse可能 |
| EXE-013 | result csv | test_result.csv | expected columnsあり |
| EXE-014 | execution report md | md | expected sectionあり |
| EXE-015 | evidence manifest | manifest | file hash含む |
| EXE-016 | evidence package md | md | summary含む |
| EXE-017 | run-tests cli dry-run | workspace | report生成 |
| EXE-018 | prepare-evidence cli | existing reports | evidence生成 |
| EXE-019 | analyze-function integration | Step04-16 | evidence生成 |

### 10.3 テスト方針

- 実プロセス実行はmock runnerで検証する
- runner output parserはfixture logで検証する
- executable resolverは一時ディレクトリで検証する
- JSONは `json.loads()` で検証する
- CSVはheader列と行数を検証する
- Markdownは主要sectionの存在を検証する
- 本物のVC6実行ファイルはunit testでは要求しない

---

## 11. 実装タスク分解

### Task 16-01: Test execution model 定義

成果物:

- `src/unit_test_runner/execution/execution_models.py`
- `TestExecutionRequest`
- `TestExecutionPolicy`
- `ExecutableInfo`
- `TestExecutionReport`
- `ExecutionCommand`
- `ExecutionCommandResult`
- `TestResultSummary`
- `TestCaseExecutionResult`
- `AssertionResult`
- `ExecutionReviewItem`
- `EvidenceManifest`
- `EvidenceFile`
- `EvidenceSummary`
- `TestExecutionWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 16-02: Executable resolver

成果物:

- `src/unit_test_runner/execution/executable_resolver.py`
- bin/utr_probe.exe探索
- 明示executable対応
- hash計算
- missing warning

完了条件:

- EXE-001 / EXE-002 が通る

### Task 16-03: Execution runner

成果物:

- `src/unit_test_runner/execution/execution_runner.py`
- dry-run
- timeout
- stdout/stderr/combined log保存
- environment capture

完了条件:

- EXE-003 / EXE-008 が通る

### Task 16-04: Precondition validator

成果物:

- build probe status確認
- placeholder policy確認
- execution blocked判定

完了条件:

- EXE-004 / EXE-009 が通る

### Task 16-05: Runner output parser

成果物:

- `src/unit_test_runner/execution/runner_output_parser.py`
- RUN / OK / FAILED / SKIPPED抽出
- assert failed抽出
- summary抽出
- parser confidence算出

完了条件:

- EXE-005 / EXE-006 / EXE-007 が通る

### Task 16-06: Test result mapper

成果物:

- `src/unit_test_runner/execution/result_mapper.py`
- test_case_draft対応付け
- coverage link反映
- unmapped output review item生成

完了条件:

- EXE-010 / EXE-011 が通る

### Task 16-07: Test result writer

成果物:

- `src/unit_test_runner/execution/test_result_writer.py`
- `test_result.json`
- `test_result.csv`
- `test_execution_report.json`
- `reports/test_execution_markdown.py`

完了条件:

- EXE-012 / EXE-013 / EXE-014 が通る

### Task 16-08: Evidence manifest generator

成果物:

- `src/unit_test_runner/execution/evidence_manifest.py`
- evidence file収集
- hash記録
- summary生成

完了条件:

- EXE-015 が通る

### Task 16-09: Evidence package markdown writer

成果物:

- `reports/evidence_package_markdown.py`
- evidence_package.md
- unresolved review items section

完了条件:

- EXE-016 が通る

### Task 16-10: run-tests CLI 実装

成果物:

- `run-tests` コマンド
- `--workspace`
- `--executable`
- `--run` / `--dry-run`
- `--timeout`
- placeholder policy option

完了条件:

- EXE-017 が通る

### Task 16-11: prepare-evidence CLI 実装

成果物:

- `prepare-evidence` コマンド
- existing reports収集
- evidence再生成

完了条件:

- EXE-018 が通る

### Task 16-12: analyze-function 接続

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
- Step 15 build_completion_plan / completion iteration生成
- Step 16 test_execution / evidence生成
- CLI `analyze-function` の出力更新

完了条件:

- EXE-019 が通る

### Task 16-13: fixture / test 整備

成果物:

- `tests/fixtures/test_execution/...`
- `tests/unit/test_executable_resolver.py`
- `tests/unit/test_execution_runner.py`
- `tests/unit/test_runner_output_parser.py`
- `tests/unit/test_result_mapper.py`
- `tests/unit/test_test_result_writer.py`
- `tests/unit/test_evidence_manifest.py`
- `tests/unit/test_run_tests_cli.py`
- `tests/unit/test_prepare_evidence_cli.py`
- `tests/unit/test_analyze_function_partial_evidence.py`

完了条件:

- EXE-001 から EXE-019 が通る

---

## 12. 受け入れ基準

Step 16 は、以下をすべて満たしたら完了とする。

1. workspaceから実行対象バイナリを解決できる
2. build probe未成功時に実行をblockできる
3. 明示オプション時のみテスト実行できる
4. dry-runで実行コマンドを確認できる
5. timeout付きで実行できる
6. stdout / stderr / combined logを保存できる
7. runner出力からtest case結果を抽出できる
8. assert failureを抽出できる
9. summaryがある場合にtotal / passed / failed / skippedを抽出できる
10. summaryがない場合も可能な範囲で結果を抽出できる
11. test_case_draftと実行結果を対応付けられる
12. placeholderを含むtest caseをreview_requiredまたはinconclusiveにできる
13. unmapped outputをreview itemにできる
14. `test_execution_report.json` を生成できる
15. `test_execution_report.md` を生成できる
16. `test_result.json` を生成できる
17. `test_result.csv` を生成できる
18. `evidence_manifest.json` を生成できる
19. `evidence_package.md` を生成できる
20. `run-tests` が明示入力からdry-runまたは実行できる
21. `prepare-evidence` が既存成果物からevidenceを再生成できる
22. `analyze-function` が Step 16 時点では test execution / evidence preparation まで進める
23. Step 17 の Function Dossier Finalizer / Review Workflow に渡せるevidence manifestがある
24. 本番リポジトリを変更しない
25. 期待結果確定やテスト自動修正へ踏み込みすぎていない
26. 実測カバレッジ計測へ踏み込みすぎていない

---

## 13. 成果物

Step 16 の成果物は以下とする。

```text
src/
  unit_test_runner/
    execution/
      __init__.py
      execution_models.py
      executable_resolver.py
      execution_runner.py
      precondition_validator.py
      runner_output_parser.py
      result_mapper.py
      test_result_writer.py
      evidence_manifest.py
    reports/
      test_execution_markdown.py
      evidence_package_markdown.py
    cli/
      commands.py

tests/
  fixtures/
    test_execution/
      success_output/
      failure_output/
      placeholder_output/
      timeout_case/
      executable_missing/
      build_not_successful/
      evidence_package/
  unit/
    test_executable_resolver.py
    test_execution_runner.py
    test_runner_output_parser.py
    test_result_mapper.py
    test_test_result_writer.py
    test_evidence_manifest.py
    test_run_tests_cli.py
    test_prepare_evidence_cli.py
    test_analyze_function_partial_evidence.py
```

生成先workspace例:

```text
workspace/
  Control_Update/
    logs/
      test_stdout.log
      test_stderr.log
      test_execution.log
    reports/
      test_execution_report.json
      test_execution_report.md
      test_result.json
      test_result.csv
      evidence_manifest.json
      evidence_package.md
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/build/build_models.py` 必要な場合のみ
- `src/unit_test_runner/build_completion/completion_models.py` 必要な場合のみ
- `src/unit_test_runner/test_design/test_case_models.py` 必要な場合のみ

---

## 14. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| 意図しないバイナリ実行 | analyze-functionで勝手に実行されると危険 | 実行は必ず `--run-tests` 等の明示オプションにする |
| placeholderをpass扱いする | TBD期待値で通っても意味がない | placeholder検出時はinconclusive / review_requiredにする |
| runner出力形式変更 | parserが壊れる | raw logを保存し、parser confidenceを持つ |
| timeout | テストが停止しない | timeout必須、timeout時はlog保存してstatus timeout |
| build未成功で実行 | 古いexeや不完全exeを実行する可能性 | require_successful_build_probeを既定trueにする |
| evidence不足 | 後から再現できない | manifestにhashと関連reportを必ず記録する |
| 期待結果確定への踏み込み | 仕様なしに期待値を断定する | Step16ではplaceholderとreview itemに留める |
| 実測coverage要求 | coverage計測までやりたくなる | Step16は実行ログと証跡に限定し、coverage instrumentationは後続で検討する |

---

## 15. Step 17 への接続

Step 16 完了後、Step 17 では Function Dossier Finalizer / Review Workflow を実装する。
Step 17 は、Step 04 から Step 16 までの成果物を1つの `function_dossier` として統合し、レビュー用の最終Markdown、JSON manifest、未解決事項一覧、次アクション一覧を作る。

想定接続:

```python
evidence = prepare_test_execution_evidence(
    workspace=workspace,
    test_case_draft=test_case_draft,
    harness_report=harness_report,
    completion_report=completion_report,
)
function_dossier = finalize_function_dossier(
    source_digest=source_digest,
    function_location=function_location,
    function_signature=function_signature,
    global_access=global_access,
    call_report=call_report,
    coverage_design=coverage_design,
    boundary_candidates=boundary_candidates,
    test_case_draft=test_case_draft,
    evidence_manifest=evidence.manifest,
)
```

Step 17 で使う情報:

- source digest
- function location
- signature
- global access
- call report
- coverage design
- boundary/equivalence candidates
- test case draft
- harness skeleton report
- build reports
- completion reports
- test execution reports
- evidence manifest
- unresolved review items

Step 16 の責務は、Function Dossier Finalizer がレビュー可能な最終成果物を作れるように、実行結果とエビデンスを構造化して渡すことである。

---

## 16. まとめ

Step 16 は、Step 15 までで生成・ビルド可能になった関数単位テストを、明示オプションのもとで実行し、結果とエビデンスを整理するステップである。

このステップにより、対象関数について、どのテストケースが実行され、どのassertが成功または失敗し、どの項目がreview requiredまたはinconclusiveなのかを `test_execution_report` と `evidence_package` として確認できる。

ただし、Step 16 は期待結果を確定したり、失敗テストを自動修正したり、実測カバレッジを計測する段階ではない。
テスト実行と証跡準備に責務を絞り、Step 17 の Function Dossier Finalizer / Review Workflow へ安全な入力を渡すことを完了条件とする。

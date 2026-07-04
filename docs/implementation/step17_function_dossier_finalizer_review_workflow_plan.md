# Step 17: Function Dossier Finalizer / Review Workflow 実装計画

作成日: 2026-07-04  
状態: Draft v0.1  
対象リポジトリ: `katamor1/unitTestRunner`  
製造担当想定: CODEX  
前提文書:

- `docs/adr/0001-cli-layer-language-selection.md`
- `docs/function_level_vc6_unit_test_codex_design.md`
- `docs/review/current_assessment_and_future_outlook.md`
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
- `docs/implementation/step16_test_execution_evidence_preparation_plan.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第17ステップとして **Function Dossier Finalizer / Review Workflow** を実装するための計画である。

Step 16 では、関数単位テスト用に生成・ビルドした成果物を明示オプションのもとで実行し、test log、result csv、execution report、evidence package を生成する計画を定義した。

Step 17 では、Step 04 から Step 16 までに生成された解析結果、設計候補、生成コード、ビルド結果、補完履歴、実行結果、エビデンスを統合し、レビュー可能な最終成果物である **function dossier** を生成する。

ここでの function dossier は、単なるJSON集約ではない。
対象関数に対して、以下を人間がレビューできる形でまとめる成果物である。

- どのVC6プロジェクト・構成に属するか
- どのdefine / include / PCH条件で解析されたか
- 関数の位置、シグネチャ、引数、戻り値は何か
- どのグローバル状態を参照・更新するか
- どの外部関数を呼ぶか
- どの分岐・条件・return経路をテスト観点としたか
- どの境界値・同値クラス候補を出したか
- どのテストケース草案を生成したか
- どのスタブ・ハーネスを生成したか
- ビルドはどこまで進んだか
- 実行結果はどうだったか
- どの項目が未解決で、誰が何をレビューすべきか

Step 17 の主な責務は以下である。

- Step 04 から Step 16 までの成果物を読み込む
- 成果物の存在・schema version・hashを検証する
- `function_dossier.json` を生成する
- `function_dossier.md` を生成する
- `traceability_matrix.csv` を生成する
- `review_checklist.md` を生成する
- `unresolved_items.md` を生成する
- `next_actions.md` を生成する
- review status / readiness を判定する
- dossier全体の品質サマリを出す
- Step 18 の VS Code Thin Adapter や、将来のモジュール単位集約へ渡せる形式にする

---

## 2. 目的

Step 17 の目的は、関数単位テスト支援パイプラインの成果を、レビュー・共有・再実行・次アクション判断に使える **最終dossier** としてまとめることである。

具体的には、以下を実現する。

- 対象関数に関する解析結果を1つのdossierに集約できる
- 各成果物の有無、生成日時、hash、schema versionを記録できる
- 解析結果、テスト設計、生成物、ビルド結果、実行結果を相互に紐付けられる
- coverage item と test case と input candidate と stub setup と実行結果を追跡できる
- unresolved / review_required / inconclusive / manual action を一覧化できる
- 期待結果未確定、file static setup困難、stub動作未確定などをレビュー項目として整理できる
- dossierの状態を `ready_for_review` / `blocked` / `ready_for_harness` / `ready_for_execution` / `evidence_ready` などで判定できる
- Markdownで人間がレビューしやすい最終レポートを生成できる
- CSVでトレーサビリティ表を出力できる
- JSONで後続ツールやVS Code adapterが扱える形式を提供できる
- 本番リポジトリを変更せず、外部ワークスペース内の成果物を整理できる

---

## 3. スコープ

### 3.1 実装対象

Step 17 で実装するもの:

1. Dossier model
   - function dossier request
   - function dossier report
   - artifact reference
   - section summary
   - traceability link
   - review item
   - readiness assessment
   - next action
   - warning

2. Artifact collector
   - reports配下のJSON/Markdown/CSVを収集
   - generated filesの一覧収集
   - logs一覧収集
   - hash計算
   - missing artifact検出
   - schema version検出

3. Dossier validator
   - 必須成果物の存在確認
   - JSON parse確認
   - schema_version確認
   - function name一致確認
   - source path一致確認
   - stale artifact候補検出
   - cross reference不整合検出

4. Summary builder
   - project/build context summary
   - source/function summary
   - signature summary
   - global access summary
   - call/stub summary
   - coverage summary
   - boundary/equivalence summary
   - test case draft summary
   - harness/build/execution/evidence summary

5. Traceability matrix generator
   - coverage item -> candidate -> test case -> stub setup -> execution result
   - call -> stub candidate -> generated stub -> test cases
   - global access -> state setup -> expected observation
   - unresolved item -> suggested action

6. Review workflow generator
   - review checklist
   - unresolved item list
   - manual action list
   - expected result review items
   - stub behavior review items
   - build/manual action review items
   - evidence review items

7. Readiness assessor
   - ready_for_review判定
   - ready_for_harness判定
   - ready_for_build_probe判定
   - ready_for_execution判定
   - evidence_ready判定
   - blocked理由整理

8. Reports
   - `function_dossier.json`
   - `function_dossier.md`
   - `traceability_matrix.csv`
   - `review_checklist.md`
   - `unresolved_items.md`
   - `next_actions.md`
   - `dossier_manifest.json`

9. CLI 接続
   - `finalize-dossier` コマンド案
   - `prepare-review` コマンド案
   - `analyze-function --finalize-dossier` 明示オプション
   - status `dossier_finalized` / `ready_for_review` / `blocked` を返す

10. Tests
   - complete artifacts
   - missing artifact
   - stale artifact
   - function name mismatch
   - traceability matrix generation
   - review checklist generation
   - unresolved item aggregation
   - readiness assessment
   - Markdown / CSV / JSON output

### 3.2 対象外

Step 17 では以下を対象外とする。

- 実行可能Cテストコードの新規生成
- スタブ雛形の新規生成
- ビルド実行
- テスト実行
- ビルドエラー補完
- 期待結果の自動確定
- review itemの自動承認
- AIによる無審査の仕様判断
- PDF / Excel の正式帳票生成
- GitHub Issue / Pull Request の自動作成
- VS Code UI実装
- モジュール単位dossier集約
- リアルタイム性・疑似時間・疑似割込対応

Step 17 では、既存成果物の統合、レビュー準備、次アクション整理に責務を絞る。

---

## 4. 入力と出力

### 4.1 入力

主入力:

- Step 04 の `build_context`
- Step 05 の `source_digest`
- Step 06 の `function_location`
- Step 07 の `function_signature`
- Step 08 の `global_access`
- Step 09 の `call_report`
- Step 10 の `coverage_design`
- Step 11 の `boundary_equivalence_candidates`
- Step 12 の `test_case_draft`
- Step 13 の `harness_skeleton_report`
- Step 14 の `build_workspace_report`
- Step 14 の `build_probe_report`
- Step 15 の `build_completion_plan`
- Step 15 の `build_completion_iteration_report`
- Step 16 の `test_execution_report`
- Step 16 の `test_result.csv`
- Step 16 の `evidence_manifest`
- workspace path

入力イメージ:

```json
{
  "function": "Control_Update",
  "workspace": "D:/work/unit_test_workspace/Control_Update",
  "reports": {
    "source_digest": "reports/source_digest.json",
    "function_location": "reports/function_location.json",
    "function_signature": "reports/function_signature.json",
    "global_access": "reports/global_access.json",
    "call_report": "reports/call_report.json",
    "coverage_design": "reports/coverage_design.json",
    "boundary_equivalence_candidates": "reports/boundary_equivalence_candidates.json",
    "test_case_draft": "reports/test_case_draft.json",
    "harness_skeleton_report": "reports/harness_skeleton_report.json",
    "build_workspace_report": "reports/build_workspace_report.json",
    "build_probe_report": "reports/build_probe_report.json",
    "build_completion_plan": "reports/build_completion_plan.json",
    "build_completion_iteration_report": "reports/build_completion_iteration_report.json",
    "test_execution_report": "reports/test_execution_report.json",
    "evidence_manifest": "reports/evidence_manifest.json"
  }
}
```

### 4.2 出力

Step 17 の主要出力は final dossier と review workflow artifacts である。

```text
workspace/
  Control_Update/
    reports/
      function_dossier.json
      function_dossier.md
      dossier_manifest.json
      traceability_matrix.csv
      review_checklist.md
      unresolved_items.md
      next_actions.md
```

---

## 5. 基本方針

### 5.1 Dossierは最終判定ではなくレビュー入口

Step 17で生成するdossierは、仕様上の正解を断定するものではない。

方針:

- `review_required` を隠さない
- `TBD` placeholder を残す
- `inconclusive` を合格扱いしない
- warning / confidence / unresolved item を明示する
- 人間が確認すべき観点をチェックリスト化する

### 5.2 トレーサビリティを重視する

テストケースやエビデンスだけでなく、以下のつながりを追えるようにする。

```text
condition / branch
  -> coverage item
  -> boundary / equivalence candidate
  -> test case draft
  -> stub setup / state setup
  -> generated test skeleton
  -> build result
  -> execution result
  -> evidence file
```

これにより、レビュー時に「このテストは何を狙っているのか」「どの条件から来たのか」「実行結果はどこにあるのか」を追跡できる。

### 5.3 欠損成果物を許容する

全Stepが常に完了しているとは限らない。

方針:

- MVP-1段階では Step 04〜07 の成果物だけでdossier生成できる
- MVP-2段階では Step 08〜12 の設計成果物を含める
- MVP-3段階では Step 13〜15 のビルド成果物を含める
- MVP-4段階では Step 16 の実行・エビデンス成果物を含める
- 欠損成果物は error ではなく readiness 判定に反映する

### 5.4 本番リポジトリ非侵襲を維持する

Step 17でも、本番リポジトリへ成果物を自動追加しない。

function dossier は外部ワークスペースまたは `unitTestRunner` 側の検証成果物として扱う。
本番リポジトリに入れるかどうかは、別途レビュー・規約判断が必要である。

---

## 6. データモデル設計

### 6.1 FunctionDossierRequest

```python
@dataclass
class FunctionDossierRequest:
    workspace_root: Path
    function_name: str
    report_paths: dict[str, Path]
    generation_policy: DossierGenerationPolicy
```

### 6.2 DossierGenerationPolicy

```python
@dataclass
class DossierGenerationPolicy:
    include_raw_artifact_index: bool
    include_traceability_matrix: bool
    include_review_checklist: bool
    include_next_actions: bool
    require_schema_version_match: bool
    allow_missing_optional_artifacts: bool
    markdown_detail_level: str
```

既定方針:

- `include_raw_artifact_index = true`
- `include_traceability_matrix = true`
- `include_review_checklist = true`
- `include_next_actions = true`
- `require_schema_version_match = false`
- `allow_missing_optional_artifacts = true`
- `markdown_detail_level = "summary_with_links"`

### 6.3 FunctionDossier

```python
@dataclass
class FunctionDossier:
    function_name: str
    source_path: Path | None
    workspace_root: Path
    status: str
    created_at: str
    artifact_index: list[DossierArtifact]
    summaries: DossierSummaries
    traceability: list[TraceabilityLink]
    review_items: list[DossierReviewItem]
    unresolved_items: list[DossierUnresolvedItem]
    next_actions: list[DossierNextAction]
    readiness: DossierReadiness
    warnings: list[DossierWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `finalized` | dossier生成が完了した |
| `partial` | 一部成果物が欠けているが生成した |
| `blocked` | 必須成果物不足で生成不能 |
| `ready_for_review` | レビュー可能 |
| `evidence_ready` | エビデンス付きでレビュー可能 |

### 6.4 DossierArtifact

```python
@dataclass
class DossierArtifact:
    artifact_id: str
    artifact_kind: str
    path: Path
    exists: bool
    sha256: str | None
    schema_version: str | None
    produced_by_step: str
    required_level: str
    stale_candidate: bool
    warnings: list[DossierWarning]
```

`artifact_kind` 候補:

- `build_context`
- `source_digest`
- `function_location`
- `function_signature`
- `global_access`
- `call_report`
- `coverage_design`
- `boundary_equivalence_candidates`
- `test_case_draft`
- `harness_skeleton_report`
- `build_workspace_report`
- `build_probe_report`
- `build_completion_plan`
- `build_completion_iteration_report`
- `test_execution_report`
- `test_result_csv`
- `evidence_manifest`
- `generated_source`
- `log`
- `markdown_report`

`required_level` 候補:

- `mvp1_required`
- `mvp2_required`
- `mvp3_required`
- `mvp4_required`
- `optional`

### 6.5 DossierSummaries

```python
@dataclass
class DossierSummaries:
    project_summary: ProjectSummary | None
    source_summary: SourceSummary | None
    function_summary: FunctionSummary | None
    dependency_summary: DependencySummary | None
    coverage_summary: DossierCoverageSummary | None
    test_design_summary: TestDesignSummary | None
    build_summary: DossierBuildSummary | None
    execution_summary: DossierExecutionSummary | None
```

### 6.6 TraceabilityLink

```python
@dataclass
class TraceabilityLink:
    link_id: str
    source_kind: str
    source_id: str
    target_kind: str
    target_id: str
    relation: str
    confidence: str
    review_required: bool
```

`relation` 候補:

| relation | 意味 |
|---|---|
| `covers` | test caseがcoverage itemを狙う |
| `derived_from` | 候補が条件式から派生 |
| `uses_stub` | test caseがstubを使う |
| `sets_state` | test caseが状態を設定する |
| `observes` | test caseが観測対象を持つ |
| `produced_file` | generatorがfileを生成した |
| `executed_as` | test caseが実行結果に対応する |
| `blocked_by` | 項目が未解決事項でblockされる |

### 6.7 DossierReviewItem

```python
@dataclass
class DossierReviewItem:
    review_id: str
    category: str
    title: str
    description: str
    related_artifacts: list[str]
    related_test_cases: list[str]
    severity: str
    suggested_reviewer_role: str
    done: bool
```

`category` 候補:

- `signature_review`
- `global_access_review`
- `stub_behavior_review`
- `coverage_review`
- `boundary_value_review`
- `expected_result_review`
- `build_review`
- `execution_review`
- `evidence_review`
- `manual_action_review`

### 6.8 DossierUnresolvedItem

```python
@dataclass
class DossierUnresolvedItem:
    item_id: str
    source_step: str
    item_kind: str
    description: str
    impact: str
    related_artifacts: list[str]
    related_test_cases: list[str]
    suggested_action: str
    blocks_readiness: bool
```

### 6.9 DossierNextAction

```python
@dataclass
class DossierNextAction:
    action_id: str
    priority: str
    action_kind: str
    title: str
    description: str
    owner_role: str
    related_unresolved_items: list[str]
    expected_output: str
```

`action_kind` 候補:

- `review_expected_result`
- `review_stub_behavior`
- `fix_generated_code`
- `add_include_path`
- `resolve_pch_issue`
- `manual_stub_edit`
- `rerun_build_probe`
- `rerun_tests`
- `approve_dossier`
- `defer_to_module_test`

### 6.10 DossierReadiness

```python
@dataclass
class DossierReadiness:
    mvp_level: str
    ready_for_review: bool
    ready_for_harness_generation: bool
    ready_for_build_probe: bool
    ready_for_execution: bool
    evidence_ready: bool
    blocked: bool
    blocked_reasons: list[str]
    quality_score: int | None
```

`mvp_level` 候補:

- `mvp1_analysis_only`
- `mvp2_test_design`
- `mvp3_build_probe`
- `mvp4_execution_evidence`
- `unknown`

### 6.11 DossierWarning

```python
@dataclass
class DossierWarning:
    code: str
    message: str
    related_artifact_id: str | None = None
    related_step: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `missing_artifact` | 成果物が見つからない |
| `artifact_parse_failed` | JSON parseに失敗した |
| `schema_version_unknown` | schema version不明 |
| `function_name_mismatch` | 成果物間でfunction nameが不一致 |
| `source_path_mismatch` | 成果物間でsource pathが不一致 |
| `stale_artifact_candidate` | 古い成果物の可能性 |
| `traceability_gap` | traceabilityが欠けている |
| `review_required_items_exist` | review required項目が残っている |
| `inconclusive_execution` | 実行結果がinconclusive |
| `manual_action_required` | 手動対応が必要 |

---

## 7. 生成設計

### 7.1 基本アルゴリズム

処理フロー:

```text
finalize_function_dossier(request)
  1. workspace / reports配下を走査する
  2. 既知artifactを収集する
  3. JSON成果物をparseする
  4. artifact indexを作る
  5. function name / source path / schema versionの整合性を検証する
  6. 各Stepのsummaryを作る
  7. coverage / candidate / test case / stub / execution のtraceabilityを作る
  8. unresolved / review_required / warningsを集約する
  9. readinessを判定する
 10. next actionsを生成する
 11. function_dossier.json / md を出力する
 12. traceability_matrix.csv / review_checklist.md / unresolved_items.md / next_actions.md を出力する
```

### 7.2 artifact収集

既知の標準path:

```text
reports/source_digest.json
reports/function_location.json
reports/function_signature.json
reports/global_access.json
reports/call_report.json
reports/coverage_design.json
reports/boundary_equivalence_candidates.json
reports/test_case_draft.json
reports/harness_skeleton_report.json
reports/build_workspace_report.json
reports/build_probe_report.json
reports/build_completion_plan.json
reports/build_completion_iteration_report.json
reports/test_execution_report.json
reports/evidence_manifest.json
```

方針:

- 標準pathにない場合でも `--report` 明示指定で読み込めるようにする
- 欠損はwarningにする
- MVPレベルに応じて必須/任意を判定する
- hashを計算してmanifestに残す

### 7.3 Summary生成

summaryは、詳細JSONを全部貼るのではなく、レビューに必要な情報へ圧縮する。

例:

- project summary
  - DSW / DSP
  - configuration
  - defines count
  - include dirs count
  - PCH情報

- function summary
  - source path
  - function line range
  - signature
  - parameters
  - return type

- dependency summary
  - globals read/write count
  - external calls count
  - stub candidates count

- coverage summary
  - branch items count
  - condition items count
  - switch / loop / return path count

- test design summary
  - test case draft count
  - review required count
  - unresolved expected count

- build summary
  - build workspace status
  - build probe status
  - missing include count
  - unresolved symbol count

- execution summary
  - executed / not run
  - total / passed / failed / inconclusive
  - evidence ready

### 7.4 Traceability matrix生成

CSV列案:

```text
source_kind,source_id,relation,target_kind,target_id,test_case_id,coverage_id,candidate_id,stub_name,execution_status,review_required,confidence
```

代表link:

- `condition` -> `coverage_item`
- `coverage_item` -> `boundary_candidate`
- `boundary_candidate` -> `test_case`
- `test_case` -> `stub_setup`
- `stub_candidate` -> `generated_stub`
- `test_case` -> `execution_result`
- `unresolved_item` -> `next_action`

### 7.5 Review checklist生成

レビュー項目例:

```markdown
# Review Checklist

## Function Interface

- [ ] Function signature is correctly detected.
- [ ] Parameter directions are reasonable.
- [ ] Pointer / array parameters are reviewed.

## State and Dependencies

- [ ] Global read/write candidates are reviewed.
- [ ] Stub candidates are reviewed.
- [ ] Hardware-like / I/O-like functions are classified correctly.

## Test Design

- [ ] Coverage items are reasonable.
- [ ] Boundary candidates are reasonable.
- [ ] Test case draft purposes are clear.
- [ ] Expected results are filled or marked as unresolved.

## Build / Execution

- [ ] Build probe status is reviewed.
- [ ] Unresolved symbols are reviewed.
- [ ] Execution result is reviewed.
- [ ] Inconclusive tests are resolved or accepted as pending.
```

### 7.6 Readiness判定

判定ルール例:

| 条件 | readiness |
|---|---|
| Step 04〜07あり | `mvp1_analysis_only` |
| Step 08〜12あり | `mvp2_test_design` |
| Step 13〜15あり | `mvp3_build_probe` |
| Step 16 evidenceあり | `mvp4_execution_evidence` |
| 必須artifact欠損 | `blocked` |
| review_requiredあり | `ready_for_review=true`, `evidence_ready=false`の場合あり |
| build failedかつmanual actionあり | `blocked=true` |
| test inconclusiveあり | `ready_for_review=true`, `evidence_ready=false`またはpartial |

quality_scoreは初期では必須にしない。
将来的に以下のような簡易スコアを検討する。

```text
100
- missing required artifact penalty
- unresolved item penalty
- low confidence penalty
- build failure penalty
- inconclusive execution penalty
```

### 7.7 Next actions生成

代表例:

| 状況 | next action |
|---|---|
| expected result unknown | 仕様書を確認し期待値を確定する |
| stub behavior unknown | 外部依存関数の戻り値・副作用仕様を確認する |
| file static setup困難 | wrapperまたは初期化経路を検討する |
| unresolved symbolあり | Step 15 completion planを確認しstub追加する |
| PCH issueあり | PCH設定またはstdafx.h抽出方針を決める |
| test inconclusive | placeholder解消後に再実行する |
| evidence ready | レビュー承認または次関数へ展開する |

---

## 8. CLI 接続設計

### 8.1 finalize-dossier コマンド案

```bat
unit-test-runner finalize-dossier ^
  --workspace D:\work\unit_test_workspace\Control_Update ^
  --out D:\work\unit_test_workspace\Control_Update\reports
```

オプション案:

```text
--workspace PATH
--function NAME
--out PATH
--mvp-level mvp1|mvp2|mvp3|mvp4|auto
--allow-missing-optional-artifacts
--strict-schema-version
--json
```

### 8.2 prepare-review コマンド案

レビュー用成果物だけを再生成する。

```bat
unit-test-runner prepare-review ^
  --dossier reports\function_dossier.json ^
  --out reports
```

生成物:

- `review_checklist.md`
- `unresolved_items.md`
- `next_actions.md`
- `traceability_matrix.csv`

### 8.3 analyze-function の Step 17 接続

Step 17 では、`analyze-function` からdossier finalizationまで進められるようにする。
ただし、ビルドやテスト実行は引き続き明示オプションでのみ行う。

```bat
unit-test-runner analyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Control - Win32 Debug" ^
  --out D:\work\unit_test_workspace\Control_Update ^
  --finalize-dossier
```

処理:

1. 指定された範囲のStep成果物を生成または読み込む
2. Step 17 の Function Dossier Finalizer を実行する
3. `function_dossier.json` を生成する
4. `function_dossier.md` を生成する
5. `traceability_matrix.csv` を生成する
6. `review_checklist.md` を生成する
7. `unresolved_items.md` を生成する
8. `next_actions.md` を生成する
9. Step 18 の VS Code Thin Adapter で表示可能なreport構造を返す

---

## 9. Report 設計

### 9.1 function_dossier.json

例:

```json
{
  "schema_version": "0.1",
  "function": {
    "name": "Control_Update",
    "source_path": "D:/work/product/src/control.c",
    "status": "ready_for_review"
  },
  "readiness": {
    "mvp_level": "mvp4_execution_evidence",
    "ready_for_review": true,
    "ready_for_harness_generation": true,
    "ready_for_build_probe": true,
    "ready_for_execution": true,
    "evidence_ready": false,
    "blocked": false,
    "blocked_reasons": []
  },
  "summaries": {
    "function_summary": {
      "signature": "int Control_Update(int mode, int sensor)",
      "line_range": "120-180",
      "parameter_count": 2
    },
    "dependency_summary": {
      "global_read_count": 1,
      "global_write_count": 1,
      "external_call_count": 2,
      "stub_candidate_count": 2
    },
    "coverage_summary": {
      "coverage_item_count": 10,
      "test_case_draft_count": 8
    },
    "execution_summary": {
      "executed": true,
      "passed": 6,
      "failed": 1,
      "inconclusive": 1
    }
  },
  "artifact_index": [
    {
      "artifact_kind": "function_signature",
      "path": "reports/function_signature.json",
      "exists": true,
      "sha256": "...",
      "produced_by_step": "Step 07"
    }
  ],
  "unresolved_items": [
    {
      "item_kind": "expected_result_unknown",
      "description": "TBD expected return remains in TC_Control_Update_001",
      "suggested_action": "Review function specification and replace TBD_EXPECTED_RETURN_INT."
    }
  ],
  "warnings": []
}
```

### 9.2 function_dossier.md

構成案:

```markdown
# Function Dossier: Control_Update

## 1. Summary

- Source: D:/work/product/src/control.c
- Project: Control.dsp / Win32 Debug
- Status: ready_for_review
- MVP Level: mvp4_execution_evidence

## 2. Function Interface

```c
int Control_Update(int mode, int sensor)
```

## 3. Dependencies

### Global Access

| Name | Scope | Access | Evidence |
|---|---|---|---|

### Calls / Stub Candidates

| Function | Target Kind | Stub Required | Reason |
|---|---|---|---|

## 4. Coverage Design

| Coverage ID | Type | Purpose | Related Variables | Related Calls |
|---|---|---|---|---|

## 5. Boundary / Equivalence Candidates

| Candidate | Target | Value | Coverage | Review |
|---|---|---|---|---|

## 6. Test Case Drafts

| Test Case | Purpose | Coverage | Review Status |
|---|---|---|---|

## 7. Build / Execution

| Item | Status |
|---|---|
| Build Probe | succeeded |
| Test Execution | inconclusive |

## 8. Traceability

See `traceability_matrix.csv`.

## 9. Unresolved Items

| Item | Impact | Suggested Action |
|---|---|---|

## 10. Next Actions

| Priority | Action | Owner Role |
|---|---|---|
```

### 9.3 traceability_matrix.csv

列案:

```csv
source_kind,source_id,relation,target_kind,target_id,test_case_id,coverage_id,candidate_id,stub_name,execution_status,review_required,confidence
condition,COND_001,derived_from,coverage_item,BR_Control_Update_001_TRUE,TC_Control_Update_001,BR_Control_Update_001_TRUE,IN_sensor_002,CheckLimit,inconclusive,true,high
```

### 9.4 review_checklist.md

レビューカテゴリ:

- Function Interface
- Build Context
- State / Global Access
- External Calls / Stubs
- Coverage Design
- Boundary / Equivalence
- Test Case Draft
- Harness / Build
- Execution / Evidence
- Final Decision

### 9.5 unresolved_items.md

分類:

- expected result unknown
- stub behavior unknown
- setup method unknown
- build issue remaining
- execution inconclusive
- evidence missing
- manual review required

### 9.6 next_actions.md

優先度別に出す。

```markdown
# Next Actions

## High

1. Replace TBD_EXPECTED_RETURN_INT in TC_Control_Update_001.
2. Review CheckLimit stub return behavior.

## Medium

1. Decide setup strategy for file static g_state.

## Low

1. Consider adding VS Code command for opening this dossier.
```

---

## 10. テスト計画

### 10.1 fixture 構成

```text
tests/
  fixtures/
    dossier/
      mvp1_analysis_only/
        source_digest.json
        function_location.json
        function_signature.json
      mvp2_test_design/
        global_access.json
        call_report.json
        coverage_design.json
        boundary_equivalence_candidates.json
        test_case_draft.json
      mvp3_build_probe/
        harness_skeleton_report.json
        build_workspace_report.json
        build_probe_report.json
        build_completion_plan.json
      mvp4_execution_evidence/
        test_execution_report.json
        evidence_manifest.json
      missing_artifact/
      mismatched_function_name/
      stale_artifact/
      unresolved_items/
```

### 10.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| DOS-001 | mvp1 dossier | Step04-07成果物 | mvp1_analysis_only |
| DOS-002 | mvp2 dossier | Step04-12成果物 | test design summaryあり |
| DOS-003 | mvp3 dossier | Step04-15成果物 | build summaryあり |
| DOS-004 | mvp4 dossier | Step04-16成果物 | execution/evidence summaryあり |
| DOS-005 | missing optional | 一部欠損 | partial + warning |
| DOS-006 | missing required | mvp1必須欠損 | blocked |
| DOS-007 | function mismatch | function名不一致 | warning function_name_mismatch |
| DOS-008 | source mismatch | source不一致 | warning source_path_mismatch |
| DOS-009 | artifact hash | fileあり | sha256記録 |
| DOS-010 | traceability | coverage/test/stub/resultあり | matrix生成 |
| DOS-011 | unresolved aggregation | TBD等あり | unresolved_items生成 |
| DOS-012 | review checklist | review_requiredあり | checklist生成 |
| DOS-013 | next actions | unresolvedあり | next_actions生成 |
| DOS-014 | readiness mvp1 | Step04-07 | ready_for_review true |
| DOS-015 | readiness blocked | 必須欠損 | blocked true |
| DOS-016 | json output | function_dossier.json | JSON parse可能 |
| DOS-017 | markdown output | function_dossier.md | expected sectionあり |
| DOS-018 | csv output | traceability_matrix.csv | expected columnsあり |
| DOS-019 | finalize-dossier cli | workspace | dossier生成 |
| DOS-020 | prepare-review cli | dossier | review files生成 |
| DOS-021 | analyze-function integration | Step04-17 | dossier生成 |

### 10.3 テスト方針

- artifact collectorは一時ディレクトリで検証する
- JSON parse失敗や欠損は例外ではなくwarning/reportで検証する
- traceabilityは最小fixtureでlink数と主要列を検証する
- Markdownは主要sectionの存在を検証する
- CSVはheader列と行数を検証する
- Step 04〜16の全実装を必要としないよう、fixture JSONでテストする

---

## 11. 実装タスク分解

### Task 17-01: Dossier model 定義

成果物:

- `src/unit_test_runner/dossier/dossier_models.py`
- `FunctionDossierRequest`
- `DossierGenerationPolicy`
- `FunctionDossier`
- `DossierArtifact`
- `DossierSummaries`
- `TraceabilityLink`
- `DossierReviewItem`
- `DossierUnresolvedItem`
- `DossierNextAction`
- `DossierReadiness`
- `DossierWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 17-02: Artifact collector

成果物:

- `src/unit_test_runner/dossier/artifact_collector.py`
- 標準report path収集
- hash計算
- schema_version抽出
- missing artifact warning

完了条件:

- DOS-005 / DOS-009 が通る

### Task 17-03: Dossier validator

成果物:

- `src/unit_test_runner/dossier/dossier_validator.py`
- function name / source path整合性確認
- schema version確認
- stale candidate判定

完了条件:

- DOS-006 / DOS-007 / DOS-008 が通る

### Task 17-04: Summary builder

成果物:

- `src/unit_test_runner/dossier/summary_builder.py`
- project / source / function / dependency / coverage / test / build / execution summary

完了条件:

- DOS-001 から DOS-004 が通る

### Task 17-05: Traceability matrix generator

成果物:

- `src/unit_test_runner/dossier/traceability.py`
- TraceabilityLink生成
- `traceability_matrix.csv` データ生成

完了条件:

- DOS-010 / DOS-018 が通る

### Task 17-06: Review item aggregator

成果物:

- `src/unit_test_runner/dossier/review_workflow.py`
- review checklist item生成
- unresolved aggregation
- manual action aggregation

完了条件:

- DOS-011 / DOS-012 が通る

### Task 17-07: Readiness assessor

成果物:

- `src/unit_test_runner/dossier/readiness.py`
- MVP level判定
- blocked判定
- ready_for_review / evidence_ready判定

完了条件:

- DOS-014 / DOS-015 が通る

### Task 17-08: Next action generator

成果物:

- `src/unit_test_runner/dossier/next_actions.py`
- unresolved itemからnext action生成
- priority付与

完了条件:

- DOS-013 が通る

### Task 17-09: Dossier writer

成果物:

- `src/unit_test_runner/dossier/dossier_writer.py`
- `function_dossier.json`
- `function_dossier.md`
- `dossier_manifest.json`
- `review_checklist.md`
- `unresolved_items.md`
- `next_actions.md`
- `traceability_matrix.csv`

完了条件:

- DOS-016 / DOS-017 / DOS-018 が通る

### Task 17-10: finalize-dossier CLI 実装

成果物:

- `finalize-dossier` コマンド
- `--workspace`
- `--function`
- `--mvp-level`
- `--strict-schema-version`
- JSON出力対応

完了条件:

- DOS-019 が通る

### Task 17-11: prepare-review CLI 実装

成果物:

- `prepare-review` コマンド
- review files再生成
- dossier input対応

完了条件:

- DOS-020 が通る

### Task 17-12: analyze-function 接続

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
- Step 16 evidence生成
- Step 17 function_dossier生成
- CLI `analyze-function` の出力更新

完了条件:

- DOS-021 が通る

### Task 17-13: fixture / test 整備

成果物:

- `tests/fixtures/dossier/...`
- `tests/unit/test_artifact_collector.py`
- `tests/unit/test_dossier_validator.py`
- `tests/unit/test_summary_builder.py`
- `tests/unit/test_traceability.py`
- `tests/unit/test_review_workflow.py`
- `tests/unit/test_readiness.py`
- `tests/unit/test_dossier_writer.py`
- `tests/unit/test_finalize_dossier_cli.py`
- `tests/unit/test_prepare_review_cli.py`
- `tests/unit/test_analyze_function_partial_dossier.py`

完了条件:

- DOS-001 から DOS-021 が通る

---

## 12. 受け入れ基準

Step 17 は、以下をすべて満たしたら完了とする。

1. workspace内の既知成果物を収集できる
2. 成果物の存在、hash、schema_versionを記録できる
3. function name / source path の不整合をwarningにできる
4. MVP-1成果物だけでもpartial dossierを生成できる
5. MVP-2成果物を含むtest design summaryを生成できる
6. MVP-3成果物を含むbuild summaryを生成できる
7. MVP-4成果物を含むexecution/evidence summaryを生成できる
8. coverage item -> candidate -> test case -> execution result のtraceabilityを生成できる
9. call -> stub candidate -> generated stub のtraceabilityを生成できる
10. unresolved / review_required / inconclusive を集約できる
11. review checklistを生成できる
12. next actionsを生成できる
13. readinessを判定できる
14. blocked理由を明示できる
15. `function_dossier.json` を生成できる
16. `function_dossier.md` を生成できる
17. `traceability_matrix.csv` を生成できる
18. `review_checklist.md` を生成できる
19. `unresolved_items.md` を生成できる
20. `next_actions.md` を生成できる
21. `finalize-dossier` がworkspaceからdossierを生成できる
22. `prepare-review` がdossierからレビュー用ファイルを再生成できる
23. `analyze-function` が Step 17 時点では function dossier finalization まで進める
24. Step 18 の VS Code Thin Adapter で表示しやすいreport構造になっている
25. 期待結果確定やreview承認を自動で行わない
26. 本番リポジトリを変更しない

---

## 13. 成果物

Step 17 の成果物は以下とする。

```text
src/
  unit_test_runner/
    dossier/
      __init__.py
      dossier_models.py
      artifact_collector.py
      dossier_validator.py
      summary_builder.py
      traceability.py
      review_workflow.py
      readiness.py
      next_actions.py
      dossier_writer.py
    reports/
      function_dossier_markdown.py
      review_checklist_markdown.py
      unresolved_items_markdown.py
      next_actions_markdown.py
      traceability_csv.py
    cli/
      commands.py

tests/
  fixtures/
    dossier/
      mvp1_analysis_only/
      mvp2_test_design/
      mvp3_build_probe/
      mvp4_execution_evidence/
      missing_artifact/
      mismatched_function_name/
      stale_artifact/
      unresolved_items/
  unit/
    test_artifact_collector.py
    test_dossier_validator.py
    test_summary_builder.py
    test_traceability.py
    test_review_workflow.py
    test_readiness.py
    test_dossier_writer.py
    test_finalize_dossier_cli.py
    test_prepare_review_cli.py
    test_analyze_function_partial_dossier.py
```

生成先workspace例:

```text
workspace/
  Control_Update/
    reports/
      function_dossier.json
      function_dossier.md
      dossier_manifest.json
      traceability_matrix.csv
      review_checklist.md
      unresolved_items.md
      next_actions.md
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/dossier/schema.py` 必要な場合のみ
- `src/unit_test_runner/test_design/test_case_models.py` 必要な場合のみ
- `src/unit_test_runner/execution/execution_models.py` 必要な場合のみ

---

## 14. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| 成果物が多すぎる | JSONやreportが増えてdossierが肥大化する | Markdownはsummary中心、詳細はartifact linkへ逃がす |
| 欠損成果物で失敗する | MVP段階では全Step成果物が存在しない | MVP levelごとに必須成果物を変える |
| traceabilityが不完全 | 解析結果間のIDが揃わない | traceability_gap warningを出し、ID規約を後続で補正する |
| 古い成果物混在 | 前回実行のreportが残る | hashと生成時刻、source path/function name一致を検証する |
| review項目が多すぎる | unresolvedが大量に出て読みにくい | severityとpriorityで整理する |
| dossierが承認済みと誤解される | 生成されたdossierはレビュー入口であり承認ではない | statusとreview checklistで明示する |
| Step18責務の侵食 | VS Code UIまで作りたくなる | Step17はreport生成まで。表示UIはStep18へ委譲する |

---

## 15. Step 18 への接続

Step 17 完了後、Step 18 では VS Code Thin Adapter を実装する。
Step 18 は、Step 17 の `function_dossier.json` / `function_dossier.md` をVS Codeから開き、現在関数の解析開始、成果物閲覧、未解決事項確認を行いやすくする。

想定接続:

```python
function_dossier = finalize_function_dossier(
    workspace_root=workspace,
    function_name="Control_Update",
)
```

VS Code adapter側では以下を行う。

- `unit-test-runner analyze-function` を呼び出す
- `function_dossier.md` を開く
- `review_checklist.md` を開く
- `next_actions.md` を開く
- 解析対象関数の選択UIを提供する

Step 17 の責務は、VS Code adapterが表示しやすい最終成果物を安定して生成することである。

---

## 16. まとめ

Step 17 は、関数単位テスト支援パイプラインの成果を、レビュー可能な最終成果物へまとめるステップである。

このステップにより、対象関数について、プロジェクト所属、build context、関数情報、副作用、呼び出し、分岐、境界値、テストケース草案、スタブ・ハーネス、ビルド、実行、エビデンス、未解決事項、次アクションを1つの `function_dossier` として確認できる。

ただし、Step 17 は期待結果を確定したり、レビュー承認を自動化したり、VS Code UIを実装したりする段階ではない。
レビュー準備とトレーサビリティ整理に責務を絞り、Step 18 の VS Code Thin Adapter や将来のモジュール単位dossier集約へ安全な入力を渡すことを完了条件とする。

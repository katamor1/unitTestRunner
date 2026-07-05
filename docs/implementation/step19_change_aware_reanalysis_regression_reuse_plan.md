# Step 19: Change-aware Reanalysis / Regression Reuse 実装計画

作成日: 2026-07-05  
状態: Draft v0.1  
対象リポジトリ: `katamor1/unitTestRunner`  
製造担当想定: CODEX  
前提文書:

- `docs/adr/0001-cli-layer-language-selection.md`
- `docs/function_level_vc6_unit_test_codex_design.md`
- `docs/review/current_assessment_and_future_outlook.md`
- `docs/implementation/step02_cli_entry_point_plan.md`
- `docs/implementation/step17_function_dossier_finalizer_review_workflow_plan.md`
- `docs/implementation/step18_vscode_thin_adapter_plan.md`

---

## 1. 位置づけ

本書は、`unitTestRunner` の第19ステップとして **Change-aware Reanalysis / Regression Reuse** を実装するための計画である。

これまでの計画では、対象関数を解析し、テストケース草案、スタブ・ハーネス雛形、ビルド、実行、エビデンス、function dossier までを生成する流れを定義した。
一方、実際の開発では、単体テスト実施後に以下が頻繁に発生する。

- テストNGにより対象関数のソースコードを修正する
- 関連する関数を修正する
- 参照・更新するグローバル変数を修正する
- 外部呼び出しやスタブ対象関数を修正する
- define / include / DSP構成が変わる
- 既存テストケースは再利用したいが、ソースと依存関係は読み直したい
- 回帰テストとして、影響があるテストだけを選んで再実行したい

そのため、Step 19 では、既存の `function_dossier` や `test_case_draft` を捨てずに、最新ソースとの差分を検出し、再解析結果と既存テスト設計を照合し、**再利用可能・要更新・無効・追加必要** を判定する仕組みを企画する。

Step 19 は、単なる再実行機能ではない。
既存テスト資産を保ったまま、現状のソースコードと依存関係に対して整合性を取り直す **変更追跡・再解析・テスト資産再利用・回帰選択** の基盤である。

---

## 2. 背景と課題

### 2.1 現状想定

Step 04 から Step 17 までの成果として、関数単位に以下が生成される。

- `source_digest.json`
- `function_location.json`
- `function_signature.json`
- `global_access.json`
- `call_report.json`
- `coverage_design.json`
- `boundary_equivalence_candidates.json`
- `test_case_draft.json`
- `harness_skeleton_report.json`
- `build_probe_report.json`
- `test_execution_report.json`
- `function_dossier.json`

しかし、テストNGや仕様変更、関連関数修正の後には、これらの成果物が最新ソースと一致しなくなる可能性がある。

### 2.2 問題

既存成果物を単純に全削除して作り直すと、以下が失われる。

- 人間がレビューしたテストケース草案
- 手動補正した期待値
- 手動補正したスタブ設定
- 手動で承認した境界値・同値クラス候補
- エビデンスとレビュー履歴
- 既存テストケースID
- 過去のNG/OK履歴

一方、既存成果物を無条件に使い回すと、以下の危険がある。

- 関数シグネチャが変わったのに古い引数でテストする
- グローバル変数の読み書きが変わったのに状態設定が古い
- 分岐条件が変わったのに古いcoverage itemを狙う
- 外部呼び出しが増えたのにスタブが足りない
- 削除された関数やcaseに対するテストが残る
- 期待値が古い仕様のまま残る

したがって、**ソースは必ず読み直すが、テスト資産は可能な限り再利用する** ための差分判定と移行ルールが必要である。

---

## 3. 目的

Step 19 の目的は、ソース変更後の関数単位テスト資産について、最新ソースとの整合性を評価し、既存テストケースを安全に再利用・更新・無効化・追加できるようにすることである。

具体的には、以下を実現する。

- 現在の `.c` / `.h` / `.dsw` / `.dsp` / build context を再読み込みできる
- 過去の function dossier と現在の再解析結果を比較できる
- 対象関数のシグネチャ変更を検出できる
- グローバルアクセス変更を検出できる
- 外部呼び出し・スタブ候補変更を検出できる
- 分岐・条件・coverage item の変更を検出できる
- 境界値・同値クラス候補の変更を検出できる
- 既存テストケース草案を再利用可能か判定できる
- 既存テストケースIDを安定して維持できる
- 手動レビュー済み項目を可能な限り保持できる
- 変更により再レビューが必要な項目を明示できる
- 影響のあるテストケースだけを回帰テスト候補として選択できる
- `change_impact_report.json` / Markdown を生成できる
- `test_case_reconciliation_report.json` / Markdown を生成できる
- `regression_selection.json` / CSV を生成できる

---

## 4. 基本方針

### 4.1 最新ソースを信頼し、既存テスト資産は再照合する

再解析では、現状のソースコードとVC6 project fileを正とする。

ただし、既存テストケースやレビュー結果は破棄しない。
再解析結果と照合し、以下へ分類する。

| 分類 | 意味 |
|---|---|
| `reusable` | そのまま再利用可能 |
| `reusable_with_review` | 大きくは使えるがレビューが必要 |
| `needs_update` | 入力・状態・stub設定などの更新が必要 |
| `obsolete` | 対応するcoverage itemや条件が消えた |
| `blocked` | 関数削除、シグネチャ大幅変更などで再利用不能 |
| `new_required` | 新しい条件・分岐・呼び出しに対して追加テストが必要 |

### 4.2 ID安定性を重視する

既存テストケースIDは、簡単には変えない。

理由:

- レビュー履歴と紐付く
- 過去エビデンスと紐付く
- 回帰テスト結果と紐付く
- ユーザーが手動補正した期待値やコメントと紐付く

方針:

- 既存 `test_case_id` は維持する
- coverage item ID が変わっても、類似条件に再マッピングできる場合はlinkを更新する
- 本当に対応先が消えた場合のみ `obsolete` とする
- 新規ケースには新しいIDを採番する

### 4.3 手動編集を保護する

ユーザーが編集した可能性がある項目は、自動上書きしない。

保護対象:

- 期待戻り値
- 期待グローバル値
- スタブ戻り値
- スタブ副作用設定
- テスト目的文
- レビューコメント
- review_status
- 手動で追加したテストケース

方針:

- 旧test_case_draftと新候補をmergeする
- 手動編集箇所は `manual_override` として保持する
- 自動更新候補はdiffとして提示する
- 明示オプションなしでは手動編集済み項目を上書きしない

### 4.4 回帰テストは影響ベースで選択する

すべてのテストを常に再実行するのではなく、変更の影響範囲から回帰候補を選ぶ。

選択基準:

- 対象関数本文が変わった
- 関数シグネチャが変わった
- 関連するグローバル変数が変わった
- 条件式・分岐が変わった
- 外部呼び出しが変わった
- スタブ候補が変わった
- テストケースが狙うcoverage itemが変わった
- 期待値・stub設定に関わる候補が変わった

---

## 5. スコープ

### 5.1 実装対象

Step 19 で実装するもの:

1. Analysis snapshot model
   - 過去解析結果snapshot
   - 現在解析結果snapshot
   - source hash / artifact hash
   - schema version
   - manual override metadata

2. Change detector
   - source hash diff
   - function signature diff
   - global access diff
   - call report diff
   - coverage design diff
   - boundary/equivalence candidate diff
   - build context diff

3. Dossier comparator
   - old function dossier と new reanalysis の比較
   - artifact stale判定
   - function name / source path / configuration一致確認

4. Test case reconciler
   - 既存test_case_draftと新規候補の照合
   - coverage link再マッピング
   - candidate link再マッピング
   - manual edit保持
   - obsolete判定
   - new required case判定

5. Regression selector
   - impacted test case抽出
   - smoke regression候補
   - full regression候補
   - impacted stubs候補
   - impacted globals候補

6. Review workflow
   - 再レビュー項目生成
   - stale expected result warning
   - stale stub setup warning
   - stale coverage warning
   - manual merge required項目生成

7. Reports
   - `change_impact_report.json`
   - `change_impact_report.md`
   - `test_case_reconciliation_report.json`
   - `test_case_reconciliation_report.md`
   - `regression_selection.json`
   - `regression_selection.csv`
   - `updated_test_case_draft.json`, 明示オプション時のみ

8. CLI 接続
   - `reanalyze-function` コマンド案
   - `reconcile-test-cases` コマンド案
   - `select-regression-tests` コマンド案
   - `analyze-function --reuse-existing-tests` 拡張案
   - VS Code Thin Adapter からの再解析導線

9. Tests
   - signature change
   - global access change
   - call change
   - branch condition change
   - coverage item removed
   - new coverage item
   - manual expected value preservation
   - obsolete test case
   - regression selection

### 5.2 対象外

Step 19 では以下を対象外とする。

- 期待結果の自動再計算
- 手動編集済みテストケースの無確認上書き
- 本番ソースの自動修正
- 本番リポジトリへのテスト資産追加
- 実測カバレッジ差分の解析
- ソースコードの意味的同値性判定
- 複雑なAST差分解析
- AIによる無審査のテストケース修正
- モジュール単位の大規模影響解析

Step 19 では、関数単位の既存テスト資産を、最新ソースに対して安全に再照合することに限定する。

---

## 6. 入力と出力

### 6.1 入力

主入力:

- 旧 `function_dossier.json`
- 旧 `test_case_draft.json`
- 旧 `coverage_design.json`
- 旧 `boundary_equivalence_candidates.json`
- 旧 `call_report.json`
- 旧 `global_access.json`
- 新しく再解析した Step 04〜12 相当の成果物
- 現在の source file
- 現在の build context
- generation / reconciliation policy

入力イメージ:

```json
{
  "function": "Control_Update",
  "workspace": "D:/work/unit_test_workspace/Control_Update",
  "previous": {
    "function_dossier": "reports/function_dossier.json",
    "test_case_draft": "reports/test_case_draft.json"
  },
  "current": {
    "source": "D:/work/product/src/control.c",
    "reanalysis_output": "reports/reanalysis/current"
  },
  "policy": {
    "preserve_manual_edits": true,
    "reuse_test_case_ids": true,
    "generate_updated_test_case_draft": false
  }
}
```

### 6.2 出力

```text
workspace/
  Control_Update/
    reports/
      reanalysis/
        current/
          source_digest.json
          function_location.json
          function_signature.json
          global_access.json
          call_report.json
          coverage_design.json
          boundary_equivalence_candidates.json
          test_case_draft.generated.json
      change_impact_report.json
      change_impact_report.md
      test_case_reconciliation_report.json
      test_case_reconciliation_report.md
      regression_selection.json
      regression_selection.csv
      updated_test_case_draft.json
```

`updated_test_case_draft.json` は、明示オプション指定時のみ生成する。
既定では、既存テストケースを直接上書きせず、reconciliation report に更新案として出す。

---

## 7. データモデル設計

### 7.1 ReanalysisRequest

```python
@dataclass
class ReanalysisRequest:
    workspace_root: Path
    function_name: str
    source_path: Path
    previous_dossier_path: Path
    previous_test_case_draft_path: Path
    policy: ReanalysisPolicy
```

### 7.2 ReanalysisPolicy

```python
@dataclass
class ReanalysisPolicy:
    preserve_manual_edits: bool
    reuse_test_case_ids: bool
    generate_updated_test_case_draft: bool
    overwrite_existing_test_case_draft: bool
    compare_build_context: bool
    compare_dependencies: bool
    compare_coverage: bool
    select_regression_tests: bool
    include_low_confidence_matches: bool
```

既定方針:

- `preserve_manual_edits = true`
- `reuse_test_case_ids = true`
- `generate_updated_test_case_draft = false`
- `overwrite_existing_test_case_draft = false`
- `compare_build_context = true`
- `compare_dependencies = true`
- `compare_coverage = true`
- `select_regression_tests = true`
- `include_low_confidence_matches = false`

### 7.3 AnalysisSnapshot

```python
@dataclass
class AnalysisSnapshot:
    snapshot_id: str
    function_name: str
    source_path: Path
    source_sha256: str | None
    build_context_hash: str | None
    created_at: str | None
    artifacts: dict[str, SnapshotArtifact]
```

### 7.4 SnapshotArtifact

```python
@dataclass
class SnapshotArtifact:
    artifact_kind: str
    path: Path
    sha256: str | None
    schema_version: str | None
    exists: bool
```

### 7.5 ChangeImpactReport

```python
@dataclass
class ChangeImpactReport:
    function_name: str
    status: str
    previous_snapshot: AnalysisSnapshot
    current_snapshot: AnalysisSnapshot
    source_changes: list[SourceChange]
    interface_changes: list[InterfaceChange]
    dependency_changes: list[DependencyChange]
    coverage_changes: list[CoverageChange]
    test_design_impacts: list[TestDesignImpact]
    regression_recommendation: RegressionRecommendation
    warnings: list[ReanalysisWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `analyzed` | 差分解析完了 |
| `no_change_detected` | 重要変更なし |
| `changed` | 変更あり |
| `incompatible_change` | 既存テスト再利用困難な変更あり |
| `blocked` | 比較に必要な情報不足 |

### 7.6 SourceChange

```python
@dataclass
class SourceChange:
    change_kind: str
    description: str
    old_value: str | None
    new_value: str | None
    impact_level: str
    evidence: str
```

`change_kind` 候補:

- `source_hash_changed`
- `build_context_changed`
- `function_location_changed`
- `function_body_changed`
- `header_changed`
- `include_changed`

### 7.7 InterfaceChange

```python
@dataclass
class InterfaceChange:
    change_kind: str
    target_name: str
    old_signature: str | None
    new_signature: str | None
    impact_level: str
    affected_test_case_ids: list[str]
    suggested_action: str
```

`change_kind` 候補:

- `return_type_changed`
- `parameter_added`
- `parameter_removed`
- `parameter_type_changed`
- `parameter_name_changed`
- `calling_convention_changed`

### 7.8 DependencyChange

```python
@dataclass
class DependencyChange:
    change_kind: str
    name: str
    old_kind: str | None
    new_kind: str | None
    impact_level: str
    affected_test_case_ids: list[str]
    suggested_action: str
```

`change_kind` 候補:

- `global_read_added`
- `global_read_removed`
- `global_write_added`
- `global_write_removed`
- `call_added`
- `call_removed`
- `stub_candidate_added`
- `stub_candidate_removed`
- `side_effect_changed`

### 7.9 CoverageChange

```python
@dataclass
class CoverageChange:
    change_kind: str
    old_coverage_id: str | None
    new_coverage_id: str | None
    old_condition: str | None
    new_condition: str | None
    similarity: float | None
    affected_test_case_ids: list[str]
    suggested_action: str
```

`change_kind` 候補:

- `coverage_item_unchanged`
- `coverage_item_modified`
- `coverage_item_removed`
- `coverage_item_added`
- `condition_changed`
- `switch_case_added`
- `switch_case_removed`
- `loop_condition_changed`
- `return_path_changed`

### 7.10 TestDesignImpact

```python
@dataclass
class TestDesignImpact:
    test_case_id: str
    impact_kind: str
    old_status: str
    new_reuse_status: str
    reason: str
    required_updates: list[str]
    review_required: bool
    confidence: str
```

`new_reuse_status` 候補:

- `reusable`
- `reusable_with_review`
- `needs_update`
- `obsolete`
- `blocked`
- `new_required`

### 7.11 TestCaseReconciliationReport

```python
@dataclass
class TestCaseReconciliationReport:
    function_name: str
    status: str
    preserved_test_cases: list[ReconciledTestCase]
    updated_test_cases: list[ReconciledTestCase]
    obsolete_test_cases: list[ReconciledTestCase]
    new_test_case_candidates: list[ReconciledTestCase]
    manual_merge_items: list[ManualMergeItem]
    warnings: list[ReanalysisWarning]
```

### 7.12 ReconciledTestCase

```python
@dataclass
class ReconciledTestCase:
    test_case_id: str
    reuse_status: str
    previous_coverage_ids: list[str]
    current_coverage_ids: list[str]
    previous_candidate_ids: list[str]
    current_candidate_ids: list[str]
    preserved_fields: list[str]
    updated_fields: list[str]
    review_required_fields: list[str]
    reason: str
    confidence: str
```

### 7.13 ManualMergeItem

```python
@dataclass
class ManualMergeItem:
    item_id: str
    test_case_id: str
    field_name: str
    previous_value: str | None
    proposed_value: str | None
    reason: str
    suggested_action: str
```

### 7.14 RegressionSelection

```python
@dataclass
class RegressionSelection:
    function_name: str
    status: str
    selected_test_cases: list[RegressionTestCase]
    skipped_test_cases: list[RegressionTestCase]
    new_required_test_cases: list[RegressionTestCase]
    selection_reason_summary: str
    warnings: list[ReanalysisWarning]
```

### 7.15 RegressionTestCase

```python
@dataclass
class RegressionTestCase:
    test_case_id: str
    selection_status: str
    priority: str
    reasons: list[str]
    related_changes: list[str]
    review_required: bool
```

`selection_status` 候補:

- `selected`
- `skipped_no_impact`
- `selected_for_smoke`
- `selected_for_full_regression`
- `blocked`
- `new_required`

### 7.16 RegressionRecommendation

```python
@dataclass
class RegressionRecommendation:
    recommendation_kind: str
    reason: str
    selected_count: int
    blocked_count: int
    new_required_count: int
    manual_review_count: int
```

`recommendation_kind` 候補:

- `no_regression_needed`
- `run_impacted_tests`
- `run_all_existing_tests`
- `update_tests_before_run`
- `manual_review_required`
- `blocked`

### 7.17 ReanalysisWarning

```python
@dataclass
class ReanalysisWarning:
    code: str
    message: str
    related_test_case_id: str | None = None
    related_artifact: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `previous_artifact_missing` | 旧成果物が見つからない |
| `current_artifact_missing` | 新成果物が見つからない |
| `manual_edit_detected` | 手動編集らしき差分を検出 |
| `test_case_id_conflict` | test case ID衝突 |
| `coverage_mapping_ambiguous` | coverage再マッピングが曖昧 |
| `signature_incompatible` | シグネチャ変更により再利用困難 |
| `stale_expected_value` | 期待値が古い可能性 |
| `stale_stub_setup` | stub設定が古い可能性 |
| `obsolete_test_case` | 既存テストが現行coverageに対応しない |
| `new_test_required` | 新規テストが必要 |

---

## 8. 差分検出設計

### 8.1 基本アルゴリズム

```text
reanalyze_and_compare(request)
  1. previous dossier / artifacts を読み込む
  2. 現在ソースに対して Step 04〜12 相当を再実行する
  3. previous snapshot と current snapshot を作る
  4. source / build_context / signature / global / call / coverage / boundary を比較する
  5. test_case_draft をreconcileする
  6. regression selection を作る
  7. reportsを生成する
```

### 8.2 シグネチャ差分

判定例:

| 差分 | 影響 |
|---|---|
| 戻り値型変更 | 期待戻り値、target invocation、assert更新が必要 |
| 引数追加 | すべての呼び出しテスト更新が必要 |
| 引数削除 | 旧入力assignmentがobsolete |
| 引数型変更 | 入力候補、境界値、fixture更新が必要 |
| 引数名変更のみ | coverage link再マッピング可能な場合あり |

### 8.3 依存関係差分

比較対象:

- globals read
- globals written
- parameter side effects
- external calls
- stub candidates
- return usage

影響例:

- global write追加: expected global observation候補を追加
- global read追加: state setup候補を追加
- call追加: stub candidate追加
- call削除: 古いstub setupがobsolete候補
- stub戻り値利用変更: stub setupレビュー必要

### 8.4 coverage差分

比較対象:

- condition raw text
- condition kind
- related variables
- related calls
- switch case labels
- loop condition
- return path

マッピング方針:

1. coverage ID完全一致
2. condition raw完全一致
3. kind + related variables + operators の一致
4. similarity score による候補
5. 判定不能なら manual merge

### 8.5 test case再利用判定

代表ルール:

| 状況 | reuse_status |
|---|---|
| coverage item・candidate・signatureが不変 | `reusable` |
| condition rawだけ軽微変更 | `reusable_with_review` |
| 入力candidateが変更 | `needs_update` |
| 対応coverage itemが削除 | `obsolete` |
| 関数引数が追加/削除 | `needs_update` または `blocked` |
| 期待値が手動編集済みで条件変更あり | `needs_update` + `stale_expected_value` |
| 新coverage itemあり | `new_required` |

### 8.6 manual edit検出

旧 `test_case_draft` が生成時と異なるかを検出するには、生成元metadataが必要である。

Step 19では以下を追加で企画する。

- test_case_draftに `generated_hash` を持つ
- 各test caseに `generated_from_candidates` を持つ
- manual editable fieldsを明示する
- 手動編集済みfieldには `manual_override=true` を付けられるようにする

既存成果物にmetadataがない場合は、以下を保守的に扱う。

- expected valuesは手動編集の可能性が高い
- review commentsは手動編集扱い
- title / purposeも手動編集の可能性あり
- 自動更新では上書きしない

---

## 9. CLI 接続設計

### 9.1 reanalyze-function コマンド案

```bat
unit-test-runner reanalyze-function ^
  --dsw D:\work\product\Product.dsw ^
  --source src\control.c ^
  --function Control_Update ^
  --configuration "Control - Win32 Debug" ^
  --workspace D:\work\unit_test_workspace\Control_Update ^
  --reuse-existing-tests
```

処理:

1. 旧 `function_dossier.json` / `test_case_draft.json` を読み込む
2. 現在ソースを再解析する
3. change impact reportを生成する
4. reconciliation reportを生成する
5. regression selectionを生成する
6. 既定では既存test_case_draftを上書きしない

### 9.2 reconcile-test-cases コマンド案

再解析済み成果物を使ってtest case再照合だけ行う。

```bat
unit-test-runner reconcile-test-cases ^
  --previous-test-case-draft reports\test_case_draft.json ^
  --previous-coverage-design reports\coverage_design.json ^
  --current-coverage-design reports\reanalysis\current\coverage_design.json ^
  --current-boundary-candidates reports\reanalysis\current\boundary_equivalence_candidates.json ^
  --out reports\test_case_reconciliation_report.json
```

### 9.3 select-regression-tests コマンド案

```bat
unit-test-runner select-regression-tests ^
  --change-impact reports\change_impact_report.json ^
  --reconciliation reports\test_case_reconciliation_report.json ^
  --out reports\regression_selection.csv
```

### 9.4 analyze-function 拡張案

既存 `analyze-function` に以下のオプションを追加する。

```text
--reuse-existing-tests
--previous-dossier PATH
--previous-test-case-draft PATH
--generate-updated-test-case-draft
--overwrite-test-case-draft
--select-regression-tests
```

ただし、既存test caseを上書きする `--overwrite-test-case-draft` は危険操作として明示指定必須にする。

---

## 10. Report 設計

### 10.1 change_impact_report.json

例:

```json
{
  "schema_version": "0.1",
  "function": {
    "name": "Control_Update",
    "status": "changed"
  },
  "interface_changes": [
    {
      "change_kind": "parameter_type_changed",
      "target_name": "sensor",
      "old_signature": "int sensor",
      "new_signature": "long sensor",
      "impact_level": "high",
      "affected_test_case_ids": ["TC_Control_Update_001"],
      "suggested_action": "Review boundary candidates and input assignments for sensor."
    }
  ],
  "dependency_changes": [
    {
      "change_kind": "call_added",
      "name": "CheckSafety",
      "impact_level": "medium",
      "suggested_action": "Add or review stub setup for CheckSafety."
    }
  ],
  "coverage_changes": [
    {
      "change_kind": "condition_changed",
      "old_coverage_id": "BR_Control_Update_001_TRUE",
      "new_coverage_id": "BR_Control_Update_001_TRUE",
      "old_condition": "sensor >= SENSOR_MIN",
      "new_condition": "sensor > SENSOR_MIN",
      "similarity": 0.86,
      "affected_test_case_ids": ["TC_Control_Update_001"],
      "suggested_action": "Review lower boundary candidate."
    }
  ],
  "regression_recommendation": {
    "recommendation_kind": "run_impacted_tests",
    "selected_count": 3,
    "manual_review_count": 1
  }
}
```

### 10.2 test_case_reconciliation_report.md

構成案:

```markdown
# Test Case Reconciliation Report

## Summary

| Status | Count |
|---|---:|
| Reusable | 5 |
| Reusable with Review | 2 |
| Needs Update | 3 |
| Obsolete | 1 |
| New Required | 2 |

## Existing Test Cases

| Test Case | Reuse Status | Reason | Required Updates |
|---|---|---|---|
| TC_Control_Update_001 | needs_update | condition changed | sensor boundary, expected return review |

## New Required Test Cases

| Reason | Related Coverage | Suggested Candidate |
|---|---|---|
| New call CheckSafety in condition | BR_Control_Update_004_TRUE | stub return true/false |

## Manual Merge Items

| Test Case | Field | Previous | Proposed | Suggested Action |
|---|---|---|---|---|
```

### 10.3 regression_selection.csv

列案:

```csv
test_case_id,selection_status,priority,reasons,related_changes,review_required
TC_Control_Update_001,selected,high,"condition changed; boundary changed","BR_Control_Update_001",true
TC_Control_Update_002,skipped_no_impact,low,"no related change","",false
TC_Control_Update_010,new_required,high,"new coverage item","BR_Control_Update_004_TRUE",true
```

---

## 11. VS Code Thin Adapter との接続

Step 18 の VS Code Thin Adapter から以下を実行できるようにする。

- `UnitTestRunner: Reanalyze Current Function`
- `UnitTestRunner: Reconcile Test Cases`
- `UnitTestRunner: Select Regression Tests`
- `UnitTestRunner: Open Change Impact Report`
- `UnitTestRunner: Open Regression Selection`

想定UX:

1. ユーザーが修正後の `.c` を開く
2. `Reanalyze Current Function` を実行する
3. extensionが `reanalyze-function --reuse-existing-tests` を呼ぶ
4. `change_impact_report.md` と `test_case_reconciliation_report.md` を開く
5. ユーザーが `regression_selection.csv` を確認する
6. 必要なら選択されたテストのみを再実行する

---

## 12. テスト計画

### 12.1 fixture 構成

```text
tests/
  fixtures/
    reanalysis/
      no_change/
        previous/
        current/
      signature_changed/
      global_changed/
      call_added/
      condition_changed/
      coverage_removed/
      coverage_added/
      manual_expected_preserved/
      obsolete_test_case/
      regression_selection/
```

### 12.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| RAN-001 | no change | previous/current同等 | no_change_detected |
| RAN-002 | source hash changed | hash差分 | source_hash_changed |
| RAN-003 | return type changed | signature差分 | high impact |
| RAN-004 | parameter added | signature差分 | affected all cases |
| RAN-005 | parameter type changed | signature差分 | needs_update |
| RAN-006 | global read added | global_access差分 | state setup review |
| RAN-007 | global write removed | global_access差分 | expected observation obsolete |
| RAN-008 | call added | call_report差分 | stub review/new required |
| RAN-009 | call removed | call_report差分 | old stub setup obsolete |
| RAN-010 | condition changed | coverage差分 | coverage remap |
| RAN-011 | coverage removed | coverage差分 | obsolete test case |
| RAN-012 | coverage added | coverage差分 | new_required |
| RAN-013 | manual expected preserved | old expected manual | preserved field |
| RAN-014 | stale expected | condition changed + expected | stale_expected_value warning |
| RAN-015 | regression selected | impacted cases | selected list |
| RAN-016 | no impact skipped | unaffected case | skipped_no_impact |
| RAN-017 | report json | change report | JSON parse可能 |
| RAN-018 | report md | reconciliation report | expected sectionあり |
| RAN-019 | csv output | regression csv | expected columnsあり |
| RAN-020 | reanalyze-function cli | explicit inputs | reports生成 |
| RAN-021 | reconcile-test-cases cli | explicit inputs | reconciliation生成 |
| RAN-022 | select-regression-tests cli | explicit inputs | selection生成 |

### 12.3 テスト方針

- 再解析そのものは既存Stepのfixture JSONを使って比較する
- 実ソース再解析を伴うintegration testは少数にする
- manual edit preservationを重点的にテストする
- ID再利用ルールを明示assertする
- Markdownは主要sectionの存在を検証する
- CSVはheader列と行数を検証する

---

## 13. 実装タスク分解

### Task 19-01: Reanalysis model 定義

成果物:

- `src/unit_test_runner/reanalysis/reanalysis_models.py`
- `ReanalysisRequest`
- `ReanalysisPolicy`
- `AnalysisSnapshot`
- `SnapshotArtifact`
- `ChangeImpactReport`
- `SourceChange`
- `InterfaceChange`
- `DependencyChange`
- `CoverageChange`
- `TestDesignImpact`
- `TestCaseReconciliationReport`
- `ReconciledTestCase`
- `ManualMergeItem`
- `RegressionSelection`
- `RegressionTestCase`
- `RegressionRecommendation`
- `ReanalysisWarning`

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 19-02: Snapshot builder

成果物:

- `src/unit_test_runner/reanalysis/snapshot_builder.py`
- previous/current snapshot生成
- artifact hash記録
- missing artifact warning

完了条件:

- RAN-001 / RAN-002 が通る

### Task 19-03: Signature diff analyzer

成果物:

- `signature_diff.py`
- return type / parameter diff
- affected test case推定

完了条件:

- RAN-003 から RAN-005 が通る

### Task 19-04: Dependency diff analyzer

成果物:

- `dependency_diff.py`
- global / call / stub diff
- state/stub impact生成

完了条件:

- RAN-006 から RAN-009 が通る

### Task 19-05: Coverage diff analyzer

成果物:

- `coverage_diff.py`
- coverage item matching
- condition similarity
- added/removed/modified分類

完了条件:

- RAN-010 から RAN-012 が通る

### Task 19-06: Test case reconciler

成果物:

- `test_case_reconciler.py`
- ID再利用
- manual field preservation
- reuse_status判定
- new_required case候補

完了条件:

- RAN-013 / RAN-014 が通る

### Task 19-07: Regression selector

成果物:

- `regression_selector.py`
- impacted test selection
- skip no impact
- priority付与

完了条件:

- RAN-015 / RAN-016 が通る

### Task 19-08: Report writer

成果物:

- `reanalysis_report_writer.py`
- `reports/change_impact_markdown.py`
- `reports/test_case_reconciliation_markdown.py`
- `reports/regression_selection_csv.py`

完了条件:

- RAN-017 / RAN-018 / RAN-019 が通る

### Task 19-09: reanalyze-function CLI 実装

成果物:

- `reanalyze-function` コマンド
- previous/current指定
- `--reuse-existing-tests`
- `--generate-updated-test-case-draft`

完了条件:

- RAN-020 が通る

### Task 19-10: reconcile-test-cases CLI 実装

成果物:

- `reconcile-test-cases` コマンド
- explicit report input対応

完了条件:

- RAN-021 が通る

### Task 19-11: select-regression-tests CLI 実装

成果物:

- `select-regression-tests` コマンド
- CSV出力

完了条件:

- RAN-022 が通る

### Task 19-12: VS Code Adapter 接続

成果物:

- `Reanalyze Current Function`
- `Open Change Impact Report`
- `Open Regression Selection`
- 明示上書き確認

完了条件:

- VS Codeから再解析レポートを開ける

### Task 19-13: fixture / test 整備

成果物:

- `tests/fixtures/reanalysis/...`
- `tests/unit/test_snapshot_builder.py`
- `tests/unit/test_signature_diff.py`
- `tests/unit/test_dependency_diff.py`
- `tests/unit/test_coverage_diff.py`
- `tests/unit/test_test_case_reconciler.py`
- `tests/unit/test_regression_selector.py`
- `tests/unit/test_reanalysis_cli.py`

完了条件:

- RAN-001 から RAN-022 が通る

---

## 14. 受け入れ基準

Step 19 は、以下をすべて満たしたら完了とする。

1. previous/current snapshotを作成できる
2. source hash変更を検出できる
3. build context変更を検出できる
4. function signature変更を検出できる
5. global access変更を検出できる
6. call/stub candidate変更を検出できる
7. coverage item変更を検出できる
8. coverage itemの再マッピング候補を生成できる
9. 既存test case IDを維持できる
10. 手動編集済みfieldを保護できる
11. reusable / needs_update / obsolete / new_required を分類できる
12. stale expected value / stale stub setup をwarningにできる
13. impactがあるtest caseをregression対象に選べる
14. impactがないtest caseをskip候補にできる
15. `change_impact_report.json` / md を生成できる
16. `test_case_reconciliation_report.json` / md を生成できる
17. `regression_selection.json` / csv を生成できる
18. 既定では既存test_case_draftを上書きしない
19. 明示オプション時のみupdated_test_case_draftを生成できる
20. `reanalyze-function` が既存テスト再利用前提で再解析できる
21. `reconcile-test-cases` が明示入力から再照合できる
22. `select-regression-tests` が回帰候補を出力できる
23. VS Code Thin Adapterから再解析結果を開ける設計になっている
24. 期待結果を自動確定しない
25. 本番リポジトリを変更しない

---

## 15. 成果物

Step 19 の成果物は以下とする。

```text
src/
  unit_test_runner/
    reanalysis/
      __init__.py
      reanalysis_models.py
      snapshot_builder.py
      signature_diff.py
      dependency_diff.py
      coverage_diff.py
      test_case_reconciler.py
      regression_selector.py
      reanalysis_report_writer.py
    reports/
      change_impact_markdown.py
      test_case_reconciliation_markdown.py
      regression_selection_csv.py
    cli/
      commands.py

tests/
  fixtures/
    reanalysis/
      no_change/
      signature_changed/
      global_changed/
      call_added/
      condition_changed/
      coverage_removed/
      coverage_added/
      manual_expected_preserved/
      obsolete_test_case/
      regression_selection/
  unit/
    test_snapshot_builder.py
    test_signature_diff.py
    test_dependency_diff.py
    test_coverage_diff.py
    test_test_case_reconciler.py
    test_regression_selector.py
    test_reanalysis_cli.py
```

生成先workspace例:

```text
workspace/
  Control_Update/
    reports/
      reanalysis/
        current/
      change_impact_report.json
      change_impact_report.md
      test_case_reconciliation_report.json
      test_case_reconciliation_report.md
      regression_selection.json
      regression_selection.csv
      updated_test_case_draft.json
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/test_design/test_case_models.py` 必要な場合のみ
- `src/unit_test_runner/dossier/dossier_models.py` 必要な場合のみ
- `vscode/unit-test-runner-vscode` 必要な場合のみ

---

## 16. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| 手動編集の上書き | レビュー済み期待値を自動生成値で消す | 既定では上書き禁止。manual field保護を最優先する |
| coverage再マッピング誤り | 似ているが意味が違う条件を同一扱いする | similarityを出し、曖昧ならmanual mergeにする |
| 変更なし判定の誤り | hash以外の依存変化を見落とす | build context / dependency / coverageも比較する |
| テストケースID崩壊 | IDを作り直すと履歴が失われる | 既存ID維持を基本にする |
| 回帰選択漏れ | 影響ありテストをskipしてしまう | 不確実な場合はselectedまたはreview_requiredに倒す |
| 候補過多 | new_requiredが大量に出る | priorityとimpact levelで整理する |
| 実装複雑化 | 差分・mergeは複雑 | 最初はJSON artifact同士の構造比較に限定する |

---

## 17. 今後の展望

Step 19 完了後、以下へ進める。

### 17.1 モジュール単位回帰への拡張

関数単位の reanalysis / regression selection が安定した後、モジュール単位へ拡張する。

候補:

- 複数function dossierの集約
- 関数依存グラフから影響関数を選択
- 変更されたglobalに関連する関数の回帰選択
- 共通stub変更時の関連テスト選択

### 17.2 履歴管理

過去のdossierと実行結果を蓄積し、変化を追えるようにする。

候補:

- `history/` 配下にsnapshot保存
- 前回OK/NGとの差分
- flaky候補検出
- テストケースの寿命管理

### 17.3 VS Code連携強化

- 変更関数の候補表示
- regression_selection.csv の表示
- stale test case warning
- 再レビュー項目のQuick Pick表示

---

## 18. まとめ

Step 19 は、単体テスト実施後のソース修正や関連依存の変更に対して、既存テスト資産を安全に再利用するための変更追跡・再解析・回帰選択のステップである。

このステップにより、ソースと依存関係は最新状態で読み直しつつ、作成済みテストケース、手動レビュー済み期待値、スタブ設定、エビデンス履歴を可能な限り保持できる。

重要なのは、既存テストを無条件に再利用するのではなく、最新ソースとの差分をもとに `reusable`、`needs_update`、`obsolete`、`new_required` へ分類し、影響のあるテストだけを回帰候補として選択することである。

Step 19 は、関数単位テスト支援を一度きりの生成ツールから、継続開発で使える回帰テスト支援ツールへ進化させるための重要な改善である。

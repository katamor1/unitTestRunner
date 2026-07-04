# Step 12: Test Case Draft Generator 実装計画

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

---

## 1. 位置づけ

本書は、`unitTestRunner` の第12ステップとして **Test Case Draft Generator** を実装するための計画である。

Step 11 では、Step 10 の `coverage_design`、Step 07 の `function_signature`、Step 08 の `global_access`、Step 09 の `call_report` を使い、境界値候補、同値クラス候補、NULL / 非NULL候補、状態候補、スタブ戻り値候補を `boundary_equivalence_candidates` として生成する計画を定義した。

Step 12 では、これまでの解析結果を統合し、レビュー可能な **テストケース草案** を生成する。

ここで生成するものは、実行可能なCテストコードではない。
この段階では、テスト設計者がレビュー・編集できるテストケース表を作ることを目的とする。

Step 12 の主な責務は以下である。

- coverage item と値候補を組み合わせてテストケース草案を作る
- 引数入力、グローバル初期状態、file static状態、extern状態、スタブ戻り値をテスト条件として整理する
- 期待戻り値、期待グローバル値、期待呼び出しなどは未確定または候補として扱う
- 1つのcoverage itemに対して最低限のテストケース候補を作る
- 境界値・同値クラス候補から過剰な組み合わせを避ける
- スタブ候補とスタブ戻り値候補をテストケースに紐付ける
- review_required、confidence、未解決事項を明示する
- `test_case_draft.json` / `test_case_draft.md` / `test_case_draft.csv` を生成する
- Step 13 の Stub / Harness Skeleton Generator に渡せるテスト設計情報を整理する

---

## 2. 目的

Step 12 の目的は、関数単位テストの設計開始点となる **レビュー可能なテストケース草案** を自動生成することである。

具体的には、以下を実現する。

- Step 10 の coverage item ごとにテストケース草案を生成できる
- Step 11 の input / state / stub return candidate をテスト条件へ配置できる
- 分岐true/false、条件true/false、switch case/default、loop zero/one/many、return pathをテスト目的として表現できる
- 引数入力値、グローバル状態、スタブ戻り値、スタブ副作用候補を1つのテストケースにまとめられる
- 同じ候補を使い回せるcoverage itemは統合候補として扱える
- テストケース数が爆発しないよう、最小セットと追加候補を分けられる
- 期待結果が未確定な箇所を `expected_result_review_required` として明示できる
- スタブ設定が必要なテストケースを明示できる
- file static状態など、setup困難な条件を warning として残せる
- CSV形式でExcel等へ持ち出せるテストケース表を生成できる
- Markdown形式でレビューしやすいレポートを生成できる
- JSON形式で後続のスタブ・ハーネス生成へ渡せる
- `analyze-function` を Step 12 時点で「テストケース草案生成」まで進められる

---

## 3. スコープ

### 3.1 実装対象

Step 12 で実装するもの:

1. Test case model
   - test case draft
   - test objective
   - input assignment
   - state setup
   - stub setup
   - expected observation placeholder
   - coverage link
   - review status

2. Coverage-to-case mapper
   - branch true / false
   - condition true / false
   - switch case / default
   - loop zero / one / many
   - return path
   - ternary true / false

3. Candidate selector
   - Step 11 の候補からcoverage itemに適した候補を選ぶ
   - 最小候補と追加候補を分ける
   - 重複候補をまとめる
   - confidence / review_required を引き継ぐ

4. Test condition builder
   - parameter input
   - global state setup
   - file static state setup warning
   - extern state setup
   - stub return setup
   - stub side effect setup placeholder

5. Expected observation placeholder builder
   - expected return value placeholder
   - expected global value placeholder
   - expected parameter side effect placeholder
   - expected call count placeholder
   - expected call argument placeholder
   - expected coverage target placeholder

6. Combination control
   - pairwiseや全組み合わせは行わない
   - coverage itemごとの代表候補を優先
   - additional_cases として候補を分離
   - 過剰なケース数を warning として残す

7. Reports
   - `test_case_draft.json`
   - `test_case_draft.md`
   - `test_case_draft.csv`

8. CLI 接続
   - `analyze-function` を test case draft生成まで進める
   - `generate-test-draft` を実用実装へ更新する
   - status `partial` または `test_case_draft_generated` を返す
   - Step 13 の Stub / Harness Skeleton Generator が必要である旨を message に含める

9. Tests
   - branch true/false case
   - condition true/false case
   - switch case/default case
   - loop zero/one/many case
   - return path case
   - boundary candidate case
   - null pointer case
   - global state case
   - stub return case
   - unresolved expected result
   - csv output
   - markdown output

### 3.2 対象外

Step 12 では以下を対象外とする。

- 実行可能なCテストコード生成
- テストランナー生成
- スタブCコード生成
- モックCコード生成
- 期待結果の最終確定
- 実際のVC6ビルド
- 実際のテスト実行
- 実測カバレッジ計測
- テストケース最小化の完全最適化
- SAT/SMTによる条件充足性判定
- 複雑な組み合わせテスト生成
- AIによる期待値確定の自動採用

Step 12 では、解析結果からレビュー可能なテストケース草案を生成することに限定する。

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

入力イメージ:

```json
{
  "source": "D:/work/product/src/control.c",
  "function": "Control_Update",
  "function_signature": "reports/function_signature.json",
  "global_access": "reports/global_access.json",
  "call_report": "reports/call_report.json",
  "coverage_design": "reports/coverage_design.json",
  "boundary_equivalence_candidates": "reports/boundary_equivalence_candidates.json"
}
```

### 4.2 出力

Step 12 の主要出力は `test_case_draft` である。

```text
workspace/
  Control_Update/
    reports/
      source_digest.json
      function_location.json
      function_signature.json
      global_access.json
      call_report.json
      coverage_design.json
      boundary_equivalence_candidates.json
      test_case_draft.json
      test_case_draft.md
      test_case_draft.csv
    intermediate/
      masked_source.c
      function_slice.c
```

`test_case_draft.json` は Step 13 以降の入力になる。

---

## 5. データモデル設計

### 5.1 TestCaseDraftRequest

```python
@dataclass
class TestCaseDraftRequest:
    source_path: Path
    function_signature: FunctionSignature
    global_access: GlobalAccessReport
    call_report: CallReport
    coverage_design: CoverageDesignReport
    boundary_candidates: BoundaryEquivalenceReport
    generation_policy: TestCaseGenerationPolicy
```

役割:

- Test Case Draft Generator の入力条件をまとめる
- CLI / internal usecase の境界を明確にする

### 5.2 TestCaseGenerationPolicy

```python
@dataclass
class TestCaseGenerationPolicy:
    max_cases_per_coverage_item: int
    include_additional_candidates: bool
    include_review_required_candidates: bool
    merge_compatible_coverage_items: bool
    prefer_high_confidence: bool
    emit_csv: bool
    emit_markdown: bool
```

既定方針:

- `max_cases_per_coverage_item = 2`
- `include_additional_candidates = true`
- `include_review_required_candidates = true`
- `merge_compatible_coverage_items = false` initially
- `prefer_high_confidence = true`

### 5.3 TestCaseDraftReport

```python
@dataclass
class TestCaseDraftReport:
    source_path: Path
    function_name: str
    status: str
    generation_policy: TestCaseGenerationPolicy
    test_cases: list[TestCaseDraft]
    additional_case_candidates: list[TestCaseDraft]
    coverage_summary: CoverageDraftSummary
    unresolved_items: list[UnresolvedTestDesignItem]
    warnings: list[TestCaseDraftWarning]
```

`status` 候補:

| status | 意味 |
|---|---|
| `generated` | テストケース草案を生成できた |
| `partial` | 一部不足があるが主要草案は生成できた |
| `insufficient_information` | 草案生成に必要な情報が不足している |
| `too_many_candidates` | 候補が多すぎて絞り込みが必要 |

### 5.4 TestCaseDraft

```python
@dataclass
class TestCaseDraft:
    test_case_id: str
    title: str
    target_function: str
    purpose: str
    priority: str
    case_kind: str
    preconditions: list[TestPrecondition]
    input_assignments: list[TestInputAssignment]
    state_setups: list[TestStateSetup]
    stub_setups: list[TestStubSetup]
    execution_steps: list[TestExecutionStep]
    expected_observations: list[ExpectedObservation]
    coverage_links: list[TestCoverageLink]
    candidate_links: list[str]
    review_status: str
    confidence: str
    warnings: list[TestCaseDraftWarning]
```

`case_kind` 候補:

| case_kind | 意味 |
|---|---|
| `branch` | 分岐到達用 |
| `condition` | 条件真偽用 |
| `boundary` | 境界値用 |
| `equivalence` | 同値クラス用 |
| `switch_case` | switch case用 |
| `loop` | loop回数用 |
| `return_path` | return経路用 |
| `stub_behavior` | スタブ戻り値制御用 |
| `state` | global状態用 |
| `review` | 人手レビュー前提 |

`review_status` 候補:

- `draft`
- `review_required`
- `blocked`
- `ready_for_harness`

### 5.5 TestPrecondition

```python
@dataclass
class TestPrecondition:
    description: str
    source: str
    review_required: bool
```

例:

- `VC6 Debug configuration is selected`
- `global g_state can be set before function call`
- `stub CheckLimit is available`

### 5.6 TestInputAssignment

```python
@dataclass
class TestInputAssignment:
    target_name: str
    target_kind: str
    value_expression: str
    value_kind: str
    source_candidate_id: str | None
    rationale: str
    review_required: bool
    confidence: str
```

`target_kind` 候補:

- `parameter`
- `global`
- `file_static`
- `extern`
- `stub_return`
- `unknown`

### 5.7 TestStateSetup

```python
@dataclass
class TestStateSetup:
    variable_name: str
    scope: str
    value_expression: str
    setup_method_hint: str
    source_candidate_id: str | None
    review_required: bool
    confidence: str
```

`setup_method_hint` 候補:

- `direct_assignment`
- `initializer_function`
- `wrapper_required`
- `not_directly_accessible`
- `unknown`

### 5.8 TestStubSetup

```python
@dataclass
class TestStubSetup:
    stub_name: str
    setup_kind: str
    value_expression: str | None
    call_behavior: str | None
    source_candidate_id: str | None
    related_call_id: str | None
    review_required: bool
    confidence: str
```

`setup_kind` 候補:

| setup_kind | 意味 |
|---|---|
| `return_value` | 戻り値制御 |
| `side_effect` | 副作用制御 |
| `call_count_observation` | 呼び出し回数観測 |
| `argument_capture` | 引数記録 |
| `not_required` | スタブ不要 |
| `unknown` | 判定不能 |

### 5.9 TestExecutionStep

```python
@dataclass
class TestExecutionStep:
    order: int
    action: str
    detail: str
    review_required: bool
```

標準ステップ:

1. reset generated stubs
2. setup globals / states
3. setup stub return values
4. call target function
5. observe return value / state / calls

### 5.10 ExpectedObservation

```python
@dataclass
class ExpectedObservation:
    observation_kind: str
    target_name: str | None
    expected_expression: str | None
    source: str
    review_required: bool
    confidence: str
    note: str | None
```

`observation_kind` 候補:

| observation_kind | 意味 |
|---|---|
| `return_value` | 戻り値確認 |
| `global_value` | global値確認 |
| `parameter_side_effect` | pointer/array引数先確認 |
| `stub_call_count` | スタブ呼び出し回数確認 |
| `stub_argument` | スタブ引数確認 |
| `coverage_target` | 対象coverage item到達確認 |
| `not_determined` | 未確定 |

注意:

- Step 12 では期待値を確定しない
- 条件から明らかなcoverage targetは観測候補として出す
- 戻り値やglobal値は `review_required=true` を既定にする

### 5.11 TestCoverageLink

```python
@dataclass
class TestCoverageLink:
    coverage_id: str
    coverage_type: str
    target_id: str
    intended_value: str | None
    link_reason: str
    confidence: str
```

### 5.12 CoverageDraftSummary

```python
@dataclass
class CoverageDraftSummary:
    total_coverage_items: int
    covered_by_draft_count: int
    uncovered_coverage_ids: list[str]
    coverage_to_test_cases: dict[str, list[str]]
```

### 5.13 UnresolvedTestDesignItem

```python
@dataclass
class UnresolvedTestDesignItem:
    item_id: str
    item_kind: str
    description: str
    related_test_case_ids: list[str]
    reason: str
    suggested_action: str
```

`item_kind` 候補:

- `expected_return_unknown`
- `expected_global_unknown`
- `file_static_setup_unknown`
- `stub_behavior_unknown`
- `candidate_conflict`
- `coverage_unmapped`
- `condition_unsatisfied`
- `manual_review_required`

### 5.14 TestCaseDraftWarning

```python
@dataclass
class TestCaseDraftWarning:
    code: str
    message: str
    related_test_case_id: str | None = None
    related_coverage_id: str | None = None
    text: str | None = None
```

warning code 例:

| code | 意味 |
|---|---|
| `expected_result_not_determined` | 期待結果が未確定 |
| `coverage_item_unmapped` | coverage itemに候補を割り当てられない |
| `candidate_conflict` | 値候補同士が矛盾する可能性 |
| `too_many_candidate_combinations` | 組み合わせが多すぎる |
| `file_static_setup_requires_wrapper` | file static設定にwrapper等が必要 |
| `stub_required_but_not_generated` | スタブが必要だが未生成 |
| `state_setup_review_required` | 状態設定にレビューが必要 |
| `low_confidence_candidate_used` | 低confidence候補を使用した |
| `manual_review_required` | 人手確認が必要 |

---

## 6. 生成設計

### 6.1 基本アルゴリズム

処理フロー:

```text
generate_test_case_draft(request)
  1. coverage_design から coverage item を取得する
  2. boundary candidates から coverage item に紐付く候補を取得する
  3. function_signature から parameter一覧を取得する
  4. global_access から state setup候補を取得する
  5. call_report から stub candidateを取得する
  6. coverage itemごとに代表候補を選択する
  7. TestCaseDraft を生成する
  8. 入力値、状態値、スタブ戻り値、実行手順、期待観測placeholderを埋める
  9. coverage itemとのlinkを作る
 10. coverage未割当、期待値未確定、setup困難などを unresolved_items にする
 11. 追加候補を additional_case_candidates にする
 12. CSV / Markdown / JSON を出力する
```

### 6.2 coverage item から test case への変換

代表ルール:

| coverage_type | case_kind | 生成方針 |
|---|---|---|
| `branch_true` | `branch` | 条件trueになる候補を選ぶ |
| `branch_false` | `branch` | 条件falseになる候補を選ぶ |
| `condition_true` | `condition` | 対象条件をtrueにする候補を選ぶ |
| `condition_false` | `condition` | 対象条件をfalseにする候補を選ぶ |
| `switch_case` | `switch_case` | case label値を選ぶ |
| `switch_default` | `switch_case` | default到達候補を選ぶ |
| `loop_zero` | `loop` | 0回候補を選ぶ |
| `loop_one` | `loop` | 1回候補を選ぶ |
| `loop_many` | `loop` | 複数回候補を選ぶ |
| `return_path` | `return_path` | return到達条件候補を選ぶ |
| `ternary_true` | `branch` | true式候補を選ぶ |
| `ternary_false` | `branch` | false式候補を選ぶ |
| `review` | `review` | 手動レビュー用ケースにする |

### 6.3 候補選択方針

優先順位:

1. coverage itemに直接linkされた候補
2. high confidence候補
3. review_requiredだが根拠が明確な候補
4. 同一targetの境界値候補
5. 型ベース同値クラス候補
6. low confidence候補

制約:

- 1 coverage itemに対して既定では最大2ケースまで
- 候補が多い場合は additional_case_candidates に回す
- 互いに矛盾する候補は同じテストケースに入れない
- 矛盾判定が難しい場合は warning `candidate_conflict` を出す

### 6.4 引数入力の組み立て

Step 07 の parameters を基準に、Step 11 の InputValueCandidate を割り当てる。

方針:

- 対象coverageに関係する引数は候補値を設定する
- 関係しない引数には default candidate を設定する
- default candidate がない場合は `TBD_VALID_VALUE` として `review_required=true`
- pointer引数は NULL / non_null の候補を明示する
- non_null pointer には fixture setup hintを付ける
- array引数は empty / one / many 候補を明示する

### 6.5 状態設定の組み立て

Step 08 の global_access と Step 11 の StateValueCandidate を使う。

方針:

- 条件式に必要なglobal状態は state_setups に入れる
- file static は直接設定できない可能性があるため `setup_method_hint=not_directly_accessible` または `wrapper_required`
- externは direct_assignment候補にする
- 初期化関数が必要そうな場合は `initializer_function` hintを出す。ただし確定しない

### 6.6 スタブ設定の組み立て

Step 09 の StubCandidate と Step 11 の StubReturnCandidate を使う。

方針:

- 条件式内call resultを制御する必要がある場合、stub_setup `return_value` を生成する
- 外部関数の戻り値が使われている場合、return value candidateを設定する
- 呼び出し回数や引数観測が必要な場合、placeholderを生成する
- スタブが必要だが未生成なので warning `stub_required_but_not_generated` を付ける
- Step 13 でスタブ雛形生成の入力にできるよう、stub name / setup kind / related call id を保持する

### 6.7 期待観測placeholder

Step 12 では期待値を確定しない。
ただし、何を観測すべきかを示す。

観測候補:

- 戻り値
- global値
- file static値
- pointer/array引数先
- stub call count
- stub captured argument
- coverage target到達

方針:

- return path coverageの場合、return value観測placeholderを作る
- global writeがある場合、global_value観測placeholderを作る
- parameter side effectがある場合、parameter_side_effect観測placeholderを作る
- stub candidateがある場合、stub_call_count / stub_argument観測placeholderを作る
- 期待式は `TBD_EXPECTED_*` とし、review_required=true を既定にする

### 6.8 CSV出力方針

CSVはExcelやレビュー表で扱いやすい平坦形式にする。

列案:

```text
id,title,target_function,purpose,priority,case_kind,input_assignments,state_setups,stub_setups,execution_steps,expected_observations,coverage_ids,candidate_ids,review_status,confidence,warnings
```

方針:

- list項目は `;` 区切りの短い文字列にする
- JSONを埋め込みすぎない
- 詳細はJSON/Markdownへ誘導する
- cp932で開く需要がある場合は後続で `--csv-encoding cp932` を検討する

---

## 7. CLI 接続設計

### 7.1 analyze-function の Step 12 接続

Step 12 では、`analyze-function` をテストケース草案生成まで進める。

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
5. Step 08 の global_access を生成または読み込む
6. Step 09 の call_report を生成または読み込む
7. Step 10 の coverage_design を生成または読み込む
8. Step 11 の boundary_equivalence_candidates を生成または読み込む
9. Step 12 の Test Case Draft Generator を実行する
10. `test_case_draft.json` を生成する
11. `test_case_draft.md` を生成する
12. `test_case_draft.csv` を生成する
13. Step 13 の Stub / Harness Skeleton Generator が必要であることを message に含める
14. 抽出に成功した場合、status `partial` または `test_case_draft_generated` を返す

### 7.2 generate-test-draft の実用化

Step 02 で定義した `generate-test-draft` を Step 12 で実用実装へ更新する。

```bat
unit-test-runner generate-test-draft ^
  --dossier D:\work\unit_test_workspace\Control_Update\reports\function_dossier.json ^
  --out D:\work\unit_test_workspace\Control_Update\reports\test_case_draft.csv ^
  --format csv
```

Step 12 時点では、`function_dossier.json` が未完成の場合があり得るため、以下の入力形式も許容する。

```bat
unit-test-runner generate-test-draft ^
  --function-signature reports\function_signature.json ^
  --global-access reports\global_access.json ^
  --call-report reports\call_report.json ^
  --coverage-design reports\coverage_design.json ^
  --boundary-candidates reports\boundary_equivalence_candidates.json ^
  --out reports\test_case_draft.csv ^
  --format csv
```

出力形式:

- `--format json`
- `--format md`
- `--format csv`
- `--format all`

---

## 8. Report 設計

### 8.1 test_case_draft.json

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
    "status": "generated"
  },
  "test_cases": [
    {
      "test_case_id": "TC_Control_Update_001",
      "title": "mode is MODE_AUTO and sensor is at lower boundary",
      "target_function": "Control_Update",
      "purpose": "Cover BR_Control_Update_001_TRUE with sensor at SENSOR_MIN",
      "priority": "high",
      "case_kind": "boundary",
      "input_assignments": [
        {
          "target_name": "mode",
          "target_kind": "parameter",
          "value_expression": "MODE_AUTO",
          "rationale": "mode == MODE_AUTO condition",
          "review_required": true
        },
        {
          "target_name": "sensor",
          "target_kind": "parameter",
          "value_expression": "SENSOR_MIN",
          "rationale": "at lower boundary",
          "review_required": true
        }
      ],
      "state_setups": [],
      "stub_setups": [
        {
          "stub_name": "CheckLimit",
          "setup_kind": "return_value",
          "value_expression": "true",
          "related_call_id": "CALL_001",
          "review_required": true
        }
      ],
      "execution_steps": [
        {
          "order": 1,
          "action": "reset_stubs",
          "detail": "Reset generated stub state"
        },
        {
          "order": 2,
          "action": "call_function",
          "detail": "Control_Update(mode, sensor)"
        }
      ],
      "expected_observations": [
        {
          "observation_kind": "return_value",
          "target_name": "return",
          "expected_expression": "TBD_EXPECTED_RETURN",
          "review_required": true
        },
        {
          "observation_kind": "coverage_target",
          "target_name": "BR_Control_Update_001_TRUE",
          "expected_expression": "covered_by_design",
          "review_required": true
        }
      ],
      "coverage_links": [
        {
          "coverage_id": "BR_Control_Update_001_TRUE",
          "coverage_type": "branch_true",
          "target_id": "BR_001",
          "intended_value": "true"
        }
      ],
      "review_status": "review_required",
      "confidence": "medium"
    }
  ],
  "unresolved_items": [
    {
      "item_kind": "expected_return_unknown",
      "description": "Expected return value must be reviewed from specification."
    }
  ],
  "warnings": []
}
```

### 8.2 test_case_draft.md

内容例:

```markdown
# Test Case Draft Report

## Target

- Source: D:/work/product/src/control.c
- Function: Control_Update
- Status: generated

## Summary

| Item | Count |
|---|---:|
| Test Cases | 8 |
| Coverage Items | 10 |
| Covered by Draft | 8 |
| Unresolved Items | 3 |

## Test Cases

### TC_Control_Update_001: mode is MODE_AUTO and sensor is at lower boundary

- Purpose: Cover BR_Control_Update_001_TRUE with sensor at SENSOR_MIN
- Priority: high
- Kind: boundary
- Review Status: review_required

#### Inputs

| Target | Value | Rationale | Review |
|---|---|---|---|
| mode | MODE_AUTO | mode == MODE_AUTO condition | yes |
| sensor | SENSOR_MIN | at lower boundary | yes |

#### State Setup

なし

#### Stub Setup

| Stub | Kind | Value | Review |
|---|---|---|---|
| CheckLimit | return_value | true | yes |

#### Expected Observations

| Kind | Target | Expected | Review |
|---|---|---|---|
| return_value | return | TBD_EXPECTED_RETURN | yes |
| coverage_target | BR_Control_Update_001_TRUE | covered_by_design | yes |

## Unresolved Items

| Kind | Description | Suggested Action |
|---|---|---|
| expected_return_unknown | Expected return value must be reviewed from specification. | Review function specification |
```

### 8.3 test_case_draft.csv

列案:

```csv
id,title,target_function,purpose,priority,case_kind,input_assignments,state_setups,stub_setups,expected_observations,coverage_ids,candidate_ids,review_status,confidence,warnings
TC_Control_Update_001,mode is MODE_AUTO and sensor is at lower boundary,Control_Update,Cover BR_Control_Update_001_TRUE with sensor at SENSOR_MIN,high,boundary,"mode=MODE_AUTO; sensor=SENSOR_MIN","","CheckLimit.return=true","return=TBD_EXPECTED_RETURN; coverage=BR_Control_Update_001_TRUE",BR_Control_Update_001_TRUE,"IN_mode_001; IN_sensor_002",review_required,medium,"expected_result_not_determined"
```

---

## 9. テスト計画

### 9.1 fixture 構成

```text
tests/
  fixtures/
    test_case_draft/
      simple_branch/
        function_signature.json
        global_access.json
        call_report.json
        coverage_design.json
        boundary_equivalence_candidates.json
      switch_cases/
      loop_cases/
      global_state/
      stub_return/
      unresolved_expected/
      too_many_candidates/
```

### 9.2 単体テストケース

| ID | 観点 | 入力 | 期待結果 |
|---|---|---|---|
| TCD-001 | branch true | branch_true + candidate | test case生成 |
| TCD-002 | branch false | branch_false + candidate | test case生成 |
| TCD-003 | condition true/false | condition item | condition case生成 |
| TCD-004 | switch case | switch_case item | case value入力生成 |
| TCD-005 | switch default | default item | default候補生成 |
| TCD-006 | loop zero | loop_zero | zero case生成 |
| TCD-007 | loop one/many | loop_one/many | loop cases生成 |
| TCD-008 | return path | return_path | return観測placeholder |
| TCD-009 | boundary input | boundary candidate | input assignment生成 |
| TCD-010 | null pointer | NULL candidate | pointer input生成 |
| TCD-011 | global state | StateValueCandidate | state setup生成 |
| TCD-012 | file static state | file static candidate | wrapper warning |
| TCD-013 | stub return | StubReturnCandidate | stub setup生成 |
| TCD-014 | call count observation | StubCandidate | expected stub call placeholder |
| TCD-015 | no candidate | coverage item only | unresolved coverage item |
| TCD-016 | candidate conflict | conflicting candidates | warning candidate_conflict |
| TCD-017 | too many candidates | many candidates | additional_case_candidatesへ分離 |
| TCD-018 | expected unknown | no expected result | expected_result_not_determined |
| TCD-019 | json output | test_case_draft.json | JSON parse可能 |
| TCD-020 | markdown output | test_case_draft.md | expected sectionあり |
| TCD-021 | csv output | test_case_draft.csv | expected columnsあり |
| TCD-022 | generate-test-draft cli | explicit report inputs | csv生成 |
| TCD-023 | analyze-function integration | Step04-12 | test_case_draft生成 |

### 9.3 テスト方針

- mapperはcoverage item単体でテストする
- candidate selectorはcandidate list単体でテストする
- writerはJSON / Markdown / CSVを個別にテストする
- integration testではStep 10 coverage_designとStep 11 boundary候補fixtureを使う
- JSONは `json.loads()` で検証する
- CSVはheader列と行数を検証する
- Markdownは主要sectionの存在を検証する
- 期待結果未確定は正常な状態として検証する

---

## 10. 実装タスク分解

### Task 12-01: Test case draft model 定義

成果物:

- `src/unit_test_runner/test_design/test_case_models.py`
- `TestCaseDraftRequest`
- `TestCaseGenerationPolicy`
- `TestCaseDraftReport`
- `TestCaseDraft`
- `TestPrecondition`
- `TestInputAssignment`
- `TestStateSetup`
- `TestStubSetup`
- `TestExecutionStep`
- `ExpectedObservation`
- `TestCoverageLink`
- `CoverageDraftSummary`
- `UnresolvedTestDesignItem`
- `TestCaseDraftWarning`
- JSON変換 helper

完了条件:

- modelを生成できる
- JSON変換できる
- model単体テストが通る

### Task 12-02: Coverage-to-case mapper

成果物:

- `src/unit_test_runner/test_design/coverage_case_mapper.py`
- coverage_type別case_kind変換
- purpose生成
- priority初期値付与

完了条件:

- TCD-001 から TCD-008 が通る

### Task 12-03: Candidate selector

成果物:

- `src/unit_test_runner/test_design/candidate_selector.py`
- coverage link候補選択
- confidence優先
- additional candidate分離
- conflict warning

完了条件:

- TCD-009 / TCD-015 / TCD-016 / TCD-017 が通る

### Task 12-04: Input assignment builder

成果物:

- parameter input assignment生成
- default valid placeholder生成
- pointer / array input handling

完了条件:

- TCD-009 / TCD-010 が通る

### Task 12-05: State setup builder

成果物:

- global / extern setup生成
- file static setup warning
- setup_method_hint付与

完了条件:

- TCD-011 / TCD-012 が通る

### Task 12-06: Stub setup builder

成果物:

- stub return setup生成
- call count observation placeholder
- argument capture placeholder
- stub required warning

完了条件:

- TCD-013 / TCD-014 が通る

### Task 12-07: Expected observation builder

成果物:

- return_value placeholder
- global_value placeholder
- parameter_side_effect placeholder
- coverage_target observation
- expected_result_not_determined warning

完了条件:

- TCD-008 / TCD-018 が通る

### Task 12-08: Test case draft analyzer

成果物:

- `src/unit_test_runner/test_design/test_case_draft_generator.py`
- mapper / selector / builders の統合
- coverage summary生成
- unresolved item生成

完了条件:

- representative fixtureでtest casesが生成される

### Task 12-09: Test case draft writer

成果物:

- `src/unit_test_runner/test_design/test_case_draft_writer.py`
- `reports/test_case_draft_markdown.py`
- `reports/test_case_draft_csv.py`
- JSON / Markdown / CSV出力

完了条件:

- TCD-019 / TCD-020 / TCD-021 が通る

### Task 12-10: generate-test-draft CLI 実装

成果物:

- `generate-test-draft` の実用化
- report個別入力形式対応
- `--format json|md|csv|all`
- `--out` 出力対応

完了条件:

- TCD-022 が通る

### Task 12-11: analyze-function 接続

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
- CLI `analyze-function` の出力更新

完了条件:

- TCD-023 が通る

### Task 12-12: fixture / test 整備

成果物:

- `tests/fixtures/test_case_draft/...`
- `tests/unit/test_coverage_case_mapper.py`
- `tests/unit/test_candidate_selector.py`
- `tests/unit/test_input_assignment_builder.py`
- `tests/unit/test_state_setup_builder.py`
- `tests/unit/test_stub_setup_builder.py`
- `tests/unit/test_expected_observation_builder.py`
- `tests/unit/test_test_case_draft_writer.py`
- `tests/unit/test_generate_test_draft_cli.py`
- `tests/unit/test_analyze_function_partial_test_case_draft.py`

完了条件:

- TCD-001 から TCD-023 が通る

---

## 11. 受け入れ基準

Step 12 は、以下をすべて満たしたら完了とする。

1. coverage itemからテストケース草案を生成できる
2. branch true / false 用の草案を生成できる
3. condition true / false 用の草案を生成できる
4. switch case / default 用の草案を生成できる
5. loop zero / one / many 用の草案を生成できる
6. return path 用の草案を生成できる
7. Step 11 の入力値候補を input assignment に変換できる
8. Step 11 のstate候補を state setup に変換できる
9. Step 11 のstub return候補を stub setup に変換できる
10. Step 09 のstub candidateからcall count / argument capture観測placeholderを生成できる
11. 期待戻り値や期待global値が未確定な場合にplaceholderとwarningを生成できる
12. coverage itemとtest caseをlinkできる
13. coverage未割当項目をunresolved itemとして出力できる
14. 候補過多の場合にadditional_case_candidatesへ分離できる
15. `test_case_draft.json` を生成できる
16. `test_case_draft.md` を生成できる
17. `test_case_draft.csv` を生成できる
18. `generate-test-draft` が明示入力からCSVまたは指定形式を生成できる
19. `analyze-function` が Step 12 時点では test case draft生成まで進み、Step 13 が必要である旨を返せる
20. Step 13 の Stub / Harness Skeleton Generator に渡せるtest case draft modelがある
21. 実行可能Cテストコード生成へ踏み込みすぎていない
22. 期待結果確定へ踏み込みすぎていない

---

## 12. 成果物

Step 12 の成果物は以下とする。

```text
src/
  unit_test_runner/
    test_design/
      __init__.py
      test_case_models.py
      coverage_case_mapper.py
      candidate_selector.py
      input_assignment_builder.py
      state_setup_builder.py
      stub_setup_builder.py
      expected_observation_builder.py
      test_case_draft_generator.py
      test_case_draft_writer.py
    reports/
      test_case_draft_markdown.py
      test_case_draft_csv.py
    cli/
      commands.py

tests/
  fixtures/
    test_case_draft/
      simple_branch/
      switch_cases/
      loop_cases/
      global_state/
      stub_return/
      unresolved_expected/
      too_many_candidates/
  unit/
    test_coverage_case_mapper.py
    test_candidate_selector.py
    test_input_assignment_builder.py
    test_state_setup_builder.py
    test_stub_setup_builder.py
    test_expected_observation_builder.py
    test_test_case_draft_writer.py
    test_generate_test_draft_cli.py
    test_analyze_function_partial_test_case_draft.py
```

既存ファイルの更新:

- `src/unit_test_runner/cli/commands.py`
- `src/unit_test_runner/c_analyzer/boundary_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/coverage_models.py` 必要な場合のみ
- `src/unit_test_runner/c_analyzer/call_models.py` 必要な場合のみ

---

## 13. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| テストケース数の爆発 | coverage itemと値候補の組み合わせが多い | 既定ではcoverage itemごとに代表候補を選び、追加候補は別枠にする |
| 期待結果の誤生成 | ソース解析だけでは仕様上の期待値を断定できない | 期待値はplaceholderとし、review_requiredを必須にする |
| 条件候補の矛盾 | 同じテストに両立しない候補が入る可能性 | conflict warningを出し、無理に統合しない |
| file static setup困難 | 外部から状態を設定できない可能性がある | setup_method_hintとwarningを出し、Step13以降でwrapper検討に回す |
| スタブ未生成 | スタブ設定案はあってもコードがない | `stub_required_but_not_generated` warningを出し、Step13へ渡す |
| CSVの情報不足 | 平坦化で詳細が失われる | 詳細はJSON/Markdownに保持し、CSVはレビュー表として割り切る |
| 設計草案と実行可能テストの混同 | ユーザーがそのまま実行できると誤解する | reportにdraft/review_requiredを明記する |
| Step13責務の侵食 | ハーネスやCコード生成まで進めたくなる | Step12は設計表生成までに限定する |

---

## 14. Step 13 への接続

Step 12 完了後、Step 13 では Stub / Harness Skeleton Generator を実装する。
Step 13 は、Step 09 の stub candidates と Step 12 の test case draft を使い、VC6 / C90 互換のスタブ雛形、テストランナー雛形、テストケース関数雛形を生成する。

想定接続:

```python
test_case_draft = generate_test_case_draft(
    function_signature=function_signature,
    global_access=global_access,
    call_report=call_report,
    coverage_design=coverage_design,
    boundary_candidates=boundary_candidates,
)
harness_skeleton = generate_harness_skeleton(
    function_signature=function_signature,
    call_report=call_report,
    test_case_draft=test_case_draft,
)
```

Step 13 で使う情報:

- target function signature
- parameter assignments
- state setups
- stub setups
- expected observation placeholders
- stub candidates
- call count / argument capture requirements
- review_required flags

Step 12 の責務は、Stub / Harness Skeleton Generator がCコード雛形に変換できるように、テストケース草案を構造化しておくことである。

---

## 15. まとめ

Step 12 は、Step 04 から Step 11 までの解析結果を統合し、関数単位テストの設計表として見える形にするステップである。

このステップにより、対象関数について、どの入力値、状態、スタブ戻り値で、どのcoverage itemを狙うかを `test_case_draft` として整理できる。

ただし、Step 12 は実行可能なテストコードや期待結果を確定する段階ではない。
テストケース草案に責務を絞り、Step 13 の Stub / Harness Skeleton Generator へ安全な入力を渡すことを完了条件とする。

# Test Execution Blocker Report Design

Date: 2026-07-20

## Summary

`run-tests --run` returns exit code `35` when execution is intentionally blocked, but the current user-facing message does not identify the blocking items or lead the user to the corrective action. The underlying reasons are distributed across the execution report, TestSpec, harness report, build-probe report, executable resolution, and run logs.

This design adds a first-class **test execution blocker report**. When and only when the canonical terminal outcome is `blocked`, the Python execution core creates a structured JSON artifact and a human-readable Markdown view containing the direct blockers, their source artifacts, current values where applicable, and deterministic next actions.

The report is stored both with the immutable run history and as a latest-workspace view:

```text
runs/<run_id>/test_execution_blockers.json
runs/<run_id>/test_execution_blockers.md
reports/test_execution_blockers.json
reports/test_execution_blockers.md
```

The VS Code extension recognizes a valid `run-tests` exit-code-35 envelope as an expected blocked domain outcome rather than an opaque CLI failure. When a verified Markdown blocker report exists, it opens that report once for the run and retains a Workflow action named `実行ブロック項目を開く（N件）`.

A later actual run with any non-blocked outcome removes only the latest `reports/test_execution_blockers.*` views and hides the Workflow action. Historical run reports remain unchanged.

## Problem

### Generic exit-code-35 feedback

The current `run-tests` handler returns the same generic message for all terminal outcomes:

```text
Test execution evidence prepared with the reported terminal outcome.
```

For a blocked run, this does not answer:

1. Which exact condition prevented execution?
2. Which test case or TestSpec item is responsible?
3. What is the current unresolved value?
4. Which report contains the source evidence?
5. What should the user do next?

### Blocker details are distributed

The existing execution model already records useful inputs:

- execution warnings and `ExecutionReviewItem` entries;
- build-probe readiness and diagnostics;
- executable resolution;
- canonical TestSpec unresolved items and candidate cases;
- harness placeholders;
- runner case results and logs.

These inputs are not normalized into a direct-cause list. Some entries are background review work rather than causes of the current block. Broad symptoms such as “no executable test cases” can also duplicate several concrete unresolved fields.

### Existing VS Code handling obscures the domain outcome

A non-zero CLI exit is normally shown as a command error. Exit code `35` instead means that the command completed and prepared evidence, but execution was blocked by an expected precondition or review state. The extension must recognize the complete structured envelope, not the numeric exit code alone.

## Goals

- Generate a blocker report for actual `run-tests --run` results whose canonical outcome is exactly `blocked`.
- List only blockers that directly contributed to that run’s blocked outcome.
- Include test-case ID, stable item ID, control name, current value, source artifact, JSON Pointer, and recommended operation where those fields apply.
- Guarantee at least one blocker in every successfully generated blocked report.
- Preserve one immutable blocker report per blocked run.
- Maintain a latest blocker report under `reports/` for simple Workflow navigation.
- Automatically open the verified Markdown report after a blocked run in VS Code.
- Preserve exit code `35` and the distinction between blocked execution and failed tests.
- Remove stale latest blocker views and hide their Workflow action after a later non-blocked actual run.
- Reuse the test-input editor’s field-location and unresolved-value rules instead of introducing a second TestSpec interpretation.
- Keep CLI-only and VS Code-driven runs behaviorally equivalent.

## Non-goals

- Generating blocker reports for `failed`, `inconclusive`, `timed_out`, `cancelled`, `passed`, or `planned` outcomes.
- Treating assertion failures as execution blockers.
- Automatically changing TestSpec, confirming review items, regenerating a harness, building, or rerunning tests.
- Implementing the broader `review-test-cases` / `apply-test-review` workflow described in the earlier blocked-review design.
- Replacing the existing test-input editor. It remains the primary correction path for unresolved executable values.
- Adding suite-level blocker aggregation in this increment.
- Copying complete product source files or unrestricted logs into the blocker artifact.

## Approved product decisions

1. The Python execution core generates the report; VS Code does not infer blocker causes.
2. VS Code automatically opens the Markdown report immediately after a valid blocked run when a verified report is available.
3. The report contains direct blockers plus cause source, current value, and recommended action.
4. Both immutable run-history files and latest `reports/` files are written.
5. Reports are generated only for the exact `blocked` outcome.
6. A later actual non-blocked run removes the latest files and hides the Workflow action.
7. Historical reports under `runs/<run_id>/` are never removed by this lifecycle.

## User experience

### Blocked run

After `run-tests --run` returns exit code `35`, VS Code opens:

```text
reports/test_execution_blockers.md
```

or, if latest-view synchronization failed, the verified run-history Markdown file.

The report begins with an actionable summary:

```text
# テスト実行ブロック項目

実行状態: BLOCKED
実行ID: run-20260720T...
ブロック項目: 3件

## 最初に行う操作

「未確定項目を入力」を開き、2件の期待値を確定してください。
```

The Workflow panel retains:

```text
実行ブロック項目を開く（3件）
```

When a deterministic primary operation exists, Workflow also exposes the mapped operation, such as `未確定項目を入力`, `ビルド結果を開く`, or `テストハーネスを生成`.

### Example item

```text
## TC_BOUNDARY_003

### 期待値: return_value

- ブロッカーID: `BLK-001`
- 種別: 未確定の期待値
- 現在値: `TBD_EXPECTED_VALUE`
- 原因元: `reports/test_spec.json`
- 位置: `/additional_case_candidates/2/expected_observations/0/expected_expression`
- 推奨操作: 未確定項目を入力
- その後:
  1. 項目を確認済みにする
  2. テストハーネスを再生成する
  3. ビルドを実行する
  4. テストを再実行する
```

### Non-blocked later run

When a later `run-tests --run` produces any outcome other than `blocked`:

- `reports/test_execution_blockers.json` is removed;
- `reports/test_execution_blockers.md` is removed;
- the Workflow blocker action and cached count are cleared;
- earlier `runs/<run_id>/test_execution_blockers.*` files remain historical evidence.

`run-tests --plan` neither generates nor removes blocker reports because it is not an actual terminal execution result.

## Architecture

### Python components

Add a focused blocker-report package under `execution/`:

```text
src/unit_test_runner/execution/
  blocker_models.py
  blocker_analyzer.py
  blocker_report_writer.py
```

#### `blocker_models.py`

Defines models for recommended actions, individual blockers, the report summary, the complete payload, and non-fatal publication diagnostics. These models do not access the filesystem.

#### `blocker_analyzer.py`

Consumes:

- `TestExecutionReport`;
- canonical TestSpec;
- the test-input form’s read-only field-location model;
- harness report;
- build-probe report;
- build-workspace report;
- current run logs when the runner itself reports blocked.

It returns a normalized in-memory report without modifying source artifacts.

#### `blocker_report_writer.py`

Responsibilities:

- validate workspace containment;
- render canonical JSON and Markdown;
- atomically publish immutable run files;
- synchronize latest `reports/` files only after both history files exist;
- remove latest files after a non-blocked actual run;
- return produced-artifact metadata and non-fatal diagnostics.

The writer does not decide why a run is blocked.

### Existing components changed

#### `RunPaths`

Add:

```python
blocker_report_json: Path
blocker_report_markdown: Path
```

resolved as:

```text
runs/<run_id>/test_execution_blockers.json
runs/<run_id>/test_execution_blockers.md
```

#### Execution orchestration

The execution flow constructs the final `TestExecutionReport`, publishes the normal immutable run files, then publishes or clears blocker views according to the terminal outcome.

#### CLI

The `run-tests` handler adds blocker details and artifacts for blocked runs and uses an action-oriented message while retaining exit code `35`.

#### VS Code extension

The adapter parses valid blocked envelopes, opens only verified paths, caches current blocker state, and renders Workflow actions. It does not derive blocker causes.

## Artifact contract

### Artifact identity

The immutable run JSON is a registered contract artifact:

```json
{
  "artifact_kind": "test_execution_blocker_report",
  "schema_version": "1.0.0"
}
```

The schema is packaged with wheels, the bundled executable, and distribution builds through the existing contract registry.

### Conceptual payload

```json
{
  "artifact_kind": "test_execution_blocker_report",
  "schema_version": "1.0.0",
  "producer": {
    "name": "unit-test-runner",
    "version": "0.1.0",
    "commit": "<commit>"
  },
  "subject": {
    "function_id": "fn_...",
    "source_path": "src/large_module_06996.c",
    "source_sha256": "<sha256>"
  },
  "data": {
    "run_id": "run-20260720T...",
    "execution_status": "blocked",
    "execution_report": {
      "path": "runs/run-.../test_execution_report.json",
      "sha256": "<sha256>"
    },
    "blocker_count": 3,
    "primary_action": {
      "code": "open_test_input_editor",
      "label": "未確定項目を入力",
      "affected_count": 2
    },
    "blockers": []
  },
  "extensions": {}
}
```

### Individual blocker

```json
{
  "blocker_id": "BLK-001",
  "code": "unresolved_expected_value",
  "category": "test_input",
  "severity": "error",
  "case_id": "TC_BOUNDARY_003",
  "item_id": "item-<stable-id>",
  "control_name": "expected_expression",
  "summary": "期待値が未確定です。",
  "current_value": "TBD_EXPECTED_VALUE",
  "source_artifact": "reports/test_spec.json",
  "source_pointer": "/additional_case_candidates/2/expected_observations/0/expected_expression",
  "recommended_action": {
    "code": "open_test_input_editor",
    "label": "未確定項目を入力"
  },
  "next_steps": [
    "値を入力する",
    "項目を確認済みにする",
    "テストハーネスを再生成する",
    "ビルドを実行する",
    "テストを再実行する"
  ],
  "truncated": false
}
```

Fields that do not apply are omitted. A missing executable blocker, for example, has no `case_id`, `item_id`, or `current_value`.

### Recommended action codes

| Code | VS Code operation |
| --- | --- |
| `open_test_input_editor` | `unitTestRunner.openTestInputEditor` |
| `open_build_probe_report` | open current build-probe Markdown |
| `generate_harness` | `unitTestRunner.generateHarnessSkeleton` |
| `run_build_probe` | `unitTestRunner.runBuildProbe` |
| `choose_or_build_executable` | open build guidance or executable configuration |
| `open_execution_log` | open the current run’s combined execution log |
| `open_execution_report` | open the current run’s execution report |

The report stores codes and labels. Routing never depends on localized text.

## Direct blocker analysis

### General rule

A blocker is included only when it directly explains why the current run’s terminal outcome is `blocked`. Background review work, informational warnings, and formal review items that did not stop the run are excluded.

### Priority order

Blockers are ordered by prerequisite sequence:

1. build-probe readiness;
2. executable availability;
3. harness readiness;
4. executable-case availability;
5. unresolved or unconfirmed executable TestSpec fields;
6. runner-reported blocked reasons.

The first blocker’s recommended operation becomes the report-level `primary_action`, with aggregation when several blockers share that operation.

### Build probe not successful

When execution is blocked because the build probe is not `succeeded`:

- include each structured error diagnostic from `build_probe_report.json`;
- include code, message, relevant file, line, and source pointer where available;
- source the blocker from the build-probe report;
- recommend `open_build_probe_report` or `run_build_probe` according to current state.

When no structured errors exist, emit one generic `build_probe_not_successful` blocker. The broad precondition warning is not counted separately when concrete diagnostics exist.

### Executable missing

When the resolved executable does not exist:

- include the attempted executable path as a workspace-relative value when safe;
- include build-probe status and resolver warning;
- recommend `choose_or_build_executable`.

### No executable test cases

When there are no executable cases:

1. query the canonical test-input form model;
2. select only execution-blocking items;
3. emit concrete blockers for unresolved or unconfirmed executable fields;
4. emit a generic `no_executable_test_cases` blocker only when no concrete direct cause can be identified.

This avoids counting both the broad symptom and each concrete field.

### Unresolved executable values

For a blocking form item:

- each unresolved required control becomes one leaf-level blocker;
- unresolved means empty or beginning with `TBD`, `TODO`, `UNKNOWN`, or `UNRESOLVED`, using the same normalization as the input editor;
- include stable item ID, control name, current value, case ID, TestSpec path, and JSON Pointer.

### Confirmation-only blockers

A parent item may contain concrete required values but remain unconfirmed, preventing candidate promotion. Emit one parent-level `unconfirmed_test_input` blocker rather than duplicating every concrete control. Its source pointer targets the parent object and its bounded current-value summary lists the relevant controls.

### Placeholder execution prohibited

When placeholders are explicitly disallowed, prefer concrete TestSpec field blockers. Emit a generic `placeholder_tests_not_allowed` blocker only for a harness placeholder that cannot be mapped to a current canonical field.

### Harness missing or stale

When execution evidence indicates that the harness is absent, stale, or inconsistent with current TestSpec, emit a harness blocker and recommend `generate_harness`. The report does not regenerate it.

### Runner-reported blocked outcome

When the executable starts but the runner reports blocked:

- map structured blocked case results when available;
- include related case IDs and runner messages;
- include a bounded log excerpt only when needed to explain an unstructured block;
- link to the full combined log;
- recommend `open_execution_log`.

If no structured case reason exists, emit one generic `runner_reported_blocked` blocker.

### Final fallback guarantee

If the terminal outcome is `blocked` but every specialized analyzer yields no blocker, emit exactly one:

```text
code: execution_blocked_unknown
category: execution
source_artifact: runs/<run_id>/test_execution_report.json
recommended_action: open_execution_report
```

A successfully generated blocked report therefore never has `blocker_count == 0`.

## Reuse of TestSpec field location

The blocker analyzer must not implement a second TestSpec traversal or placeholder interpretation. Expose a narrow read-only API from the test-input subsystem, conceptually:

```python
locate_editable_test_spec_fields(spec) -> tuple[LocatedEditableField, ...]
```

Each description includes stable parent item ID, case ID, current collection, item kind, parent and leaf JSON Pointers, control names, current values, confirmation status, execution-blocking status, and editability. The API performs no writes and does not change review state.

## Deduplication and stable ordering

### Deduplication key

```text
code + case_id + item_id + control_name + source_artifact + source_pointer
```

Missing optional values normalize to empty strings.

### Stable sort

Within fixed category priority, sort by:

```text
case_id
item_id
control_name
source_pointer
code
```

Assign `BLK-001`, `BLK-002`, and so on after sorting. IDs are stable for the same normalized set but scoped to one report.

## Size and path safety

- `current_value`: maximum 2,048 Unicode code points.
- diagnostic message: maximum 4,096 code points.
- runner log excerpt: maximum 8,192 code points.
- truncated content sets `truncated: true`.
- full source artifact or log paths remain available.
- navigable source, log, and executable paths must be workspace-relative.
- absolute paths outside the workspace are not exposed as openable references.
- symlinks and junctions follow existing containment checks.
- Markdown escapes HTML-significant characters, table separators, and backticks.
- no source file or complete log is copied into the report.

## Publication lifecycle

### Blocked actual run

1. Construct final `TestExecutionReport` in memory.
2. Write normal immutable execution report, result files, and logs.
3. Build and validate blocker report in memory.
4. Atomically write run-history blocker JSON.
5. Atomically write run-history blocker Markdown.
6. After both history files exist, atomically synchronize latest JSON and Markdown under `reports/`.
7. Write `reports/latest_run.json` with execution-report and available blocker-report references.
8. Prepare remaining evidence artifacts.

The run-history JSON is canonical. Markdown and latest copies are views.

### Non-blocked actual run

After the new immutable execution report is safely written:

1. remove latest blocker JSON if it exists;
2. remove latest blocker Markdown if it exists;
3. write `latest_run.json` without blocker reference;
4. leave all prior run-history directories unchanged.

### Planned run

`run-tests --plan` does not create a run-history directory and does not generate, synchronize, or delete blocker reports.

## `latest_run.json`

Add an optional field:

```json
{
  "run_id": "run-...",
  "execution_report": {
    "artifact_kind": "test_execution_report",
    "path": "runs/run-.../test_execution_report.json",
    "sha256": "<sha256>"
  },
  "blocker_report": {
    "artifact_kind": "test_execution_blocker_report",
    "path": "runs/run-.../test_execution_blockers.json",
    "markdown_path": "runs/run-.../test_execution_blockers.md",
    "sha256": "<sha256>"
  },
  "updated_at": "2026-07-20T...Z"
}
```

Omit `blocker_report` for non-blocked runs and when blocker publication failed. Existing consumers continue to accept pointers without it.

## Failure semantics

The blocker report is explanatory evidence. Publication failure must not replace the true test outcome.

### Run-history blocker write failure

- retain `blocked` and exit code `35`;
- add structured diagnostic `blocker_report_write_failed`;
- remove or invalidate latest blocker views so older data is not presented as current;
- write `latest_run.json` without blocker reference;
- return normal execution and evidence artifacts.

### Latest synchronization failure

When history files are valid but latest synchronization fails:

- retain exit code `35`;
- return run-history paths as produced artifacts;
- add a warning diagnostic;
- VS Code opens verified run-history Markdown instead of an old latest path.

### Markdown-only failure

When canonical JSON exists but Markdown fails:

- retain JSON and exit code `35`;
- expose JSON or execution report as fallback;
- never claim Markdown exists.

### Latest-file deletion failure

After a non-blocked run:

- retain the actual terminal outcome;
- omit blocker data from `latest_run.json`;
- clear VS Code blocker cache and action;
- add a warning diagnostic;
- never treat a leftover file as current.

## CLI behavior

### JSON envelope

A blocked-domain result retains:

```text
exit_code: 35
outcome: blocked
status: blocked
```

and includes the in-memory count and primary action even if view publication partially failed:

```json
{
  "blockers": {
    "count": 3,
    "primary_action": "open_test_input_editor",
    "run_json": "runs/run-.../test_execution_blockers.json",
    "run_markdown": "runs/run-.../test_execution_blockers.md",
    "latest_json": "reports/test_execution_blockers.json",
    "latest_markdown": "reports/test_execution_blockers.md"
  }
}
```

Only successfully written paths are present.

### Message

```text
Test execution was blocked by 3 items. See reports/test_execution_blockers.md.
```

Human output presents the first operation and available report path. Blockers are not placed in CLI `errors` merely because the domain outcome is blocked. Publication failures are diagnostics; actual command failures retain the error channel.

### Produced artifacts

Blocked runs register successfully written immutable JSON, immutable Markdown, latest views, and all existing execution/evidence artifacts. Other outcomes do not register blocker artifacts.

## VS Code integration

### Structured blocked classification

The extension treats a non-zero process result as a handled blocked domain outcome when all of the following hold:

```text
command == run-tests
execution was requested with --run
exitCode == 35
JSON envelope parses successfully
JSON command == run-tests
JSON outcome == blocked
```

An exit code `35` with missing or invalid JSON remains a normal CLI error. Numeric exit code alone is never sufficient.

Report-path verification is a separate gate for automatic opening. A valid blocked envelope with a report-publication diagnostic remains a handled blocked outcome, but VS Code displays the diagnostic and does not open an unverified or missing report.

### Automatic opening

On a valid blocked result with at least one blocker and a verified Markdown path:

1. record run outcome and report metadata;
2. validate latest Markdown, falling back to run-history Markdown;
3. open Markdown once;
4. cache run ID, blocker count, hashes, and primary action;
5. refresh Workflow.

The extension stores the last auto-opened blocker run ID so refreshes and restoration do not reopen it. Closing the tab does not remove the Workflow action.

### Workflow state

Conceptually:

```typescript
{
  status: 'blocked',
  workspace: string,
  runId: string,
  count: number,
  primaryAction: string,
  reportJson?: string,
  reportMarkdown?: string,
  reportSha256?: string,
  updatedAt: string
}
```

Paths and hashes are optional because report publication can fail without changing the blocked outcome. A non-blocked actual run clears this state.

### Workflow actions

Both simple and detailed views display `実行ブロック項目を開く（N件）` when verified report metadata is available. Where supported, an adjacent primary-operation button is mapped from the stable action code. Labels never drive routing.

When a blocked outcome has no published view, Workflow shows the blocked status and publication diagnostic but does not render an open-report button.

### Activation-time restoration

Restore blocker state only when:

1. `reports/latest_run.json` is valid;
2. its execution report exists and reports `blocked`;
3. its optional blocker reference uses the same run ID;
4. blocker JSON validates against schema;
5. blocker JSON references the same execution report;
6. recorded SHA-256 matches blocker JSON;
7. Markdown is workspace-contained and exists.

A stray `reports/test_execution_blockers.md` alone never restores the action.

## Compatibility

- Exit code `35` is unchanged.
- Existing execution-report fields are unchanged.
- `latest_run.json.blocker_report` is optional.
- Existing runs without blocker reports remain readable.
- Consumers ignoring new CLI detail fields continue to work.
- The new artifact kind and schema are additive.
- `run-tests --plan` behavior remains unchanged.

## Testing strategy

### Python analyzer tests

- build-probe diagnostics become individual blockers;
- non-successful probe without diagnostics becomes one generic blocker;
- executable-not-found includes attempted path and build state;
- no executable cases expands to concrete blocking TestSpec fields;
- broad no-case and placeholder messages are not double-counted when concrete causes exist;
- empty, `TBD*`, `TODO*`, `UNKNOWN*`, and `UNRESOLVED*` use shared input-form rules;
- each unresolved required leaf becomes one blocker;
- a concrete but unconfirmed parent becomes one confirmation-only blocker;
- unrelated formal review items are excluded;
- runner structured blockers and fallback log explanations are normalized;
- an otherwise unexplained blocked result produces `execution_blocked_unknown`;
- duplicate removal, sorting, IDs, primary action, and truncation are deterministic.

### Publication tests

- blocked run writes all four files;
- run-history files are never overwritten;
- JSON passes contract validation;
- Markdown safely escapes dynamic content;
- `latest_run.json` contains a valid optional reference;
- a later non-blocked run deletes only latest files;
- historical files remain;
- `--plan` changes nothing;
- run-history failure retains exit `35` and removes stale latest views;
- latest synchronization failure returns history paths;
- Markdown failure preserves JSON and true outcome;
- workspace escapes, symlinks, and junction escapes are rejected.

### CLI tests

- blocked result retains exit `35`;
- message includes count and available path;
- count and primary action remain present during publication failure;
- blocker artifacts register only when written;
- non-blocked outcomes expose no blocker artifacts;
- publication warnings do not convert outcome to failed or internal error.

### VS Code tests

- valid blocked envelope is handled even when publication failed;
- valid blocked envelope with verified Markdown auto-opens once;
- malformed exit-code-35 output remains a CLI error;
- simple and detailed Workflow views show the same count;
- open-report action validates containment;
- stable action codes invoke correct commands;
- later non-blocked run clears action;
- other outcomes do not auto-open;
- activation restores only matching run IDs, hashes, schema, and paths;
- stale, modified, or external paths are not opened;
- user can reopen a previously auto-opened report from Workflow.

### Integration tests

#### Blocked to resolved

```text
create TestSpec with blocking unresolved values
→ generate prerequisites
→ run-tests --run
→ assert exit 35 and four blocker files
→ assert concrete TestSpec field details
→ resolve and confirm through canonical input-form APIs
→ regenerate harness and build
→ run-tests --run
→ assert non-blocked outcome
→ assert latest blocker files removed
→ assert historical files retained
```

#### Build-precondition block

```text
prepare non-successful build-probe report with diagnostics
→ run-tests --run
→ assert build diagnostics in blocker report
→ assert build-related primary action
→ assert unrelated TestSpec review items excluded
```

#### Distribution contract

- wheel contains blocker schema;
- bundled executable emits the artifact;
- packaged VSIX contains blocked-result handling and Workflow action;
- Windows distribution smoke verifies exit `35`, report creation, and safe auto-open metadata.

## Acceptance criteria

1. Every successfully generated blocked report contains at least one direct blocker.
2. A blocked actual run creates immutable JSON and Markdown under its run directory.
3. Latest JSON and Markdown views are synchronized under `reports/`.
4. Unrelated review work is excluded.
5. Concrete TestSpec blockers include case ID, stable item ID, control name, current value, source artifact, and JSON Pointer.
6. The report provides deterministic primary operation and ordered next steps.
7. Exit code `35` and blocked semantics are unchanged.
8. VS Code handles valid blocked envelopes even if report publication fails.
9. VS Code automatically opens a verified Markdown report once after the run.
10. Both Workflow modes provide `実行ブロック項目を開く（N件）` while verified current report metadata exists.
11. A later non-blocked actual run removes latest views and UI state without deleting history.
12. `run-tests --plan` does not change blocker state.
13. Publication failures do not overwrite the true outcome or expose an older report as current.
14. CLI-only and VS Code-driven runs produce the same canonical blocker artifacts.
15. Full Python, VS Code, Extension Host, fixture smoke, package-contract, source-integrity, and Windows distribution checks pass.

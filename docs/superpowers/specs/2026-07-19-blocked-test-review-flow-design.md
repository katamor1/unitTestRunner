# Blocked Test Review Flow Design

Date: 2026-07-19

## Summary

`run-tests --run` currently returns exit code `35` when test execution is blocked, but its human-facing message only says that execution evidence was prepared. The user is not told why execution was blocked, what must be reviewed, or which command or UI action should be used next.

This design introduces a guided review flow that connects a blocked test run to an explicit, safe next action:

1. explain the blocker and summarize unresolved work;
2. generate an editable test-review plan without changing the canonical TestSpec;
3. validate and apply reviewed candidate cases with exact revision and fingerprint guards;
4. regenerate the harness;
5. run execution preflight and show either `Build tests` or `Run tests` as the next action;
6. expose the same flow in the VS Code extension through a dedicated review panel.

The design does not auto-approve generated expectations and does not execute tests merely because a review was applied.

## Problem

The current workflow has three related usability and capability gaps.

### 1. Exit code 35 does not explain the next action

`EXIT_TESTS_BLOCKED = 35` is a deliberate terminal outcome, but the command message is generic and identical across terminal outcomes. Human output therefore emphasizes evidence preparation rather than the action needed to unblock execution.

### 2. Diagnostic details are hidden from normal human output

The execution report can contain warnings such as `no_executable_test_cases`, placeholder-related review items, and build precondition failures. These details are available in JSON and generated reports, but ordinary CLI output does not summarize them or convert them into a prioritized next action.

### 3. There is no complete candidate-to-executable transition

The current tool can:

- generate `additional_case_candidates`;
- patch fields inside an existing case;
- record review decisions;
- generate a harness from executable `test_cases`.

It cannot complete the user workflow of reviewing a candidate, supplying executable values, promoting it to `test_cases`, persisting the review authority, regenerating the harness, and reporting the next runnable action.

## Goals

- Make every blocked `run-tests` result answer three questions directly:
  - What happened?
  - Why did it happen?
  - What is the next operation?
- Provide a review artifact that groups each candidate's inputs, state, stubs, expected observations, and coverage intent in one place.
- Provide an explicit, guarded operation that promotes reviewed candidates to executable cases.
- Preserve human review authority. No generated expected value is silently approved.
- Keep test execution explicit. Applying a review never starts the test executable.
- Keep existing exit-code behavior and existing JSON fields backward compatible.
- Reuse existing TestSpec, review-decision, harness-generation, build-probe, and execution-preflight components where possible.
- Provide equivalent CLI and VS Code workflows.

## Non-goals

- Inferring or auto-approving expected return values, global values, or stub behavior.
- Replacing the existing review-decision ledger.
- Automatically running a compiler or test executable after review application.
- Redesigning all dossier review screens.
- Treating exit code 35 as a test failure.
- Allowing placeholder execution as the normal resolution path.

## User experience

### Blocked CLI output

When `run-tests --run` produces `RunOutcome.BLOCKED`, human output changes from the generic evidence message to an action-oriented summary.

```text
テストは実行されませんでした

状態:
  BLOCKED（終了コード 35）

理由:
  実行可能なテストケースが 0 件です。

確認が必要な項目:
  テスト候補       10件
  期待戻り値       11件
  グローバル期待値 11件

次に行う操作:
  unit-test-runner review-test-cases --workspace "C:\...\workspace"

詳細:
  reports\unresolved_items.md
```

The first next action is selected deterministically from the blocker set. The command does not display `run-tests --run` as the primary next action when rerunning would reproduce the same block.

### Blocker-to-action priority

The explainer chooses one primary action and may include secondary links.

| Blocker | Primary next action |
| --- | --- |
| No executable cases or unresolved case values | `review-test-cases` |
| Review plan is stale or incomplete | reopen or regenerate the review plan |
| Harness is missing or stale | regenerate the harness |
| Build artifact is missing or stale | `build-probe --workspace ... --run` |
| Explicit executable is missing | choose or rebuild the executable |
| Environment/toolchain is missing | open build diagnostics or environment guidance |
| All preconditions are ready | `run-tests --workspace ... --run` |

When multiple blockers exist, the earliest prerequisite wins. Secondary blockers remain visible under `その後に必要な操作`.

## New CLI commands

### `review-test-cases`

```powershell
unit-test-runner review-test-cases `
  --workspace $workspace
```

This is a read-only planning operation with respect to canonical TestSpec and review decisions. It writes review views:

```text
reports/test_review_plan.json
reports/test_review_plan.md
```

The command returns exit code `0` when the plan is generated successfully, even when the reviewed workspace is not execution-ready. Its domain outcome is `planned` rather than `passed` to avoid implying that tests are green.

Supported options:

```text
--workspace <path>            required
--out <path>                  optional alternate output directory
--case-id <id>                repeatable candidate filter
--include-executable          include already executable cases for comparison
```

The initial implementation does not provide a bulk auto-approval flag.

### `apply-test-review`

```powershell
unit-test-runner apply-test-review `
  --workspace $workspace `
  --review "$workspace\reports\test_review_plan.json"
```

This command validates exact guards, applies the candidate dispositions and explicit review decisions in the plan, promotes complete adopted candidates whose blocking review items are resolved, regenerates the harness, and runs execution preflight. It does not run a compiler or test executable.

Successful application writes operation views:

```text
reports/test_review_apply_report.json
reports/test_review_apply_report.md
```

Supported options:

```text
--workspace <path>            required
--review <path>               required
--expected-spec-revision <n>  optional command-line guard; must match the plan when supplied
```

The command rejects a plan that does not contain exact guards. There is no force, overwrite-local-edits, or ignore-staleness option.

## Test review plan artifact

### Artifact identity

The canonical JSON review plan uses:

```json
{
  "artifact_kind": "test_review_plan",
  "schema_version": "1.0.0"
}
```

A schema is registered with the existing contract registry and packaged in wheels and the executable distribution.

### Immutable guards

Each plan records:

- workspace-relative canonical TestSpec path;
- `spec_id`;
- TestSpec revision;
- TestSpec SHA-256;
- function identity;
- source path and source SHA-256;
- review snapshot fingerprint;
- producer version and commit;
- generation timestamp.

Each case records a stable case fingerprint computed from its identity, executable fields, coverage links, candidate links, and referenced review items.

### Editable case decisions

Each candidate entry has this conceptual shape:

```json
{
  "case_id": "TC_UtrLarge_Module_06996_003",
  "case_fingerprint": "<sha256>",
  "disposition": "adopt",
  "disposition_rationale": "Selected to cover the positive multiple-of-17 path",
  "title": "...",
  "input_assignments": [],
  "state_setups": [],
  "stub_setups": [],
  "expected_observations": [],
  "coverage_links": [],
  "review_decisions": [
    {
      "review_id": "review-...",
      "resolution": "approved",
      "reviewer": "reviewer01",
      "rationale": "Validated against the function behavior"
    }
  ]
}
```

Allowed dispositions are:

- `adopt`: validate executable completeness and move the case to `test_cases`; every blocking review item for the case must be resolved as `approved` or validly `waived`;
- `defer`: keep the case in `additional_case_candidates` without closing its review work;
- `reject`: keep the case in `additional_case_candidates` and require a non-empty `disposition_rationale` explaining why it is not being adopted.

Candidate disposition and review resolution remain separate concepts. The applier never infers or rewrites a review resolution from `adopt`, `defer`, or `reject`. A rejected candidate may have `changes_requested`, `waived`, or still-open review items according to the reviewer’s explicit entries and the existing ledger rules.

### Markdown view

The Markdown view groups all information needed to make one decision:

```text
ケース: TC_UtrLarge_Module_06996_003
採用: adopt / defer / reject
理由: Selected to cover the positive multiple-of-17 path

入力:
  seed = 17

事前状態:
  g_system_tick = 100

スタブ:
  UtrLarge_Module_06997
  戻り値 = 5
  期待呼出回数 = 1
  期待引数 = 16

期待結果:
  戻り値 = 55
  g_system_tick = 100

対象カバレッジ:
  seed > 0
  seed % 17 == 0
  スタブ呼出経路
```

The Markdown file is a view, not an accepted apply input. `apply-test-review` consumes the validated JSON plan only.

## Validation rules

A case with disposition `adopt` must satisfy all of the following before any canonical file is changed:

- the case exists exactly once in the current `additional_case_candidates`;
- its case fingerprint matches the current candidate;
- its case ID is not already present in `test_cases`;
- each input target has at most one assignment;
- each state target has at most one setup value for the same setup phase;
- each stub has at most one return-value setup for the same call mode;
- all required parameters have executable values;
- no executable field is empty or starts with `TBD`, `TODO`, `UNKNOWN`, or `UNRESOLVED`;
- expected observations required by the case contain concrete expressions;
- stub call-count and captured-argument expectations are concrete when the case asserts them;
- coverage links reference current coverage items;
- candidate links reference current candidate identities;
- every blocking review item associated with the case is present, current, and resolved as `approved` or validly `waived`;
- every `approved` or `waived` decision satisfies the existing review-ledger rules;
- every `reject` disposition includes a non-empty `disposition_rationale`;
- the complete updated TestSpec passes current-context contract validation.

Validation errors identify the case ID and JSON path, for example:

```text
レビュー内容を適用できません。

TC_003:
  - /stub_setups/0/expected_arguments/0 が未入力です。

TC_004:
  - /expected_observations/1/expected_expression が未確定です。
```

## Components

### `BlockedReasonExplainer`

Inputs:

- `TestExecutionReport`;
- execution warnings and unresolved review items;
- current TestSpec summary;
- harness and build readiness.

Outputs:

- user-facing status title;
- primary reason;
- categorized blocker counts;
- one primary `NextAction`;
- zero or more secondary actions;
- report links.

The output is used by both CLI rendering and VS Code notifications. Reason codes, not localized text, drive the action selection.

### `TestReviewPlanBuilder`

Responsibilities:

- load current TestSpec and review snapshot in strict mode;
- select candidate cases;
- calculate exact guards and case fingerprints;
- materialize JSON and Markdown views;
- avoid modifying TestSpec or the review ledger.

### `TestReviewValidator`

Responsibilities:

- validate the `test_review_plan` contract;
- verify workspace containment and exact guards;
- validate dispositions, executable values, review decisions, and references;
- construct an in-memory updated TestSpec and review-decision set;
- return all case-level validation errors in one response where safe.

### `TestReviewTransaction`

Responsibilities:

- acquire canonical locks in a fixed order:
  1. TestSpec repository lock;
  2. review-decision repository lock;
  3. generated-harness workspace lock;
- re-read TestSpec and review snapshots after locks are held;
- compare all revision, SHA, and fingerprint guards;
- verify existing harness outputs are tool-owned and match their last published hashes before replacing them;
- reject locally modified or unprovenanced harness files instead of overwriting them;
- render and validate all target bytes in a staging directory;
- commit canonical TestSpec and review ledger with atomic replacement;
- regenerate harness outputs from the committed TestSpec;
- write an operation record containing before/after hashes and resulting artifact references;
- restore exact previous canonical bytes if a commit-stage operation fails before completion;
- fail closed and preserve a recovery record if rollback itself fails.

Lock order is global and must be shared by future multi-artifact operations to prevent deadlocks.

### `ExecutionReadinessAdvisor`

After review application, this component performs the same checks as `run-tests --plan` without executing or publishing run/evidence artifacts. It returns one of:

- `review_incomplete`;
- `harness_blocked`;
- `build_required`;
- `executable_required`;
- `ready_to_run`.

The advisor produces the next action displayed by CLI and VS Code.

### VS Code `Test Review Panel`

The extension remains a thin adapter. It invokes CLI commands and renders returned structured data; it does not implement TestSpec mutation or review authority itself.

The panel supports:

- candidate navigation;
- adopt/defer/reject selection;
- editing concrete input, state, stub, and expected values;
- entering disposition rationale, reviewer, and review rationale;
- inline validation;
- opening related source, coverage, and unresolved-item reports;
- applying the review;
- showing `Build tests` or `Run tests` after preflight.

## Data flow

```text
run-tests --run
  -> TestExecutionReport(BLOCKED)
  -> BlockedReasonExplainer
  -> human output / JSON next_actions / VS Code notification

review-test-cases
  -> strict TestSpec + review snapshot
  -> TestReviewPlanBuilder
  -> test_review_plan.json + test_review_plan.md

apply-test-review
  -> strict plan validation
  -> TestReviewValidator
  -> TestReviewTransaction
       -> updated TestSpec
       -> updated review_decisions
       -> regenerated harness
       -> operation record
  -> ExecutionReadinessAdvisor
  -> Build tests OR Run tests
```

## CLI result contract additions

Existing fields remain unchanged. The following are additive under CLI result `details`:

```json
{
  "blockers": {
    "primary_code": "no_executable_test_cases",
    "counts": {
      "candidate_cases": 10,
      "expected_return": 11,
      "expected_global": 11
    }
  },
  "next_actions": [
    {
      "id": "review_test_cases",
      "priority": "primary",
      "label": "テストケースを確認",
      "command": [
        "unit-test-runner",
        "review-test-cases",
        "--workspace",
        "C:\\...\\workspace"
      ],
      "artifact_path": "reports/test_review_plan.json"
    }
  ]
}
```

Commands are represented as argument arrays in JSON. Human renderers quote them for the current platform. The JSON contract does not expose shell-concatenated strings as the authoritative representation.

## Human-output rules

- For nonzero outcomes, lead with the domain state and user impact, not artifact production.
- Display `BLOCKED` as “not executed,” never as “failed.”
- Show exactly one primary next action.
- Do not suggest rerunning an operation when no prerequisite changed.
- Display report paths relative to the workspace where possible.
- Keep evidence artifact paths available under a secondary `生成された証跡` section.
- Preserve `--json` as machine-readable output without mixing human text into stdout.
- Preserve `--quiet`, but never suppress the primary blocker and next action for a nonzero terminal outcome.

## VS Code behavior

When the CLI exits with code `35`, the extension reads the structured blocker and action data.

Initial notification:

```text
テストは実行されませんでした。
実行可能なテストケースがありません。

[テストケースを確認] [未解決項目を開く]
```

The extension must not present `再実行` as the primary action for an unchanged blocker.

After applying a review:

```text
テストケースの確認内容を適用しました。
4件のテストケースが実行可能です。

[テストをビルド]
```

or, when the executable is current:

```text
テスト実行の準備ができました。

[テストを実行] [生成されたテストを開く]
```

## Derived-artifact freshness

Promoting a case changes the TestSpec and therefore invalidates derived harness, build, and execution artifacts.

`apply-test-review` must:

1. regenerate the harness from the new TestSpec;
2. publish fresh harness hashes and reports;
3. mark prior build-probe and execution pointers stale through existing provenance checks rather than deleting historical runs;
4. run readiness preflight;
5. recommend `build-probe --workspace ... --run` when the current executable no longer matches the generated inputs;
6. recommend `run-tests --workspace ... --run` only when build and executable provenance are current.

Historical run and evidence directories remain immutable.

## Security and safety

- All input and output paths must remain inside the authorized workspace or explicitly authorized output root.
- Existing symlink, reparse-point, Windows path-alias, and physical-containment checks apply to review-plan and transaction paths.
- Review plans are untrusted input when reapplied, even if generated by the same tool.
- The applier accepts JSON only and validates it before traversing user-controlled paths or values.
- Exact revision, SHA-256, source identity, review fingerprint, and case fingerprints are mandatory.
- There is no `--force`, `--overwrite-local-edits`, `--ignore-sha`, or stale-plan override.
- Command arguments in JSON are arrays to avoid shell injection through display strings.
- The transaction never modifies product source files.
- Applying a review never launches a compiler or test executable.

## Error handling

### Stale plan

No files are changed. The user sees:

```text
レビュー計画が現在のテスト仕様と一致しません。

現在のrevision: 4
計画のrevision: 3

次に行う操作:
  unit-test-runner review-test-cases --workspace "..."
```

### Incomplete adopted case

No files are changed. All safe-to-report case validation errors are returned together.

### Concurrent writer

The command fails with a revision/fingerprint conflict. It does not retry by silently rebasing user decisions.

### Locally modified harness

No canonical files are changed. The command identifies each generated path whose current hash differs from the last published hash and asks the user to preserve or revert those edits before applying the review.

### Harness regeneration failure

The canonical transaction is rolled back when failure occurs inside the commit window. If rollback cannot be completed, the command returns an internal error, writes a recovery manifest with exact before/after hashes, and does not claim that the review was applied.

### Build not ready

Review application succeeds, but the terminal status is `review_applied_build_required`; the primary next action is the build-probe command. This is not treated as a review-application failure.

## Backward compatibility

- Exit code `35` remains `EXIT_TESTS_BLOCKED`.
- Existing `run-tests` JSON fields remain present and retain their meaning.
- New blocker and next-action fields are additive.
- Existing scripts that use only the process exit code continue to work.
- Existing scripts that parse `data.details.test_execution` continue to work.
- The generic message may change for blocked human output, but `--json` remains the stable automation interface.
- `--allow-placeholder-tests` remains available for explicit compatibility use; the new guided path never recommends it as the normal resolution.
- Existing TestSpec and review-decision contracts are not mutated in place without a schema-versioned migration.

## Testing strategy

### Unit tests

- blocker-code to primary-action mapping;
- blocker count aggregation;
- platform-specific command rendering from argument arrays;
- plan fingerprint stability;
- plan Markdown rendering;
- duplicate input/state/stub target validation;
- placeholder detection;
- disposition and review-resolution validation;
- updated TestSpec construction;
- derived-artifact freshness classification.

### Contract tests

- `test_review_plan` schema acceptance and rejection;
- `test_review_apply_report` schema acceptance and rejection;
- wheel and PyInstaller schema packaging;
- additive CLI result fields;
- no raw shell command as the authoritative JSON action;
- immutable identity and guard fields.

### Repository and transaction tests

- stale TestSpec revision;
- stale TestSpec SHA;
- stale review fingerprint;
- stale case fingerprint;
- two concurrent appliers yield exactly one successful write;
- lock acquisition order;
- atomic replacement and rollback;
- rollback failure recovery record;
- locally modified harness rejection;
- symlink, reparse-point, and Windows long/8.3 alias behavior;
- no product-source modification.

### CLI tests

- exit code 35 human output includes reason and one primary next action;
- JSON output contains structured blocker/action data;
- `--quiet` retains essential blocked guidance;
- `review-test-cases` is non-destructive;
- `apply-test-review` rejects incomplete or stale plans without byte changes;
- `apply-test-review` rejects adopted cases with unresolved blocking review items;
- successful apply returns `build_required` or `ready_to_run` accurately;
- applying a review never starts build or test processes.

### VS Code tests

- code 35 shows `テストケースを確認` as the primary button;
- unchanged blockers do not show `再実行` as primary;
- panel edits round-trip through the CLI plan contract;
- inline errors map to case IDs and fields;
- apply result selects `テストをビルド` or `テストを実行`;
- source/report opening uses workspace-contained URIs.

### End-to-end regression

Use the generated large-module fixture that previously produced ambiguous candidate IDs and duplicate `seed` assignments.

The regression sequence is:

1. generate a fresh workspace from current `main`;
2. run execution and observe `BLOCKED` with exit code 35;
3. assert the output recommends `review-test-cases`;
4. generate a review plan;
5. populate four reviewed executable cases with known inputs and expectations;
6. explicitly resolve every blocking review item for the four adopted cases;
7. apply the review;
8. assert the cases moved to `test_cases`, decisions were persisted, and the harness was regenerated;
9. run the verification build;
10. run tests and assert four passes;
11. confirm prior blocked run/evidence history remains unchanged.

## Rollout

Implementation is divided into independently reviewable slices:

1. structured blocker explanation and improved human output;
2. `test_review_plan` contract and read-only plan generation;
3. validation and guarded TestSpec promotion;
4. coordinated review-decision persistence and transaction safety;
5. harness regeneration and readiness advice;
6. VS Code review panel and action buttons;
7. end-to-end large-module regression and documentation.

The first slice immediately improves the exit-code-35 experience even before the full review application workflow ships. The new commands are documented as preview functionality until transaction, Windows path-safety, and end-to-end gates are green.

## Acceptance criteria

- A user receiving exit code 35 can identify the blocker and the next operation without opening JSON manually.
- `run-tests` never recommends an unchanged rerun as the primary action.
- A review plan can be generated without changing TestSpec or review decisions.
- A stale or incomplete plan changes no canonical bytes.
- A valid reviewed candidate can be promoted to `test_cases` with review authority preserved.
- Every blocking review item for an adopted case is explicitly resolved as `approved` or validly `waived`.
- Duplicate assignments and placeholders cannot enter an executable adopted case.
- Locally modified generated harness files are never silently overwritten.
- Harness and provenance are refreshed after promotion.
- The tool identifies whether build or execution is the next operation.
- Applying a review never starts build or test execution.
- CLI and VS Code use the same reason codes and structured next actions.
- Existing exit-code and JSON consumers remain compatible.

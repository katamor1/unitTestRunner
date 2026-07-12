# Unit Test Runner Phase 1/2 Restart Handoff

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute these task plans one at a time, and use `superpowers:test-driven-development` plus a fresh formal reviewer for every task.

**Goal:** Preserve the Phase 1 Task 6 through Phase 2 Task 8 preflight decisions so work can resume safely from the formally approved Phase 1 Task 5 integration merge.

**Architecture:** Resume on the integration branch, create one branch per independently reviewable task, establish RED before product edits, run cumulative isolated Python verification, obtain fresh formal approval, and merge only the approved task. Contract versions advance by artifact kind and never overwrite an older schema.

**Tech Stack:** Python 3.12, `unittest`, JSON Schema Draft 2020-12, TypeScript 5.4, VS Code 1.85, C90/CP932/CRLF, VC6 DSP/DSW/NMAKE, host compiler verification, Git worktrees.

## Status and authority boundary

- These files are preflight and restart documentation only. Phase 1 Task 6 and every later product implementation task are **not started**.
- Phase 1 Task 5 formal approval and merge is complete. Commit `36622ed` on `codex/unit-test-runner-hardening-sdd` is the recorded restart baseline and must remain an ancestor of every later task branch.
- The tracked phase plans remain the baseline requirements:
  - [Phase 1 contract, execution, and evidence](../2026-07-11-unit-test-runner-phase-1-contract-execution-evidence.md)
  - [Phase 2 VC6 semantic generation](../2026-07-11-unit-test-runner-phase-2-vc6-semantic-generation.md)
  - [Hardening master plan](../2026-07-11-unit-test-runner-hardening-master.md)
- This directory records dependency corrections, stricter RED maps, version coordination, verification policy, and restart commands discovered during preflight. If a later implementation finds a conflict with the current registry, stop and amend the affected task document before changing schemas.
- CSV and Markdown remain generated views. Canonical machine authority is limited to the registered JSON contracts; review approval exists only in `reports/review_decisions.json`.

## Required implementation order

| Order | Task | Deliverable | Prerequisite |
|---:|---|---|---|
| 1 | [Phase 1 Task 6](phase1-task-6-preflight.md) | Stable review decisions and semantic readiness | Approved and merged Task 5 |
| 2 | [Phase 1 Task 7](phase1-task-7-preflight.md) | VS Code adoption of canonical contracts | Approved and merged Task 6 |
| 3 | [Phase 1 Task 8](phase1-task-8-preflight.md) | Public policy, phases, completion, traceability | Approved and merged Task 7 |
| 4 | [Phase 2 Task 1](phase2-task-1-preflight.md) | Per-source VC6 compile context | Phase 1 gate G1 |
| 5 | [Phase 2 Task 7](phase2-task-7-preflight.md) | Exact project/configuration target identity | Approved and merged P2 T1 |
| 6 | [Phase 2 Task 2](phase2-task-2-preflight.md) | Configuration-aware active source | Approved and merged P2 T7 |
| 7 | [Phase 2 Task 3](phase2-task-3-preflight.md) | Shared C type resolver | Approved and merged P2 T2 |
| 8 | [Phase 2 Task 4](phase2-task-4-preflight.md) | Explicit typed and same-TU bridges | Approved and merged P2 T3 |
| 9 | [Phase 2 Task 5](phase2-task-5-preflight.md) | Typed TestSpec values and oracles | Approved and merged P2 T4 |
| 10 | [Phase 2 Task 6](phase2-task-6-preflight.md) | Faithful approved C90 lowering | Approved and merged P2 T5 |
| 11 | [Phase 2 Task 9](phase2-task-9-preflight.md) | Workspace cache and progress protocol | Approved and merged P2 T6 |
| 12 | [Phase 2 Task 8](phase2-task-8-preflight.md) | Host and protected VC6 certification | Approved and merged P2 T9 |

The Phase 2 numeric order is intentionally not the execution order. Exact source compile context must exist before target selection; exact target identity must exist before active-source facts; semantic generation must be complete before indexing/progress; certification is last.

## Coordinated contract-version decisions

| Task | Kind/protocol | Decision |
|---|---|---|
| P1 T6 | `REVIEW_DECISIONS`, `FUNCTION_DOSSIER`, `DOSSIER_MANIFEST` | Current becomes 1.1.0; retain immutable 1.0 schemas and kind-specific migration. |
| P1 T7 | CLI envelope | Remains 1.0.0; extension consumes backend current versions and never guesses them. |
| P1 T8 | `FUNCTION_DOSSIER`, `TEST_EXECUTION_REPORT` | Bump only if serialized traceability/policy shape changes; preserve every prior schema. |
| P2 T1 | `BUILD_CONTEXT` | Current becomes 1.1.0; missing source context in 1.0 remains explicit unknown/display-only. |
| P2 T7 | `TEST_SPEC` and other function-scoped kinds | Introduce explicit `TargetIdentity`. Because T7 precedes T5, TestSpec advances from 1.1.0 to 1.2.0 here. Other changed kinds advance one minor from the actual registry current. |
| P2 T2 | source/fact kinds | Advance only kinds whose active/unknown semantics change; old facts are display-only/stale because provenance cannot be reconstructed. |
| P2 T3 | `FUNCTION_SIGNATURE`, `DEPENDENCY_POLICY` | Advance one minor from actual current; old category strings cannot prove type graph identity. |
| P2 T4 | harness/build kinds | Advance only when bridge/hash/encoding data is serialized. |
| P2 T5 | `TEST_SPEC` | Advance from T7's 1.2.0 to 1.3.0 for typed values/oracles; freeze and retain 1.2, 1.1, 1.0 schemas. This resolves the two source briefs that independently proposed 1.2.0. |
| P2 T6 | harness report | Advance one minor only if the generation-gate/report shape changes. |
| P2 T9 | progress events | Standalone protocol 1.0.0, not an ArtifactKind and not a CLI envelope bump. |
| P2 T8 | acceptance records | No invented production ArtifactKind and no gratuitous schema bump. |

For every schema change: add the new schema instead of editing the old one, register the new current version, provide only lossless migration, keep migrated data display-only when current semantics cannot be proven, build the wheel, install it fresh, and load every registry schema from the installed package.

## Authoritative isolated verification policy

The host periodically enters a high-load state during a monolithic Python run. Therefore, cumulative PASS from every actual `tests/test_*.py` module, each launched serially in a fresh Python process, is the authoritative full Python PASS. Do not run `unittest discover` as one monolithic process.

Run from the repository root in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$modules = Get-ChildItem -LiteralPath .\tests -Filter 'test_*.py' -File |
  Sort-Object Name |
  ForEach-Object { 'tests.' + $_.BaseName }
$failed = @()
foreach ($module in $modules) {
  & py -m unittest $module -v
  if ($LASTEXITCODE -ne 0) { $failed += $module }
}
if ($failed.Count -ne 0) {
  throw ('isolated Python failures: ' + ($failed -join ', '))
}
```

Record module count, executed test count, skips, failures, errors, and nonzero process exits in the task report. A task cannot claim the full gate from a subset. Run focused RED/GREEN tests first, then related modules, then this isolated full gate.

Common non-Python gates:

```powershell
py -m compileall -q src tests
py -m unit_test_runner --help
git diff --check
```

When extension files change, also run from `vscode/extension`:

```powershell
npm.cmd test
npm.cmd run compile
npm.cmd run build
```

Use the package scripts that exist at the task's base; if a named script is absent, record that fact and run the equivalent declared package gate. Schema changes additionally require wheel build, fresh-environment install, registry/schema load, and version/migration tests. C-generation changes require fixture compile/link or compile/run as specified by the task.

## Per-task branch, review, and merge protocol

1. Confirm the prerequisite task is formally approved and merged into `codex/unit-test-runner-hardening-sdd`.
2. Start a fresh task branch from the integration HEAD named in the task document.
3. Run the listed RED test and preserve evidence that it fails for the intended missing behavior.
4. Implement the minimum coherent behavior; do not absorb a later task's boundary.
5. Run focused, related, isolated full, compile/package/extension/fixture, and `git diff --check` gates as applicable.
6. Commit product and tests in reviewable units; leave the task branch clean except ignored `.superpowers` reports.
7. Freeze the base-to-head diff and give it to a fresh formal reviewer. Fix every Critical/Important finding and obtain a new formal approval.
8. Merge the approved branch with `--no-ff` into the integration branch. Do not parallelize product-writing tasks that share this tree.

## Explicit restart checklist after Task 5

Task 5 formal approval and merge are complete. Re-verify the recorded ancestor before opening the Task 6 branch:

```powershell
Set-Location C:\Users\stell\source\repos\unitTestRunner-sdd
$env:PYTHONPATH = (Resolve-Path .\src).Path
git status --short --branch
git switch codex/unit-test-runner-hardening-sdd
git merge-base --is-ancestor 36622ed HEAD
if ($LASTEXITCODE -ne 0) { throw 'Task 5 integration merge 36622ed is not an ancestor of HEAD' }
git show --no-patch --oneline 36622ed
git log --oneline --decorate -8
git status --porcelain
git show HEAD:src/unit_test_runner/schemas/test_spec.schema.json *> $null
py -m unit_test_runner --help
git switch -c codex/p1t6-review-decisions-readiness
```

Before the final `git switch -c`, verify:

- the integration worktree is clean;
- Task 5 integration merge `36622ed` is an ancestor of the current integration HEAD;
- `TEST_SPEC` current version is 1.1.0 and its 1.0 schema remains loadable;
- canonical `reports/test_spec.json` is the only editable test contract;
- the exact-saved-bytes repository/export/harness/reanalysis tests from Task 5 pass in isolated processes;
- no Task 6 product implementation is already present on the branch.

Then follow [Phase 1 Task 6](phase1-task-6-preflight.md). If any check fails, do not create the Task 6 branch; restore the recorded integration baseline or investigate the regression first.

## Phase boundaries retained for later work

- Phase 2 does not implement Phase 3 progress UI, coordinator/cancellation UX, workspace queueing, dialogs, accessibility, or Extension Host E2E.
- Phase 2 does not implement Phase 4 three-way reanalysis merge, portable suite management, or stale-safe suite history.
- P2 T9 exposes a validated progress callback only; P2 T8 certifies semantics only.
- Completion means the task's fresh reviewer approves and all applicable gates pass. Preflight text alone is never implementation evidence.

## Task 5 completion baseline

- Task branch head: `b5baacd`.
- Integration merge: `36622ed`.
- Formal review: **Approved**, Critical 0, Important 0, Minor 0.
- Merge-after focused verification: isolated external custom regression 1/1, `test_test_spec_cli` 2/2, `compileall` PASS, and diff check PASS.
- Recorded cumulative isolated evidence: 111/111 modules, 520 tests, 3 skips, 0 failures. The newly added external custom regression is reported separately as 1/1 instead of being added to the cumulative test total, avoiding duplicate counting.
- Task 6 and all later product tasks remain not started at this baseline.

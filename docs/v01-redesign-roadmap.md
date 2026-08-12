# unitTestRunner v0.1 redesign roadmap

Status: active
Created: 2026-08-11
Scope: four milestones, fourteen vertical tasks

This is the only active product roadmap. The former 38-task plans under
`docs/superpowers/plans/` are historical inputs, not completion authority.

## Product boundary

unitTestRunner v0.1 creates reviewable dossiers and executable evidence for a
supported subset of legacy VC6/C90 functions. It keeps dossier, TestSpec,
build/run, ordinary artifact review, reanalysis, suite execution, and a thin
VS Code adapter. It does not claim a complete C frontend, universal automatic
harness generation, hostile same-user filesystem resistance, supply-chain
provenance, runtime reviewer IPC, or immutable proof ledgers.

The local host, Python, Git, Node, and SystemRoot are developer-controlled
trusted inputs for v0.1. A requirement outside this boundary is recorded for
Phase 2 or raised as a scope-expansion request; it is not silently added to an
active task.

## Public interfaces

Exactly these JSON artifact kinds are public:

1. `function_dossier`
2. `test_spec`
3. `review_record`
4. `build_probe_report`
5. `test_run_report`
6. `reanalysis_report`
7. `suite_manifest`
8. `suite_run_report`

Every public artifact has `schema_version: "1.0.0"`, `artifact_kind`,
`subject`, and `data`. The subject retains source-relative path, source
SHA-256, function, project, and full configuration. Markdown, CSV, and log
files are views and do not define separate schemas.

The public CLI envelope contains only:

- `command`
- `outcome`
- `message`
- `artifacts[{kind,path,sha256}]`
- `diagnostics[{code,level,message}]`

The outcome domain is `planned`, `passed`, `failed`, `blocked`, `timed_out`,
`cancelled`, and `error`. Only a successfully completed execution is
`passed`; malformed input, a missing artifact, or an outcome/exit mismatch is
non-zero.

The supported commands are:

- project/analysis: `doctor`, `discover-projects`, `map-source`,
  `list-functions`, `analyze-function`, `finalize-dossier`
- review/input: `review-set`, `get-test-input-form`,
  `apply-test-input-form`
- build/run: `build-probe`, `run-tests`
- reanalysis: `reanalyze-function`, `apply-reanalysis`
- suite: `suite-register`, `suite-update`, `suite-remove`, `suite-list`,
  `suite-run`

Real function and suite runs require zero unresolved items, a successful
build-probe, and an `approved` review record for the current TestSpec SHA.
Dry-run and build-probe remain available before approval.

Old workspaces are regenerated. v0.1 does not provide automatic workspace
migration, compatibility aliases, opaque authority wrappers, or private
schema registries.

## Milestone 1: foundation

### Task 1 — Git topology and baseline

- Archive both historical Git common directories, refs, worktrees, dirty
  bytes, and PR inventory outside the repository, and verify replay.
- After explicit approval, close superseded PRs and remove archived branches,
  worktrees, the nested common directory, and incomplete archive attempt.
- Keep one primary common directory, at most two normal worktrees, `main`, and
  one active milestone branch.
- Establish the serial Python and VS Code full-suite baseline once.

### Task 2 — Public schemas and truthful CLI

- Implement only the eight public artifact schemas and the public CLI
  envelope.
- Remove old schemas, migrations, aliases, opaque wrappers, internal DTO
  schemas, and duplicate hash domains after their callers are replaced.
- Test schema package membership, reference resolution, all outcomes, exit
  agreement, and artifact SHA readback.

### Task 3 — Dossier, TestSpec, review, and run persistence

- Keep `reports/function_dossier.json` and `reports/test_spec.json` canonical.
- Store a review record containing artifact kind/SHA, decision, reviewer,
  timestamp, and comment; a changed artifact invalidates approval.
- Store ordinary `runs/<run_id>/test_run_report.json` results without a hash
  chain or immutable ledger.
- Persist a current dossier before workspace-based review assessment, then
  recompute and rewrite readiness truthfully.
- Reject old workspaces with a clear regeneration error.

## Milestone 2: supported VC6 execution

### Task 4 — VC6 target, paths, and encodings

- Auto-select only a unique project, full configuration, and source
  membership. Zero or multiple matches return `blocked` with candidates and
  write no artifact.
- Derive build context in project-base, full-configuration, source
  ADD/SUBTRACT order.
- Treat DSW/DSP, CP932/Shift-JIS/UTF-8 BOM, Windows paths, and UNC paths as
  normal inputs.
- Require output outside the source root and reject ordinary canonical
  containment or reparse/symlink escapes.

### Task 5 — Function, preprocessor, and type facts

- Exclude only regions known inactive under selected defines.
- Preserve unknown conditions as diagnostics and unresolved items.
- Share a small type classification across target, dependency, and global
  analysis; never coerce ambiguous types to `int`.
- Cover representative file-scope definitions, externs, and direct calls.
- Full preprocessing, a complete C type system, and C++ are non-goals.

### Task 6 — Dependency, harness, build-probe, and run

- Support direct calls as `real`, `stub`, or `review_required`.
- Mark function pointers, macro/member calls, and unrepresentable values for
  review.
- Never leave placeholders or always-true oracles in a runnable harness.
  Unresolved work produces a review-only scaffold and blocks real run.
- Generate C90/CP932/CRLF artifacts in an external workspace without changing
  source.
- Accept real execution only for the reviewed `Control_Update` and practical
  fixture paths; universal automatic harness generation is not promised.
- Cache/progress protocols remain Phase 2 until measured evidence justifies
  expansion.

## Milestone 3: thin, truthful UX

### Task 7 — Workspace-safe CLI and VS Code execution

- Resolve the target from the active document's workspace folder and
  resource-scoped settings, never a global last-workspace value.
- Share one simple extension-wide single-flight gate; reject a second request
  before spawning.
- Preflight DSW/source/output/timeout/CLI availability.
- Release the gate on success, failure, spawn error, and timeout; return from
  timeout only after process-tree cleanup.
- Do not add a scheduler, event bus, runtime IPC, or hostile-filesystem
  hardening.

### Task 8 — Truthful workflow, TestSpec, and review UI

- Advance workflow only from validated CLI success or explicit user
  confirmation, never file existence, open, or save alone.
- Edit canonical TestSpec only through the Python CLI revision guard.
- Clear downstream review/build/run state after reanalysis or regeneration.
- Present review as ordinary artifact review, not runtime authority.

### Task 9 — Accessibility and distribution boundary

- Give existing buttons, checkboxes, and form controls accessible names; use
  `aria-pressed` for toggles.
- Restore minimum focus after refresh, save, and conflict reload.
- Smoke source CLI, Windows EXE, bundled VSIX CLI, and installed VSIX.
- Keep C/DSW/DSP analysis out of the extension.

## Milestone 4: reanalysis and suites

### Task 10 — Non-destructive reanalysis

- Derive function and case IDs deterministically from source-relative path,
  function, coverage anchor, and case kind.
- Produce a candidate TestSpec and reanalysis report without rewriting the
  canonical TestSpec.
- Copy human input for identical case IDs and report field-level conflicts.
- Apply only when expected revision and candidate SHA match and conflicts are
  zero. Do not add an immutable base store or automatic three-way merge.

### Task 11 — Explicit regression selection

- Support only explicit case ID, tag, and `all` selectors.
- Reject unknown, empty, or disabled selectors as input errors.
- If change mapping is unknown, recommend all cases without selecting them
  automatically.
- Record requested, started, completed, and not-run case IDs.

### Task 12 — Portable suite manifest

- Store manifest-relative POSIX paths, entry ID, enabled flag, tags, function
  subject, TestSpec SHA, and harness SHA.
- Reject traversal, duplicates, unknown entries, and empty selection.
- Use revision-guarded atomic register/update/remove writes.
- Preserve tags and enabled state on re-registration unless explicitly set.

### Task 13 — Stale-safe suite execution

- Compare source SHA, TestSpec SHA, and harness SHA before execution.
- Block before spawning on mismatch and report changed fields.
- Reuse Task 6 approval/run gates for every entry.
- Aggregate every selected outcome and return non-zero if any is not `passed`.
- Do not add cryptographic history chains, Python installation provenance, or
  complete repository-read identity proofs.

### Task 14 — Suite UI, legacy removal, and cutover

- Offer register, enable/disable, tags/filter, explicit selection, run, and
  open-latest-report only.
- Remove advanced analytics, unlimited history drill-down, automatic
  regression graphs, replaced schemas/commands/modules/tests, and stale docs.
- Align README and usage guides to the one-way v0.1 workflow.
- Run the final release gates and mark the old 38-task plan historical.

## Fixed test and review budgets

- Focused acceptance: at most 20 tests per task.
- New or substantially changed tests: at most 8 per task.
- Ordinary review: one per task; Tasks 3, 6, 9, and 14 may add one milestone
  review.
- Serial Python and full VS Code suites run only at the initial baseline and
  final Task 14 gate. Intermediate tasks run fixed affected modules.
- Keep tests for retained behavior. Delete tests dedicated solely to removed
  behavior in the same task.
- Final retained Python and extension suites must be green; removed
  meta-authority behavior is not retained as an accepted failure.

Fixed final smoke:

- S1: source CLI creates dossier/TestSpec and performs build-probe/run on the
  VC6 fixture.
- S2: packaged EXE and VSIX build; bundled EXE hash equals the packaged EXE.
- S3: isolated installed VSIX covers analyze, review, build/run confirmation,
  reanalysis, and suite representative paths.

Every task also runs `compileall` where applicable, verifies fixture/source
immutability and external output roots, and runs `git diff --check`.
Completion means the task's fixed properties pass, task-caused regressions are
zero, and in-scope blockers are zero. Open-ended `C0/I0/M0` is not a gate.

## Review and expansion guardrails

Each task begins with user value, fixed scope, non-goals, test limit, review
limit, and Phase 2 deferral conditions. A newly proposed schema, operation,
threat category, test family, or review gate is not implemented automatically;
it requires a scope-expansion request describing reason, cost, and user value.
Existing authority gaps are classified as STOP, accepted risk, or Phase 2 and
are not bypassed with prose or private overlays.

Cleanup, stage, commit, push, PR close, and branch deletion always require
separate explicit approval. Existing user changes are never discarded.

## Progress

| Milestone | Task | State |
|---|---|---|
| M1 | 1 Git topology and baseline | implemented / verified |
| M1 | 2 Public schemas and truthful CLI | implemented / verified |
| M1 | 3 Dossier, TestSpec, review, run persistence | implemented / verified |
| M2 | 4 VC6 target, paths, encodings | implemented / verified |
| M2 | 5 Function, preprocessor, type facts | implemented / verified |
| M2 | 6 Dependency, harness, build/run | implemented / verified |
| M3 | 7 Workspace-safe CLI/VS Code | implemented / verified |
| M3 | 8 Truthful workflow/review UI | implemented / verified |
| M3 | 9 Accessibility/distribution | implemented / verified |
| M4 | 10 Non-destructive reanalysis | implemented / verified |
| M4 | 11 Explicit regression selection | implemented / verified |
| M4 | 12 Portable suite manifest | implemented / verified |
| M4 | 13 Stale-safe suite execution | implemented / verified |
| M4 | 14 Suite UI and cutover | implemented / verified |

Current topology evidence (2026-08-13): both archived repository bundles
verify as complete history; the live repository has one common directory,
two worktrees, `main` plus the active milestone branch, remote `main` only,
no nested Git directory, and no open pull request.

Current final-gate evidence (2026-08-13): retained Python tests ran 449 and
reported OK (`skipped=3`), VS Code tests 35/35, S1 source CLI build/run PASS, and S2
packaged EXE/VSIX PASS with identical packaged/bundled/VSIX-entry executable
hashes. S3 used the installed VSIX in an isolated trusted profile and exercised
the real extension command handlers for `analyze-function`, `review-set`,
`finalize-dossier`, harness preparation, build dry-run, `reanalyze-function`, and
`suite-register`. The build and test handlers both reached their modal confirmation
and were cancelled before process spawn. The UI rendered the `Control_Update`
workflow and its enabled suite entry. The bundled EXE SHA-256 remained
`1a753ddb1317e3403fa3541ddadc511f9ad2d3d34408f857042d16501d9f9e74`, the
Extension Host log SHA-256 is
`8ba644a64c9c4f54a8fe1975210bb2f9f37d8f02da8658b7dda9aba5a2799399`, and
the five-file VC6 fixture stayed clean with aggregate SHA-256
`458eeec5ece2ccf35d974634ed8e61b10c3125baa1abda3a037284be7e68e192`.

The fixed-scope final whole-branch review found eight roadmap-level truthfulness
and state-invalidation issues. One bounded remediation wave closed them; the
integrated affected Python checks passed 55/55, the affected VS Code checks
passed 16/16, the retained ambiguous-map and partial-mapping checks passed 4/4,
and the scoped independent re-review approved the resulting working tree.
The post-remediation full-suite logs are SHA-256
`c207be70bd5acf2729222b5950fe1af11b98d73d26aefecd7b18c4499777787f`
(Python) and
`c61e553b4154f1561af6caee081e46e8f7eaf2eda6004a0c85a07bb6ff83e9e4`
(VS Code).

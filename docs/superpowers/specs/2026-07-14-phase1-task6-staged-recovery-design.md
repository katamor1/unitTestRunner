# Phase 1 Task 6 Staged Recovery Design

**Status:** Approved by the user on 2026-07-14.

## Objective

Move the hardening program from the proven `13 / 38` boundary to a verified
`14 / 38` boundary by restoring a trustworthy `main` baseline first and then
merging Phase 1 Task 6 as one carrier-free product pull request.

This design preserves the full `38 / 38` objective. It defines only the next
two merge boundaries; Phase 1 Tasks 7 and 8 receive their own execution plans
after Task 6 is merged.

## Authority and supersession

The semantic requirements in these files remain binding:

- `docs/superpowers/plans/2026-07-11-unit-test-runner-hardening-master.md`
- `docs/superpowers/plans/2026-07-11-unit-test-runner-phase-1-contract-execution-evidence.md`
- `docs/superpowers/plans/preflight/phase1-task-6-preflight.md`

For branch creation, recovery, verification ordering, evidence timing, and
merge sequencing, this design supersedes conflicting commands in:

- `docs/superpowers/plans/preflight/README.md`
- `docs/superpowers/plans/2026-07-13-phase1-task6-recovery-and-main-merge.md`

The older recovery plan remains investigation evidence. It is not executable
as written because its CI contract, compiler-skip, TDD, and evidence-ordering
steps conflict with the current repository.

## Proven starting state

- `main` and `origin/main` are `b66790165a2d4f82943cd199b3b499e1f1725fc3`.
- Integrated progress is Phase 0 `8 / 8` plus Phase 1 `5 / 8`, or `13 / 38`.
- The primary checkout contains the user's staged `build.ps1` and an untracked
  older recovery plan. Neither belongs to this work.
- The isolated worktree is
  `C:\Users\stell\source\repos\unitTestRunner-sdd` on
  `codex/p1-baseline-gate` at `b667901`.
- The baseline has one reproducible TestSpec consumer failure. The host VC6
  end-to-end test skips locally because no supported host compiler is present.
- GitHub CI still runs monolithic Python discovery despite the repository's
  authoritative isolated-process policy.

## Merge boundary A: baseline maintenance pull request

The first pull request is maintenance-only. It contains no Task 6 product
implementation.

### CI contract

`tests/test_ci_contract.py` becomes the executable contract for:

- enumerating every actual `tests/test_*.py` module;
- running each module serially in a fresh Python process;
- collecting all failing module names before failing the job;
- preserving the Python failure-log artifact;
- requiring `gcc`, `clang`, or `cc` before the VC6 fixture smoke command.

The contract test changes first and must fail against the old workflow. The
workflow changes only after that RED result is recorded.

### Existing regression alignment

`tests/test_test_spec_consumers.py` compares normalized consumer identifiers
with the canonical envelope rather than obsolete literals.

`tests/test_vc6_fixture_build_e2e.py` asserts CLI envelope 1.0.0 through:

- `data.outcome`;
- `data.exit_code`;
- `data.details.build_probe.status`.

These are test corrections for already-established public contracts; they do
not add product behavior. The existing TestSpec failure is the RED evidence.
The VC6 assertion is verified by the compiler-required GitHub smoke job.

### Evidence and review

The committed baseline record contains only facts knowable before the pull
request: base SHA, code commit SHA, focused RED/GREEN output, local isolated
totals, skips, and local limitations. Pull-request URLs, Actions run URLs,
review verdicts, and merge SHA remain GitHub evidence and are added only to a
post-merge record when they exist. No commit attempts to contain its own SHA.

The branch receives task-scoped subagent reviews and one whole-branch review.
All six GitHub jobs must pass before a merge commit is created on `main`.

## Merge boundary B: Task 6 product pull request

The second pull request starts from the merged baseline and contains one clean
Task 6 product diff.

### Recovery authority

PR #16 is a carrier and must never be merged. Its payload is nevertheless the
only complete, reproducible Task 6 source:

- gzip SHA-256:
  `121bfc6fdcbb6e8728402997f291a0ef3af000d775d3c8bca791e0de28d13123`;
- patch SHA-256:
  `8aaa74a87b2e1ea64087726bbcbfd8c998d5940c458d04768b63f969fe461ef0`;
- reconstructed product tree:
  `363ddb6f86a4508eb5f4dd2a26013b837a5e26d6` on base `b667901`.

The later checkpoint payload is not an alternative: its decoded gzip is
29,997 bytes with SHA-256
`080fd74895b0f651a9705a8fa5392cb8bf5d39b0f2546de6c6569c9db73f202d`,
does not match its recorded size/hash, and cannot be decompressed.

### TDD recovery

Recovery does not make the carrier authoritative. Before applying a product
behavior hunk, the Task 6 execution plan identifies its focused behavioral
test, applies or writes that test first, and records an assertion-level RED on
the merged baseline. The corresponding minimal product slice is then applied
and verified GREEN. Import/setup errors are not accepted as RED evidence.

The four known compatibility failures are handled as separate RED/GREEN
cycles:

- current-envelope reanalysis normalization;
- the already-fixed baseline TestSpec consumer expectation;
- the already-fixed baseline VC6 CLI envelope expectation;
- declared `referencing` dependency and normal fresh-wheel installation.

Carrier payload files, materialization workflows, and checkpoint metadata are
excluded from the product branch.

### Task 6 acceptance

The product pull request must prove:

- stable semantic review IDs shared by dossier and TestSpec;
- immutable 1.0 schemas plus current 1.1.0 schemas and lossless compatible
  migration;
- revision-checked, atomic, stale-aware decision persistence;
- `reports/review_decisions.json` as the sole approval authority;
- independent `ready_for_review`, `review_complete`, `evidence_ready`, and
  `test_green` axes;
- CLI envelope 1.0.0 for discovery and write commands;
- every Python test module passing in a separate process;
- compileall, CLI smoke, wheel/fresh-install, registry/schema, fixture, VS Code,
  source-integrity, and diff checks;
- fresh review with Critical 0 and Important 0.

Only after the product merge and post-merge verification may the phase plan,
Task 6 preflight, restart handoff, and completion record advance to `14 / 38`.

## Failure handling

- A baseline CI failure is diagnosed and fixed on the baseline branch; Task 6
  recovery does not begin early.
- A Task 6 recovery hash or tree mismatch stops recovery without applying the
  patch.
- A test that errors instead of demonstrating the intended missing behavior is
  corrected before product code is applied.
- A Critical or Important review finding returns to the same task's implementer
  and reviewer loop.
- An obsolete PR or branch is closed or deleted only after the clean Task 6
  merge is verified to contain every required product change.

## Next phase boundary

After Task 6 reaches `14 / 38`, write and execute a separate Phase 1 Task 7
plan. Task 8 follows Task 7. Phase 2 does not begin until Gate G1 proves all
eight Phase 1 tasks complete, bringing progress to `16 / 38`.

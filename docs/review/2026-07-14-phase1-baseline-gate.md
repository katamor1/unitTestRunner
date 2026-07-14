# Phase 1 Baseline Gate Evidence

## Scope

This pre-publication record covers the maintenance-only Phase 1 baseline gate:
isolated Python-module execution in CI, an explicit fixture-compiler
precondition, and alignment of existing TestSpec and CLI-result assertions with
their current public contracts. It contains no Phase 1 Task 6 product
implementation.

## Base and code commits

- Product base: `b66790165a2d4f82943cd199b3b499e1f1725fc3`
- CI contract code commit: `72e14f616884b5bcb0b9f8e61adcca8e9853776c`
- Baseline assertion code commit: `1c039f308d4c10a71ed7ae2fc1756349f3978d3b`
- CI review-remediation test commit: `bccf17e1a6f7d08e29b7f51b80f29c958114315c`
- Second CI review-remediation test commit: `33adb15039c5ad0d12a1bd693a59f76be2cd3dee`
- Append-only log remediation test commit: `d22a4acd626c31b19fa2e7ece14822fdcbde6b4e`
- Windows path-alias prerequisite merge on `main`: `99f71317584bdf5bb22aac8081c1c7c02fe7ba6b`
- Current-main integration merge: `2565e5387d6323542ae1c4d4f5dbf7ddc0b47a18`
- Fail-closed CI workflow remediation: `1c6c733241c6348eb5483b0aaf2c7652b37540f1`
- YAML token-semantics remediation: `677815a0e1df60b07fdd8e04991c6b8823e722b2`

## Focused RED evidence

With `PYTHONPATH` set to the repository `src` directory,
`py -m unittest tests.test_test_spec_consumers -v` ran six tests. Exactly
`test_canonical_envelope_is_normalized_to_consumer_data_and_views_are_rejected`
failed: the obsolete expected value `spec-control-update` differed from the
canonical normalized value `spec-fn_control_update_cdd351ecf31d`. The other
five tests passed.

## Focused GREEN evidence

After aligning the assertions with the canonical envelopes:

- `py -m unittest tests.test_test_spec_consumers -v` passed 6 tests.
- `py -m unittest tests.test_cli_result_contract -v` passed 4 tests.
- `py -m unittest tests.test_vc6_fixture_build_e2e -v` ran 1 test and skipped
  it with `host C compiler is required`.
- `git diff --check` exited successfully.

## Review remediation

Whole-branch review at `3ea51892ba7c6a6395eeb15b3e8441c34bc22a72`
found one Important test-coverage gap: the CI contract did not reject removal
or displacement of several isolated-test and compiler-precondition invariants.

Regression-first RED ran `tests.test_ci_contract` as seven tests. The six
pre-existing tests passed, while all seven mutation subtests failed because
the incomplete validator accepted removal of sorting, failure collection, the
final throw, and append logging; compiler-precondition reordering; dynamic
compiler installation; and Python failure-artifact renaming.

After adding job- and step-scoped validators, `tests.test_ci_contract` passed
7 tests, `tests.test_repository_source_tracking` passed 2 tests, all seven
mutants were rejected, and `git diff --check` exited successfully. Commit
`bccf17e1a6f7d08e29b7f51b80f29c958114315c` changes only the executable CI
regression contract; `.github/workflows/ci.yml` and Task 6 product behavior
were not changed. A fresh whole-branch re-review remains pending, and no final
review verdict is claimed here.

## Second review remediation

Re-review at `45b465c7a80c86e4a956261808552b1c070c4790`
identified three remaining false-green paths in the Python-loop contract and
one false-red path in the dynamic-install scan. Regression-first RED ran
`tests.test_ci_contract` as 8 tests with 4 failures: inline termination,
success-polarity failure collection, and post-loop log truncation were
accepted, while a harmless full-line compiler-install comment was rejected.
The other tests and the prior seven mutation cases remained GREEN.

After requiring the exact non-terminating loop guard, scanning inline control
flow, limiting executable `$log` use to initialization and append-only writes,
and excluding full-line comments from runtime scans,
`tests.test_ci_contract` passed 8 tests and
`tests.test_repository_source_tracking` passed 2 tests. All 10 mutants were
rejected, the harmless-comment control was accepted, and `git diff --check`
exited successfully. Commit
`33adb15039c5ad0d12a1bd693a59f76be2cd3dee` changes only the executable CI
regression contract; `.github/workflows/ci.yml` and Task 6 product behavior
were not changed. A fresh whole-branch re-review remains pending, and no final
review verdict is claimed here.

## Append-only log remediation

Re-review at `544b41c484365d1c4ab83d78f9581d5398df68f2`
identified one remaining false-green: a pipeline could truncate `$log` before
ending in the allowed append-only `Tee-Object` form. Regression-first RED ran
`tests.test_ci_contract` as 8 tests with the single expected accepted-mutant
failure. The real workflow, prior 10 mutants, harmless-comment control, and
other contract tests remained GREEN.

The validator now requires every non-initializer executable log line to match
the full append-only Tee form and contain `$log` exactly once as Tee's
`-FilePath` argument. After the change, `tests.test_ci_contract` passed 8
tests, `tests.test_repository_source_tracking` passed 2 tests, all 11 mutants
were rejected, the harmless-comment control was accepted, and
`git diff --check` exited successfully. Commit
`d22a4acd626c31b19fa2e7ece14822fdcbde6b4e` changes only the executable CI
regression contract; `.github/workflows/ci.yml` and Task 6 product behavior
were not changed. A fresh whole-branch re-review remains pending, and no final
review verdict is claimed here.

## Authoritative isolated gate

Before the review-remediation commits, every actual `tests/test_*.py` module
was executed serially in a fresh Python process. This initial authoritative
gate observed
`isolated_modules=111 tests=521 skips=3 failures=0`.

After the isolated module loop, `py -m compileall -q src tests`,
`py -m unit_test_runner --help`, and `git diff --check` each exited
successfully. The CLI help exposed the expected command surface through
`suite-run`.

## Final pre-publication re-verification

The final local pre-publication gate verified code/test head
`b6ce72e34cff1d34c0cc4683a6693e616d73300f` under isolated run ID
`20260714T045158659+0900`. It executed all 111 top-level test modules in
separate serial Python processes and observed 523 tests, 3 skips, 0 failures,
0 errors, 0 failing modules, 0 non-zero module exits, and 0 result-parse
failures. All 111 module-process commands exited 0.

The increase from the initial 521 tests to 523 tests is accounted for by the
CI mutation and harmless-comment regression methods added during review
remediation; it is not a missing or duplicated module.

At the verified head, `py -m compileall -q src tests`,
`py -m unit_test_runner --help`, and `git diff --check b667901..HEAD` each
exited 0. The final `git status --porcelain=v1` produced no entries, confirming
that the target worktree was clean at the end of the verification run.

## Current-main integration re-verification

After prerequisite PR #18 merged, current `origin/main` at
`99f71317584bdf5bb22aac8081c1c7c02fe7ba6b` was merged into the baseline
branch. The resulting code/test integration head was
`2565e5387d6323542ae1c4d4f5dbf7ddc0b47a18`. Its effective pull-request diff
against current main contains only the CI workflow, the CI contract test, and
three plan/review documents; it contains no `src/` product-code change and no
Phase 1 Task 6 implementation.

The merged workflow retains both the sorted fresh-process module loop and
`UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "1"`. Focused verification ran
`tests.test_ci_contract`, `tests.test_windows_path_alias_regression`,
`tests.test_test_spec_consumers`, and `tests.test_vc6_fixture_build_e2e` as 22
tests: 21 passed and only the compiler-backed fixture test reported the
expected local `host C compiler is required` skip. All seven Windows path
alias regressions ran and passed without skipping.

The first complete merged-head run executed all 112 modules successfully and
observed 534 tests, but the prerequisite branch's external validation script
still expected the pre-merge main total of 532. Comparing its CSV with the
pre-merge main CSV isolated the entire two-test increase to
`tests.test_ci_contract`: the baseline branch adds the mutation-rejection and
harmless-comment controls, increasing that module from six tests to eight.
No other module count changed.

The same isolated gate was then rerun with the merged-head expectation of 534
tests and exited 0. Run `20260714-073944` recorded 112 modules, 534 tests, 3
expected compiler skips, 0 failures, 0 errors, 0 non-zero module exits, and 0
result-parse failures. Its raw local evidence is
`C:\Users\stell\AppData\Local\Temp\unit-test-runner-isolated-20260714-073944.log`
with the corresponding `.csv` file at the same basename.

At the integration head, `py -m compileall -q src tests`,
`py -m unit_test_runner --help`, and `git diff --check origin/main..HEAD` each
exited 0. Hosted verification on the new pull-request head remains mandatory;
these local results do not claim GitHub Actions success.

## Current-main review remediation

Independent review of the merged branch found that the workflow itself was
correct but its executable contract still accepted behavior-defeating
mutations. Regression-first verification initially reproduced six accepted
mutants: zero-test selectors, post-loop failure reset, compiler-result
overwrite, literal-path log truncation, and relocation of the required 8.3
environment setting. Subsequent adversarial passes reproduced job/step
disabling, shell and environment overrides, setup-step test masking,
workflow-level default-shell masking, trigger removal, and disabling of the
other four jobs. A separate RED proved that strategically placed harmless
full-line comments prevented the raw mutation anchors from applying. A final
boundary RED then showed that a valid YAML comment immediately after a literal
scalar changed the hand-normalized digest even though PyYAML produced the same
workflow value.

The contract now uses layered fail-closed checks: a canonical PyYAML token-stream
SHA-256, a parsed-node workflow preamble, canonical `python-tests` and
`fixture-smoke` jobs, and canonical PowerShell run blocks. Tokenization ignores
YAML comments and structural whitespace while retaining scalar token values
and styles, duplicate keys, and literal scalar values. This prevents PyYAML 1.1
from collapsing `on:` into `true:` and prevents last-value handling from hiding
duplicate keys. Full-line comments, blank lines, and trailing ASCII spaces
remain permitted only in YAML structure outside literal block scalars; literal
script values remain exact. The Python loop throws when module discovery
returns zero modules. A separate scalar-aware normalizer is used only for
mutation anchors and test-side inspection, so validator acceptance does not
depend on the hand-normalized source.

Focused GREEN ran all ten `tests.test_ci_contract` methods and both
`tests.test_repository_source_tracking` methods successfully. The contract
rejected all 48 mutants in both raw and commented forms, while accepting the
real workflow, YAML-structure comment controls, and the literal-scalar boundary
comment control. The added collision proof confirms that token canonicalization
distinguishes `on:` from `true:` and preserves duplicate keys even when
`safe_load` results are equal. A nested PowerShell proof showed the custom-shell
mutant can mask an internal failure with wrapper exit 0; the contract rejects
that effective variant. `py -m compileall -q src tests` and `git diff --check`
also exited 0.

The test-only dependency is declared as `PyYAML>=6.0.1,<7`, installed by the Python
test job through `pip install -e ".[test]"`, and documented in the README, test
specification, and developer ADR. A temporary wheel inspection confirmed both
`Provides-Extra: test` and the conditional PyYAML requirement; an editable
install dry-run resolved PyYAML successfully. Product, fixture, and package
contract installs remain on the base dependency set.

The remediation adds no product code or Phase 1 Task 6 behavior. Independent
post-fix code and documentation reviews reported Critical 0, Important 0, and
Minor 0. The final code review instrumented both mutation paths: each accepted
its normalized baseline before rejecting 48 distinct applied mutants. The ten
CI-contract tests also passed under CPython 3.12.13 with PyYAML 6.0.1. The
complete 112-module isolated gate was then rerun on the follow-up remediation
commit as recorded below.

## Follow-up remediation verification

The verified code-and-test head is
`677815a0e1df60b07fdd8e04991c6b8823e722b2`. Before creating its log, the
isolated runner executes `git status --porcelain --untracked-files=no` and
throws if any tracked change exists. This invocation passed that fail-fast
precondition, wrote the verified HEAD to its log, and then ran every tracked
top-level `tests/test_*.py` module in its own Python process. The final strict
summary was 112 modules, 536 tests, 3 expected compiler-required skips,
0 failures, 0 errors, 0 nonzero module exits, and 0 result-parse failures. The
runner exited 0 after also matching the exact three-method skip set.

The two-test increase from the earlier 534-test integration baseline is fully
accounted for by the scalar-boundary acceptance regression and the YAML 1.1 /
duplicate-key collision regression added to `tests.test_ci_contract`. The
successful raw evidence is
`C:\Users\stell\AppData\Local\Temp\unit-test-runner-isolated-20260715-000605.log`
with the corresponding `.csv` file at the same basename.

## Local compiler limitation

`Get-Command gcc, clang, cc -ErrorAction SilentlyContinue` found no supported
host compiler (`fixture_compiler=not_found`). The focused VC6 fixture E2E was
therefore the single compiler-required skip in its module, while the final
full gate retained three local skips; all three reported
`host C compiler is required`. These local results do not substitute for the
GitHub compiler-required job, which must execute its compiler-backed path
without skip.

## Publication boundary

The current-main integration evidence does not claim new-head GitHub Actions
results, a final review verdict, or the final PR #17-to-main merge SHA. Those
outcomes can be recorded only after this branch is pushed and the hosted gates
finish. The existing draft pull-request URL is not evidence of those outcomes.

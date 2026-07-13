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

## Authoritative isolated gate

Every actual `tests/test_*.py` module was executed serially in a fresh Python
process. The observed summary was
`isolated_modules=111 tests=521 skips=3 failures=0`.

After the isolated module loop, `py -m compileall -q src tests`,
`py -m unit_test_runner --help`, and `git diff --check` each exited
successfully. The CLI help exposed the expected command surface through
`suite-run`.

## Local compiler limitation

`Get-Command gcc, clang, cc -ErrorAction SilentlyContinue` found no supported
host compiler (`fixture_compiler=not_found`). Consequently, the local VC6
fixture E2E result is the single compiler-required skip recorded above. This
local result does not substitute for the compiler-required GitHub fixture job.

## Publication boundary

The pull-request URL, GitHub Actions URLs, review verdict, and merge SHA exist
only after publication and are not claimed by this pre-publication record.

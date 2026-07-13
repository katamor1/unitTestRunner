# Windows 8.3 Remote Gate Follow-up Implementation Plan

> **Execution rule:** implement this follow-up with TDD and fresh implementer/reviewer separation. Do not modify TEMP/TMP, weaken artifact containment, or enter Phase 1 Task 6 product work.

**Goal:** Close the three deterministic Windows 8.3 alias gaps exposed by both Python jobs on PR #18, then restore a fully green local and hosted integration gate.

**Remote evidence:** Push run `29287642448` and pull-request run `29287654802` used the same head `9d9229e`, each ran 532 tests, and each ended with `failures=1, errors=5`. All seven `tests.test_windows_path_alias_regression` tests ran as `ok` with `UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS=1`; the anti-skip gate is working. The failures are therefore deterministic residual alias handling, not an unavailable alias or a flaky runner.

**Failure families:**

1. `tests/test_execution_evidence.py:223` applies lexical `Path.relative_to` to a long report path and short workspace path that name the same directory.
2. `tests/test_prepare_evidence_non_destructive.py:283` compares the same report through short and long `Path` spellings.
3. `src/unit_test_runner/cli/commands.py::_test_spec_view_artifact_root` treats a short custom-view path inside a long canonical workspace as an external output. This collapses the produced artifact path from `reports/writer-a.*` or `custom-views/writer-a.*` to `writer-a.*`, causing four writer-snapshot subtest errors.

**Security invariant:** `_test_spec_view_artifact_root` must keep lexical containment as the first decision. Only after lexical mismatch may it test physical containment with the strict `resolved_relative_to` primitive. A genuinely external custom output must keep its lexical parent as the independent root, and `build_produced_artifact` must continue rejecting resolved escapes.

---

### Follow-up Task A: Reproduce and close the remaining result-path aliases

**Files:**
- Modify: `tests/test_execution_evidence.py`
- Modify: `tests/test_prepare_evidence_non_destructive.py`
- Modify: `tests/test_test_spec_formal_review_writer_snapshots.py`
- Modify: `src/unit_test_runner/cli/commands.py`

**Keeps unchanged:**
- `tests/windows_path_alias_support.py` public fixture contract
- all seven existing dedicated alias tests
- external custom-view artifact-root behavior
- `build_produced_artifact` containment and reparse/escape rejection
- test inventory: 112 modules and 532 test methods

- [ ] **Step 1: Make the three existing failing methods reproduce real aliases locally**

In each of the three test modules, import:

~~~python
from tests.windows_path_alias_support import (
    WINDOWS_8DOT3_PREFIX,
    require_windows_path_alias_pair,
)
~~~

Use `TemporaryDirectory(prefix=WINDOWS_8DOT3_PREFIX)` in the affected method. On Windows, obtain a real pair and use `pair.short` as the temporary root/workspace spelling; on non-Windows, retain `Path(temp_dir)`. Do not change the failing assertion or product code yet.

For `test_cli_run_tests_prepare_evidence_and_analyze_function_connect_execution_evidence`, pass the selected root to `prepare_workspace`.

For `test_prepare_evidence_cli_reports_the_explicit_older_source_run`, use the selected root as `workspace`.

For `test_explicit_custom_views_render_writer_a_snapshot_and_inventory`, build `out` below the selected root for all four `md/csv x reports/separate` subtests.

- [ ] **Step 2: Run the exact local RED**

~~~powershell
$env:UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS = '1'
py -m unittest tests.test_execution_evidence tests.test_prepare_evidence_non_destructive tests.test_test_spec_formal_review_writer_snapshots -v
~~~

Expected: 23 tests run with exactly the same six failing outcomes as both hosted jobs: one execution-evidence `ValueError`, one prepare-evidence raw-path assertion failure, and four writer-snapshot `FileNotFoundError` subtests. All other tests pass and no alias fixture skips.

- [ ] **Step 3: Correct the two identity-only test assertions**

In `tests/test_execution_evidence.py`, compare the resolved report and workspace before taking the relative path:

~~~python
self.assertEqual(
    "runs",
    run_report_path.resolve().relative_to(workspace.resolve()).parts[0],
)
~~~

In `tests/test_prepare_evidence_non_destructive.py`, compare resolved physical identity:

~~~python
self.assertEqual(
    (workspace / "runs" / "run-older" / "test_execution_report.json").resolve(),
    Path(execution["json"]).resolve(),
)
~~~

These are test-only identity corrections. Do not change the product return values.

- [ ] **Step 4: Preserve lexical-first trust, then recognize a physical workspace alias**

In `src/unit_test_runner/cli/commands.py`, import `resolved_relative_to`.

Keep the current lexical `relative_to` check first. In its `except ValueError` branch, attempt strict physical containment:

~~~python
    try:
        lexical_path.relative_to(lexical_workspace)
    except ValueError:
        try:
            resolved_relative_to(lexical_path, lexical_workspace)
        except ValueError:
            # A genuine external --out remains independently rooted. The
            # artifact builder still rejects a reparse redirect outside it.
            return lexical_path.parent
    return lexical_workspace
~~~

Do not catch or soften errors inside `resolved_relative_to` itself. Do not change `build_produced_artifact`.

- [ ] **Step 5: Run focused GREEN and security/fallback regressions**

~~~powershell
$env:UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS = '1'
py -m unittest tests.test_execution_evidence tests.test_prepare_evidence_non_destructive tests.test_test_spec_formal_review_writer_snapshots tests.test_test_spec_formal_review_export_atomicity tests.test_cli_artifact_references tests.test_windows_path_alias_regression -v
py -m compileall -q src tests
git diff --check
~~~

Expected: 53 tests pass with zero skips in the alias-backed methods. The existing external custom-view test must still report only the file name relative to its external parent, and artifact escape tests must remain green.

- [ ] **Step 6: Commit and obtain an independent task review**

~~~powershell
git add -- tests/test_execution_evidence.py tests/test_prepare_evidence_non_destructive.py tests/test_test_spec_formal_review_writer_snapshots.py src/unit_test_runner/cli/commands.py
git diff --cached --check
git commit -m "fix: close remaining Windows alias result paths"
~~~

Review requirements: plan compliance approved; Critical 0; Important 0; lexical-first/external fallback and all six hosted failure outcomes explicitly checked.

---

## Re-entry Integration Gate

1. Run all 112 tracked `tests/test_*.py` modules in separate fresh Python processes with `UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS=1` and continue after failures.
2. Require 532 tests, the exact three local compiler skips, zero failures/errors/nonzero exits/parse failures, and seven dedicated alias tests non-skipped.
3. Run `py -m compileall -q src tests`, `py -m unit_test_runner --help`, and `git diff --check origin/main..HEAD`.
4. Obtain a fresh whole-branch review for `origin/main..HEAD` with plan compliance approved, Critical 0, and Important 0.
5. Push the existing `codex/windows-83-path-alias` branch; do not force-push.
6. Require every push and pull-request check on PR #18 to pass. Confirm the Python log shows `Ran 532 tests`, `OK`, all seven alias tests non-skipped, and none of the six former failures.
7. Confirm the VC6 compiler-backed E2E remains non-skipped, mark PR #18 ready, and merge with a merge commit only after the complete gate is green.

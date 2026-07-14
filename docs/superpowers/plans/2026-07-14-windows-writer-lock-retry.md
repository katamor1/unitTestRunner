# Windows Writer Lock Retry Hotfix Plan

> **Execution rule:** use TDD, preserve the TestSpec revision/atomicity contracts, and do not enter Phase 1 Task 6 until the hotfix is merged and the new `main` push is green.

**Goal:** remove the intermittent Windows `PermissionError(13)` exposed by post-merge run `29347466880` without weakening non-Windows permission failures or transaction rollback behavior.

**Evidence:** the hosted failure captured one worker `PermissionError` but discarded its traceback. Local stress independently reproduces Windows sharing denials both while exclusively creating `.test_spec.json.lock` and while replacing canonical `test_spec.json`. The current lock loop retries only `FileExistsError`, and all TestSpec atomic replacements are single-attempt operations.

## Task A: Add deterministic regressions

- [x] Inject one-shot Windows sharing denials into lock creation and deletion, and require bounded retry plus lock cleanup.
- [x] Inject a one-shot Windows sharing denial into canonical JSON replacement and require a valid saved artifact with no temporary residue.
- [x] Inject a one-shot Windows sharing denial into fixed CSV view replacement and require a consistent Markdown/CSV pair with no residue.
- [x] Change the concurrent snapshot test to re-raise the captured worker exception so hosted logs retain its original traceback.
- [x] Run the focused tests and record the expected RED failures before product changes.

## Task B: Implement the bounded Windows-only retry

- [x] Add a small shared predicate for Windows `PermissionError` sharing denials.
- [x] Retry transient lock-create denials within the existing lock deadline while keeping `FileExistsError` timeout behavior.
- [x] Route canonical JSON and all TestSpec view replacements through a short bounded retry helper.
- [x] Keep POSIX permission failures and non-permission `OSError` failures immediate.
- [x] Preserve rollback and temporary-file cleanup behavior.

## Task C: Verify and integrate

- [x] Pass repository, writer-snapshot, and export-atomicity focused tests, including repeated two-writer stress.
- [x] Pass `compileall`, CLI help, and `git diff --check`.
- [x] Obtain an independent whole-diff review with Critical 0 and Important 0.
- [ ] Run the strict 112-module isolated gate and require 543 tests with only the three expected local compiler skips.
- [ ] Push a dedicated hotfix PR, require all hosted checks green, merge, and confirm the resulting `main` push is green.
- [ ] Only then write the Phase 1 Task 6 execution plan and resume the 38-task roadmap.

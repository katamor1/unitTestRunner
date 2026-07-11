# Unit Test Runner Phase 0 Main Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore an importable CLI and a deterministic all-green baseline before deeper contract or VC6 refactoring.

**Architecture:** Repair the incomplete dependency-policy merge at its source, then consolidate extension activation and remove platform-dependent path behavior. Resolve the known residual failures according to the safer intended contract and split CI so Python and VS Code always report independently.

**Tech Stack:** Python 3.12, `unittest`, TypeScript 5.4, Node.js 20 test runner, VS Code 1.85, GitHub Actions Windows runner.

## Global Constraints

- Do not revert the dependency-policy dispatcher or DSP/LIB resolution to recover the build.
- Do not change runner parsing to treat a bare `UTR RUN` marker as passed.
- Do not preserve lossy aggregate-to-`int` behavior merely to satisfy stale snapshots.
- Keep product sources read-only and verify their hashes in the dependency rewriter E2E.
- Every task must leave its focused test set GREEN before commit.

---

### Task 1: Repair source tracking and restore `dependency_rewriter.py`

**Files:**

- Modify: `.gitignore`
- Create: `src/unit_test_runner/build/dependency_rewriter.py`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_dependency_call_rewriter.py`
- Test: `tests/test_ci_contract.py`
- Test: `tests/test_dependency_policy_end_to_end.py`

**Interfaces:**

- Produces: `rewrite_dependency_calls(source: str, dispatches: list[dict[str, Any]]) -> tuple[str, list[str]]`
- Consumes: `dispatches[*].callee`, `dispatcher_name`, and 1-based `rewrite_sites[*].start/end` positions from `harness_skeleton_report.json`.
- Safety result: any mismatch is returned as a structured error; mismatched text is never rewritten and build generation becomes `blocked`.

- [x] **Step 1: Add a failing repository-ignore contract**

Add a CI-contract test that runs:

```python
completed = subprocess.run(
    ["git", "check-ignore", "--no-index", "-q", "src/unit_test_runner/build/dependency_rewriter.py"],
    cwd=REPO_ROOT,
)
self.assertNotEqual(0, completed.returncode)
```

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_ci_contract -v
```

Expected: FAIL because `.gitignore:40` contains unanchored `build/`.

- [x] **Step 2: Anchor build-output ignore rules**

Replace generic repository-wide entries with explicit output roots:

```gitignore
/.venv-release/
/build/
/dist/
vscode/extension/dist/
```

Run the test again. Expected: PASS.

- [x] **Step 3: Extend the rewriter regression tests**

Add cases for CRLF, two reverse-ordered replacements on one line, duplicate include suppression, mismatched callee text, member calls, and macro/address uses. Exact direct calls must change; all other uses must remain byte-for-byte unchanged.

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_dependency_call_rewriter -v
```

Expected: import failure before the file is created.

- [x] **Step 4: Implement the minimal position-checked rewriter**

The implementation must return structured issues:

```python
@dataclass(frozen=True)
class DependencyRewriteIssue:
    call_id: str
    code: str
    message: str
    severity: Literal["error"] = "error"

def rewrite_dependency_calls(
    source: str,
    dispatches: list[dict[str, Any]],
) -> tuple[str, list[DependencyRewriteIssue]]:
    edits: list[tuple[int, int, str]] = []
    issues: list[str] = []
    # Convert 1-based line/column pairs to offsets.
    # Verify source[start:end] equals the declared callee.
    # Reject overlaps and apply valid edits in descending start order.
    # Add utr_dependency_dispatch.h exactly once only when an edit succeeds.
    return rewritten, issues
```

Run focused rewriter and dependency E2E tests. Expected: PASS, and product source hashes unchanged.

Update `_rewrite_target_dependency_calls()` so any rewrite issue produces an error diagnostic, sets build workspace status to `blocked`, and prevents compile/run. Add an E2E where a `stub` policy has a mismatched site and assert the real callee is never executed.

- [x] **Step 5: Add a tracked-source preflight to CI**

Before Python tests, add a step that verifies the file exists in `git ls-files` and that `python -m compileall -q src` succeeds.

- [x] **Step 6: Commit**

```bash
git add .gitignore .github/workflows/ci.yml src/unit_test_runner/build/dependency_rewriter.py tests/test_dependency_call_rewriter.py tests/test_ci_contract.py
git commit -m "fix: restore dependency call rewriter and source tracking"
```

---

### Task 2: Replace the cascading baseline with the real failure inventory

**Files:**

- Modify: `docs/superpowers/plans/2026-07-11-unit-test-runner-phase-0-main-recovery.md` (verification record only)
- Test: all `tests/test_*.py`

**Interfaces:** None; this task establishes evidence for Tasks 3-5.

- [x] **Step 1: Run the complete Python suite**

```bash
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
```

Expected after Task 1: no `ModuleNotFoundError`; approximately 250 tests discovered. Record exact failures without changing production code.

- [x] **Step 2: Run TypeScript tests**

```bash
cd vscode/extension
npm ci
npm test
```

Expected on the current Linux diagnostic environment: compile succeeds, 38 pass and 5 Windows-path tests fail. Record platform and Node version.

- [x] **Step 3: Confirm CLI startup**

```bash
PYTHONPATH=src python -m unit_test_runner --help
PYTHONPATH=src python -m unit_test_runner --json discover-projects --workspace tests/fixtures/vc6_project
```

Expected: both exit 0 and JSON stdout contains no traceback.

No commit is required unless the verification record is updated.

Verification record (2026-07-11, Linux, Python 3.12.13, Node 24.14.0):

- Python discovery reached 258 tests: 6 failures, 1 Linux-only `cmd.exe` error, and 1 skip. There were no import errors.
- VS Code compilation succeeded; 43 tests ran: 38 passed and 5 failed on Windows-path interpretation.
- `unit_test_runner --help` and JSON `discover-projects` both exited 0 without a traceback.
- npm 11.9.0 required a writable `--cache /tmp/unit-test-runner-npm-cache` in the sandbox; this was an environment setup issue rather than a product failure.

---

### Task 3: Consolidate VS Code activation and command registration

**Files:**

- Modify: `vscode/extension/package.json`
- Modify: `vscode/extension/src/extension.ts`
- Create: `vscode/extension/src/commands/quickCommands.ts`
- Create: `vscode/extension/src/commands/commandRegistry.ts`
- Create: `vscode/extension/src/test/runTest.ts`
- Create: `vscode/extension/src/test/extensionHost/index.ts`
- Delete: `vscode/extension/src/quickExtension.ts`
- Modify: `tests/test_vscode_adapter.py`
- Modify: `vscode/extension/src/test/adapter.test.ts`
- Modify: `vscode/extension/src/test/quickCheck.test.ts`

**Interfaces:**

- Produces: `registerUnitTestRunnerCommands(context, dependencies): vscode.Disposable[]`
- Produces: `registerQuickCommands(registry, dependencies): void`
- Invariant: every `package.json` command ID is registered exactly once by `extension.activate()`.

- [x] **Step 1: Write an exactly-once command manifest test**

Parse `package.json`, collect command IDs, inject a recording registry into `registerUnitTestRunnerCommands`, and assert a count of one for every ID. Include `openGeneratedTestSource`, which is currently registered twice.

- [x] **Step 2: Write top-level Quick profile tests**

Invoke the actual Quick command handler with each profile and assert phases:

```text
design        -> design
harness       -> harness
build-dry-run -> build
```

The test must fail if the handler overwrites the selected profile.

- [x] **Step 3: Move Quick handlers under the core activation path**

Set:

```json
"main": "./dist/extension.js"
```

Move Quick command handlers into `commands/quickCommands.ts`, use the core output channel and workspace state, and remove `quickExtension.ts`.

Because the resolver and Python analyzer currently implement C identifiers rather than C++ overload/member identity, restrict v1 editor menu/activation conditions to `editorLangId == c`. Document C++ as unsupported instead of advertising a false contract.

- [ ] **Step 4: Run manifest, compile, and unit tests**

Add `@vscode/test-electron`, an `npm run test:extension-host` script, and an Extension Host smoke test that awaits activation, asserts `extension.isActive`, enumerates expected commands, and deactivates without error.

```bash
PYTHONPATH=src python -m unittest tests.test_vscode_adapter -v
cd vscode/extension && npm test
cd vscode/extension && npm run test:extension-host
```

Expected: manifest entrypoint contract passes, activation succeeds, and no duplicate command exists.

Local manifest, compile, and unit-test coverage passed. The Extension Host harness was compiled, but its runtime launch requires a display server unavailable in the Linux execution environment; the Windows `vscode-activation` job remains the required completion evidence.

- [x] **Step 5: Commit**

```bash
git add vscode/extension/package.json vscode/extension/src tests/test_vscode_adapter.py
git commit -m "refactor: use one VS Code activation entrypoint"
```

---

### Task 4: Make Windows path behavior explicit and platform-independent

**Files:**

- Create: `vscode/extension/src/platform/pathDialect.ts`
- Modify: `vscode/extension/src/config/validation.ts`
- Modify: `vscode/extension/src/cli/cliResultParser.ts`
- Modify: `vscode/extension/src/reports/reportPathResolver.ts`
- Modify: `vscode/extension/src/test/adapter.test.ts`
- Modify: `vscode/extension/src/test/quickCheck.test.ts`
- Modify: `tests/test_cli_entry_point_contract.py`
- Modify: `tests/test_build_output_encoding.py`

**Interfaces:**

```typescript
export function pathDialect(value: string): typeof path.win32 | typeof path.posix;
export function isPathInside(candidate: string, root: string): boolean;
export function resolveReportedPath(value: string, workspace: string): string;
```

- [x] **Step 1: Add drive, UNC, POSIX, and mixed-separator tests**

Use explicit `C:\\work`, `\\\\server\\share`, and `/work` cases. Test behavior, not the host OS result.

- [x] **Step 2: Implement dialect selection**

Select `path.win32` for drive/UNC values and `path.posix` for POSIX-rooted values. Resolve a relative report path against the workspace; retain an already absolute reported path.

- [x] **Step 3: Correct platform-specific Python tests**

- Build the absolute-source assertion from `relative_to(workspace)` rather than joining an absolute path to `out_dir`.
- Decorate the `cmd.exe` execution test with `@unittest.skipUnless(os.name == "nt", "Windows command-shell contract")` and retain a platform-neutral encoding-unit test.

- [ ] **Step 4: Run on Linux and Windows CI**

Expected: the five current TypeScript path failures pass on both platforms; the Windows-only Python test skips only on non-Windows.

Linux verification passed. Windows verification remains pending on the recovery PR.

- [x] **Step 5: Commit**

```bash
git add vscode/extension/src tests/test_cli_entry_point_contract.py tests/test_build_output_encoding.py
git commit -m "fix: make Windows path contracts platform independent"
```

---

### Task 5: Resolve the known Python contract drift safely

**Files:**

- Modify: `src/unit_test_runner/harness/parameter_init_compat.py`
- Modify: `src/unit_test_runner/harness/target_invocation_compat.py`
- Create: `src/unit_test_runner/harness/type_bridge.py`
- Modify: `src/unit_test_runner/reports/japanese.py`
- Modify: `tests/test_build_probe_env_include_fix.py`
- Modify: `tests/test_execution_evidence.py`
- Modify: `tests/test_harness_report_localization.py`
- Modify: `tests/test_target_invocation_compat.py`

**Interfaces:**

- `classify_bridge_type(type_text, defining_headers)` must not map a known complete aggregate typedef to `int`.
- Generated `target_invocation.h` must include the header that defines a typedef used in its public prototype.
- Bare `UTR RUN` without OK/FAILED/SKIPPED remains inconclusive.

- [x] **Step 1: Preserve aggregate declarations in generated tests**

Add the minimal shared type-classification result in `harness/type_bridge.py`, distinguishing scalar, aggregate, pointer, and unresolved types. For a known aggregate value parameter, generate:

```c
gbl_input prm = {0};
```

Do not emit assignment from `TBD_VALID_INT_VALUE`.

- [x] **Step 2: Include typedef-defining headers in the public target bridge**

When `DWORD` or another resolved typedef appears in `target_invocation.h`, include the same verified product header in the header, not only in `target_invocation.c`.

- [x] **Step 3: Complete user-facing localization**

Add the missing stable translation for the generated-test approval warning. Keep machine enum fields unchanged; localize only render output.

- [x] **Step 4: Update the stale bare-RUN parser test**

Change the expected result to `inconclusive`/low confidence and add a companion `UTR RUN` + `UTR OK` case that is passed.

- [x] **Step 5: Run focused and full Python tests**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_build_probe_env_include_fix \
  tests.test_target_invocation_compat \
  tests.test_harness_report_localization \
  tests.test_execution_evidence -v
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
```

Expected on Windows: all tests pass. Expected on non-Windows: only explicitly Windows-native tests skip.

- [x] **Step 6: Commit**

```bash
git add src/unit_test_runner/harness src/unit_test_runner/reports tests
git commit -m "fix: align generated type and runner contracts"
```

---

### Task 6: Split and strengthen CI gates

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_ci_contract.py`
- Create: `tests/test_repository_source_tracking.py`

**Interfaces:** Five independent jobs: `source-integrity`, `python-tests`, `vscode-tests`, `vscode-activation`, and `fixture-smoke`.

- [x] **Step 1: Split the current sequential job**

Ensure Python failure does not skip Node setup/tests. Give every job a distinct required-check name.

The `vscode-activation` job installs dependencies and runs `npm run test:extension-host` on Windows. It is a required check, not an optional local command.

Add `workflow_dispatch` alongside push/pull_request. After pushing the recovery PR, verify repository Actions are enabled/approved and all five checks are created; the GitHub connector returned no workflow run for current merge commit `ec85f0f`, so “workflow file exists” is not sufficient evidence.

- [x] **Step 2: Add source-integrity checks**

Run `git ls-files`, `git check-ignore --no-index`, Python `compileall`, and TypeScript compile. Assert all imported local modules are tracked.

- [x] **Step 3: Add a non-executing fixture smoke**

Run `discover-projects`, `map-source`, and `analyze-function --phase design` against `tests/fixtures/vc6_project`; assert the CLI envelope is valid and generated paths exist.

- [x] **Step 4: Preserve full logs and test counts**

Upload test logs only on failure. Do not convert failed tests into `continue-on-error`.

- [ ] **Step 5: Run the workflow on a recovery PR**

Expected: all five jobs execute even if one fails; after Tasks 1-5, all are GREEN.

- [x] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml tests/test_ci_contract.py tests/test_repository_source_tracking.py
git commit -m "ci: split source Python VS Code and fixture gates"
```

---

### Task 7: Correct file-scope object-definition detection and add host build E2E

**Files:**

- Create: `src/unit_test_runner/c_analyzer/object_definition_finder.py`
- Modify: `src/unit_test_runner/dependency_policy/analyzer.py`
- Modify: `src/unit_test_runner/build/build_workspace_generator.py`
- Modify: `tests/test_build_workspace_extern_globals.py`
- Modify: `tests/test_dependency_external_object_binding.py`
- Create: `tests/test_vc6_fixture_build_e2e.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ObjectDefinition:
    name: str
    type_text: str
    storage_class: str | None
    line: int
    is_tentative: bool

def find_file_scope_object_definitions(source_text: str) -> list[ObjectDefinition]: ...
```

- [x] **Step 1: Reproduce the `g_error_code` link failure**

Add a fixture test in which a header declares `extern int g_error_code;` and the target function assigns to it. Assert that an assignment is not an object definition and that the generated fixture defines the object exactly once.

- [x] **Step 2: Add true-definition edge cases**

Cover `int g;`, `int g = 1;`, `static int g;`, arrays, brace initializers, declarations inside functions, comments, and macros. Only brace-depth-zero object declarations count.

- [x] **Step 3: Implement and share the finder**

Replace `_target_source_defines_name()` and dependency-policy definition scanning with the shared file-scope finder. Do not use a name-plus-assignment regex.

- [x] **Step 4: Add default fixture host build E2E**

Run the public CLI over `tests/fixtures/vc6_project` through `analyze-function --phase build`, then run `build-probe --toolchain verification --run`. Assert successful compile/link, one generated `g_error_code` definition, no fixture conflict/missing diagnostic, and unchanged product-tree hashes.

- [x] **Step 5: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_build_workspace_extern_globals \
  tests.test_dependency_external_object_binding \
  tests.test_vc6_fixture_build_e2e -v
git add src/unit_test_runner/c_analyzer src/unit_test_runner/dependency_policy src/unit_test_runner/build tests
git commit -m "fix: distinguish external object definitions from assignments"
```

---

### Task 8: Stop returning success for a non-PASS test run

**Files:**

- Modify: `src/unit_test_runner/cli/commands.py`
- Modify: `src/unit_test_runner/cli/exit_codes.py`
- Modify: `tests/test_execution_evidence.py`
- Modify: `tests/test_cli_entry_point_contract.py`
- Create: `tests/test_cli_execution_outcome.py`

**Interfaces:**

```python
def legacy_execution_exit(
    status: Literal["planned", "passed", "failed", "blocked", "inconclusive", "cancelled", "timed_out", "error"],
    executed: bool,
) -> tuple[str, int]:
    # passed -> ("tests_passed", 0)
    # failed -> ("tests_failed", 32)
    # timed_out -> ("tests_timed_out", 34)
    # blocked/inconclusive -> ("tests_blocked", 30)
    # cancelled -> ("tests_cancelled", 36)
    # no execution requested -> ("evidence_prepared", 0)
```

This is the immediate v0.1 safety fix. Phase 1 replaces it with the versioned outcome envelope and granular codes.

- [x] **Step 1: Write table-driven status/exit tests**

Assert both process return code and JSON `exit_code` for `passed`, `failed`, `timed_out`, `blocked`, `inconclusive`, `cancelled`, and `planned` cases.

- [x] **Step 2: Promote report status in `handle_run_tests()`**

Remove unconditional `EXIT_OK`. Never infer PASS merely from `executed=True`.

- [x] **Step 3: Add a negative E2E assertion**

Use the current fixture with unresolved/TBD expectations and assert its internal failed status produces a nonzero CLI result. Do not claim this fixture is a valid GREEN test; Phase 2 adds the reviewed-oracle GREEN E2E.

- [x] **Step 4: Run and commit**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_execution_evidence tests.test_cli_entry_point_contract \
  tests.test_cli_execution_outcome -v
git add src/unit_test_runner/cli tests
git commit -m "fix: propagate test outcomes to CLI exit codes"
```

---

## Phase 0 Completion Check

Run fresh:

```bash
PYTHONPATH=src python -m compileall -q src tests
PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py" -v
cd vscode/extension && npm ci && npm test
```

Then confirm:

- [x] `git status --short` contains only intended changes.
- [x] `git ls-files src/unit_test_runner/build/dependency_rewriter.py` returns the file.
- [x] `python -m unit_test_runner --help` exits 0.
- [x] No command ID is registered more than once.
- [x] Default fixture host compile/link succeeds without an unresolved external.
- [x] A failed, timed-out, blocked, inconclusive, or cancelled execution does not return exit 0.
- [ ] All GitHub Actions jobs ran and are GREEN.
- [x] The verification record states exact pass/skip counts and operating system.

Verification record (2026-07-11, Linux 6.12.47 x86_64, Python 3.12.13, Node 24.14.0, npm 11.9.0):

- `compileall` passed for `src` and `tests`.
- Python discovery ran 274 tests: all passed, with 2 expected platform skips.
- VS Code compilation and unit tests ran 51 tests: all passed, with 0 skips.
- The public CLI fixture E2E compiled and linked the generated host test binary without an unresolved external and preserved product-tree hashes.
- The negative execution fixture returned a nonzero CLI and JSON exit code; table-driven coverage confirms nonzero results for failed, timed-out, blocked, inconclusive, cancelled, error, and unknown terminal states.
- `unit_test_runner --help` exited 0, `dependency_rewriter.py` is tracked, and the exactly-once command-manifest test passed.
- Windows path and Extension Host runtime verification remains pending until the branch is pushed and all five GitHub Actions jobs run.

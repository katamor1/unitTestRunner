# Windows 8.3 Path Alias Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Merge a prerequisite pull request that makes product path handling correct for equivalent Windows long and 8.3 short paths, restores all six GitHub checks to GREEN, and then lets maintenance-only PR #17 update and merge without hiding the product defect.

**Architecture:** Add one strict physical-relative primitive that resolves both operands and never hides containment failures. Use the new primitive only at three contract boundaries: build inventory recording, explicit executable relativization, and TestSpec canonical-path identity after the existing lexical/reparse authorization. Tests obtain real long/short aliases through GetLongPathNameW followed by GetShortPathNameW, exercise both directions, and make alias absence a hard failure in GitHub Actions while allowing an explicit local skip when the volume has no short names.

**Tech Stack:** Python 3.12 on GitHub Actions, Python 3.13 locally, pathlib, ctypes Win32 file APIs, unittest, PowerShell, Git worktrees.

## Global Constraints

- Work only in C:\Users\stell\source\repos\unitTestRunner-win83 on branch codex/windows-83-path-alias.
- Do not modify, unstage, commit, or delete user-owned files in C:\Users\stell\source\repos\unitTestRunner.
- Do not modify the existing PR #17 worktree while this prerequisite branch is under implementation.
- The prerequisite starts from origin/main at b66790165a2d4f82943cd199b3b499e1f1725fc3.
- Reuse the already-reviewed test-only contract correction from commit 1c039f308d4c10a71ed7ae2fc1756349f3978d3b so this prerequisite can become independently GREEN. After this prerequisite merges, merge origin/main into PR #17; the identical file content must disappear from its effective diff.
- Keep canonical contract paths normalized and workspace-relative. Do not make absolute paths valid contract output.
- Keep the existing TestSpec order: lexical shape and authority checks first, then symlink/junction/reparse checks, then physical identity or containment checks. A resolve-based comparison must never replace lexical authorization.
- Preserve the existing workspace-escape and symlink/reparse rejection behavior.
- Do not change TEMP, TMP, or TMPDIR to mask the defect.
- Do not call fsutil or alter host 8.3-name policy.
- Do not add Phase 1 Task 6 product behavior, carrier payloads, or materialization workflow code.
- Every production change requires observed RED before implementation and focused GREEN afterward.
- Every task requires a fresh task review with both spec-compliance and code-quality approval. The complete branch requires a whole-branch review with Critical 0 and Important 0 before publication.

---

### Task 1: Import the two current-contract baseline assertions

**Files:**
- Modify: tests/test_test_spec_consumers.py
- Modify: tests/test_vc6_fixture_build_e2e.py

**Interfaces:**
- Consumes: canonical TestSpec envelope values and CLI result envelope 1.0.0 already established on main.
- Produces: the same test-only correction currently carried by PR #17 commit 1c039f3, without importing its CI workflow or evidence documents.

- [ ] **Step 1: Preserve the observed baseline evidence**

The controller has already run:

~~~powershell
py -m unittest discover -s tests -p 'test_*.py' -v
~~~

Observed at b667901 on this host: 521 tests, one failure, three skips. The only local failure was the stale literal spec_id assertion in tests.test_test_spec_consumers. GitHub main run 29187107516 additionally proved the old VC6 CLI status lookup raises KeyError after a successful probe. Record these facts in the task report; do not manufacture a second baseline result.

- [ ] **Step 2: Reproduce the local TestSpec RED**

~~~powershell
py -m unittest tests.test_test_spec_consumers -v
~~~

Expected: exactly test_canonical_envelope_is_normalized_to_consumer_data_and_views_are_rejected fails because spec-control-update differs from spec-fn_control_update_cdd351ecf31d.

- [ ] **Step 3: Cherry-pick only the reviewed assertion correction**

~~~powershell
git cherry-pick 1c039f308d4c10a71ed7ae2fc1756349f3978d3b
git show --stat --oneline HEAD
~~~

Expected changed files: tests/test_test_spec_consumers.py and tests/test_vc6_fixture_build_e2e.py only.

- [ ] **Step 4: Run focused GREEN verification**

~~~powershell
py -m unittest tests.test_test_spec_consumers tests.test_cli_result_contract tests.test_vc6_fixture_build_e2e -v
git diff --check HEAD^ HEAD
~~~

Expected locally: TestSpec consumer and CLI-result tests pass; the compiler-backed VC6 test either passes with an available compiler or reports its existing compiler skip; the diff check exits 0.

- [ ] **Step 5: Review Task 1**

Generate a review package from b667901 to the cherry-pick head. The reviewer must confirm both public-envelope expectations are current, no product code entered the task, and the effective patch matches commit 1c039f3.

---

### Task 2: Add real Windows alias fixtures and a strict relative primitive

**Files:**
- Create: tests/windows_path_alias_support.py
- Create: tests/test_windows_path_alias_regression.py
- Modify: src/unit_test_runner/path_utils.py

**Interfaces:**
- Produces: resolved_relative_to(path: Path | str, root: Path | str) -> Path.
- Produces: WindowsPathAliasPair(original, long, short) for real existing directories.
- Keeps unchanged: normalize_relative(path, root) -> str with its existing non-throwing external-path fallback.

- [ ] **Step 1: Create the reusable Windows test fixture**

Create tests/windows_path_alias_support.py with:

~~~python
from __future__ import annotations

import ctypes
import os
import unittest
from dataclasses import dataclass
from pathlib import Path


WINDOWS_8DOT3_REQUIRED_ENV = "UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS"
WINDOWS_8DOT3_PREFIX = "unitTestRunner Windows 8dot3 alias "


class WindowsPathAliasUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WindowsPathAliasPair:
    original: Path
    long: Path
    short: Path


def _call_windows_path_api(function_name: str, path: Path) -> Path:
    if os.name != "nt":
        raise OSError("Windows path aliases require Windows.")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = getattr(kernel32, function_name)
    function.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
    ]
    function.restype = ctypes.c_uint32
    path_text = os.path.abspath(os.fspath(path))
    capacity = max(260, len(path_text) + 1)
    while True:
        buffer = ctypes.create_unicode_buffer(capacity)
        written = function(path_text, buffer, capacity)
        if written == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        if written < capacity:
            return Path(buffer.value)
        capacity = written + 1


def windows_path_alias_pair(existing_dir: Path) -> WindowsPathAliasPair:
    original = Path(os.path.abspath(os.fspath(existing_dir)))
    if not original.is_dir():
        raise FileNotFoundError(original)
    long_path = _call_windows_path_api("GetLongPathNameW", original)
    short_path = _call_windows_path_api("GetShortPathNameW", long_path)
    if not long_path.is_dir() or not short_path.is_dir():
        raise AssertionError("Win32 path aliases must name existing directories.")
    if not os.path.samefile(long_path, short_path):
        raise AssertionError("Win32 long and short paths do not name the same directory.")
    long_key = os.path.normcase(os.path.normpath(os.fspath(long_path)))
    short_key = os.path.normcase(os.path.normpath(os.fspath(short_path)))
    if long_key == short_key:
        raise WindowsPathAliasUnavailable(
            f"No distinct Windows 8.3 alias exists for {long_path}"
        )
    return WindowsPathAliasPair(original, long_path, short_path)


def require_windows_path_alias_pair(
    test: unittest.TestCase,
    existing_dir: Path,
) -> WindowsPathAliasPair:
    try:
        return windows_path_alias_pair(existing_dir)
    except WindowsPathAliasUnavailable as error:
        if os.environ.get(WINDOWS_8DOT3_REQUIRED_ENV) == "1":
            test.fail(f"required Windows 8.3 alias unavailable: {error}")
        test.skipTest(str(error))
~~~

Do not call Path.resolve in this fixture. tempfile may already return RUNNER~1 on GitHub; converting original to long first is what makes both representations observable.

- [ ] **Step 2: Write the strict-relative RED tests**

Create tests/test_windows_path_alias_regression.py with policy tests plus these initial contract tests:

~~~python
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import unit_test_runner.path_utils as path_utils
from tests import windows_path_alias_support as alias_support


class WindowsPathAliasPolicyTests(unittest.TestCase):
    def test_required_mode_fails_when_alias_is_unavailable(self):
        error = alias_support.WindowsPathAliasUnavailable("disabled")
        with (
            mock.patch.dict(
                os.environ,
                {alias_support.WINDOWS_8DOT3_REQUIRED_ENV: "1"},
            ),
            mock.patch.object(
                alias_support,
                "windows_path_alias_pair",
                side_effect=error,
            ),
            self.assertRaises(AssertionError),
        ):
            alias_support.require_windows_path_alias_pair(self, Path("."))

    def test_optional_mode_skips_when_alias_is_unavailable(self):
        error = alias_support.WindowsPathAliasUnavailable("disabled")
        with (
            mock.patch.dict(
                os.environ,
                {alias_support.WINDOWS_8DOT3_REQUIRED_ENV: ""},
            ),
            mock.patch.object(
                alias_support,
                "windows_path_alias_pair",
                side_effect=error,
            ),
            self.assertRaises(unittest.SkipTest),
        ):
            alias_support.require_windows_path_alias_pair(self, Path("."))


class ResolvedRelativePathContractTests(unittest.TestCase):
    def test_strict_relative_primitive_is_public_and_rejects_outside_root(self):
        self.assertTrue(
            hasattr(path_utils, "resolved_relative_to"),
            "path_utils must expose resolved_relative_to",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            root = parent / "root"
            outside = parent / "outside.txt"
            root.mkdir()
            with self.assertRaises(ValueError):
                path_utils.resolved_relative_to(outside, root)


@unittest.skipUnless(os.name == "nt", "Windows 8.3 aliases require Windows")
class WindowsPathAliasIntegrationTests(unittest.TestCase):
    def _resolved_relative_to(self, path: Path, root: Path) -> Path:
        self.assertTrue(
            hasattr(path_utils, "resolved_relative_to"),
            "path_utils must expose resolved_relative_to",
        )
        return path_utils.resolved_relative_to(path, root)

    def test_helper_returns_distinct_existing_aliases_for_same_directory(self):
        with tempfile.TemporaryDirectory(
            prefix=alias_support.WINDOWS_8DOT3_PREFIX
        ) as temp_dir:
            pair = alias_support.require_windows_path_alias_pair(
                self, Path(temp_dir)
            )
            self.assertTrue(pair.long.is_dir())
            self.assertTrue(pair.short.is_dir())
            self.assertTrue(os.path.samefile(pair.long, pair.short))
            self.assertNotEqual(
                os.path.normcase(os.fspath(pair.long)),
                os.path.normcase(os.fspath(pair.short)),
            )

    def test_relative_path_accepts_long_child_under_short_root_alias(self):
        with tempfile.TemporaryDirectory(
            prefix=alias_support.WINDOWS_8DOT3_PREFIX
        ) as temp_dir:
            pair = alias_support.require_windows_path_alias_pair(
                self, Path(temp_dir)
            )
            (pair.long / "reports").mkdir()
            relative = self._resolved_relative_to(
                pair.long / "reports" / "test_spec.json",
                pair.short,
            )
            self.assertEqual(Path("reports/test_spec.json"), relative)

    def test_relative_path_accepts_short_child_under_long_root_alias(self):
        with tempfile.TemporaryDirectory(
            prefix=alias_support.WINDOWS_8DOT3_PREFIX
        ) as temp_dir:
            pair = alias_support.require_windows_path_alias_pair(
                self, Path(temp_dir)
            )
            (pair.long / "reports").mkdir()
            relative = self._resolved_relative_to(
                pair.short / "reports" / "test_spec.json",
                pair.long,
            )
            self.assertEqual(Path("reports/test_spec.json"), relative)
~~~

- [ ] **Step 3: Run Task 2 RED**

~~~powershell
$env:UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS = '1'
py -m unittest tests.test_windows_path_alias_regression -v
~~~

Expected: the strict-relative contract fails with path_utils must expose resolved_relative_to. Win32 helper and policy tests must not fail from setup or API misuse.

- [ ] **Step 4: Implement only the new strict primitive**

In src/unit_test_runner/path_utils.py add:

~~~python
def resolved_relative_to(path: Path | str, root: Path | str) -> Path:
    return Path(path).resolve(strict=False).relative_to(
        Path(root).resolve(strict=False)
    )
~~~

Do not change normalize_relative. Do not catch ValueError inside
resolved_relative_to. Strict callers rely on that exception to reject an
actual root escape.

- [ ] **Step 5: Run Task 2 GREEN and commit**

~~~powershell
$env:UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS = '1'
py -m unittest tests.test_windows_path_alias_regression -v
py -m compileall -q src tests
git diff --check
git add -- tests/windows_path_alias_support.py tests/test_windows_path_alias_regression.py src/unit_test_runner/path_utils.py
git diff --cached --check
git commit -m "test: establish Windows path alias contract"
~~~

Expected at this task boundary: six tests in tests.test_windows_path_alias_regression pass on this Windows host; compileall and both diff checks exit 0.

---

### Task 3: Relativize build inventory and explicit executables across aliases

**Files:**
- Modify: tests/test_artifact_provenance_hashes.py
- Modify: tests/test_windows_path_alias_regression.py
- Modify: src/unit_test_runner/build/build_report_writer.py
- Modify: src/unit_test_runner/execution/executable_resolver.py

**Interfaces:**
- Consumes: resolved_relative_to from Task 2.
- Produces: relative WorkspaceFile.workspace_path and ExecutableInfo.path for either long/short representation of the same workspace.
- Keeps: the existing fallback for an absolute executable physically outside the workspace; changing that public contract is out of scope.

- [ ] **Step 1: Write the build inventory regression**

Add this import to tests/test_artifact_provenance_hashes.py:

~~~python
from tests.windows_path_alias_support import (
    WINDOWS_8DOT3_PREFIX,
    require_windows_path_alias_pair,
)
~~~

Add this Windows-only test to ArtifactProvenanceHashTests:

~~~python
    @unittest.skipUnless(sys.platform == "win32", "Windows 8.3 aliases require Windows")
    def test_build_report_records_long_generated_path_under_short_output_alias(self):
        with tempfile.TemporaryDirectory(
            prefix=WINDOWS_8DOT3_PREFIX
        ) as temp_dir:
            pair = require_windows_path_alias_pair(self, Path(temp_dir))
            build = BuildWorkspaceReport(
                source_path=Path("src/control.c"),
                function_name="Control_Update",
                status="generated",
                output_root=pair.short,
                copied_files=[],
                referenced_files=[],
                generated_build_files=[],
                compile_units=[],
                link_units=[],
                include_dirs=[],
                defines=[],
                compiler_options=[],
                build_commands=[],
                diagnostics=[],
            )
            probe = BuildProbeReport(
                source_path=Path("src/control.c"),
                function_name="Control_Update",
                status="not_run",
                executed=False,
                exit_code=None,
                commands=[],
                diagnostics=[],
                missing_includes=[],
                unresolved_symbols=[],
                pch_issues=[],
                vc6_compatibility_issues=[],
                log_files=[],
            )
            try:
                write_build_reports(pair.short, build, probe)
            except ValueError as error:
                self.fail(f"long generated path must fit short output root: {error}")
            inventory = {
                item.workspace_path.as_posix()
                for item in build.generated_build_files
            }
            self.assertIn("build/UTR_Control_Update.dsp", inventory)
~~~

- [ ] **Step 2: Write the explicit executable regression**

Add this import to tests/test_windows_path_alias_regression.py:

~~~python
from unit_test_runner.execution.executable_resolver import resolve_executable
~~~

Add this method to WindowsPathAliasIntegrationTests:

~~~python
    def test_resolve_executable_relativizes_short_executable_under_long_workspace_alias(self):
        with tempfile.TemporaryDirectory(
            prefix=alias_support.WINDOWS_8DOT3_PREFIX
        ) as temp_dir:
            pair = alias_support.require_windows_path_alias_pair(
                self, Path(temp_dir)
            )
            executable = pair.long / "bin" / "utr_probe.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"fixture executable")
            info = resolve_executable(
                pair.long,
                pair.short / "bin" / "utr_probe.exe",
                {"function": {"status": "succeeded"}},
            )
            self.assertTrue(info.exists)
            self.assertEqual("bin/utr_probe.exe", info.path.as_posix())
~~~

- [ ] **Step 3: Run Task 3 RED**

~~~powershell
$env:UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS = '1'
py -m unittest tests.test_artifact_provenance_hashes tests.test_windows_path_alias_regression -v
~~~

Expected: the build regression fails through self.fail with long generated path must fit short output root, and the executable regression fails because ExecutableInfo.path is still absolute. Existing tests must remain passing.

- [ ] **Step 4: Apply the strict primitive at both boundaries**

In src/unit_test_runner/build/build_report_writer.py import:

~~~python
from unit_test_runner.path_utils import resolved_relative_to
~~~

Change _record_build_file to:

~~~python
    relative = resolved_relative_to(path, output_root)
~~~

In src/unit_test_runner/execution/executable_resolver.py import the same helper and replace the absolute branch with:

~~~python
    if path.is_absolute():
        absolute = path.resolve(strict=False)
        try:
            relative = resolved_relative_to(absolute, workspace)
        except ValueError:
            relative = path
~~~

Leave the relative-input branch unchanged.

- [ ] **Step 5: Run Task 3 GREEN and commit**

~~~powershell
$env:UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS = '1'
py -m unittest tests.test_artifact_provenance_hashes tests.test_windows_path_alias_regression tests.test_build_and_execution_module_boundaries tests.test_execution_evidence tests.test_execution_run_history tests.test_evidence_integrity tests.test_prepare_evidence_non_destructive -v
py -m compileall -q src tests
git diff --check
git add -- tests/test_artifact_provenance_hashes.py tests/test_windows_path_alias_regression.py src/unit_test_runner/build/build_report_writer.py src/unit_test_runner/execution/executable_resolver.py
git diff --cached --check
git commit -m "fix: normalize Windows aliases at build and execution boundaries"
~~~

Expected: all named modules pass; tests.test_windows_path_alias_regression now runs seven tests; compileall and diff checks exit 0.

---

### Task 4: Preserve TestSpec authority while accepting physical aliases

**Files:**
- Modify: tests/test_test_spec_repository.py
- Modify: tests/test_test_spec_generation.py
- Modify: tests/test_test_spec_reanalysis.py
- Modify: src/unit_test_runner/test_spec/repository.py

**Interfaces:**
- Consumes: assert_safe_canonical_test_spec_path and resolved_relative_to.
- Produces: the exact relative path reports/test_spec.json after lexical/reparse authorization.
- Keeps: root-to-canonical-leaf symlink/junction/reparse rejection, workspace escape rejection, and the existing lock-file symlink rejection.

- [ ] **Step 1: Add both TestSpec alias directions**

Add this import to tests/test_test_spec_repository.py:

~~~python
from tests.windows_path_alias_support import (
    WINDOWS_8DOT3_PREFIX,
    require_windows_path_alias_pair,
)
~~~

Add these methods to TestSpecRepositoryTests:

~~~python
    def _assert_alias_save(self, path_form: str, context_form: str):
        with tempfile.TemporaryDirectory(
            prefix=WINDOWS_8DOT3_PREFIX
        ) as temp_dir:
            pair = require_windows_path_alias_pair(self, Path(temp_dir))
            roots = {"long": pair.long, "short": pair.short}
            path = roots[path_form] / "reports" / "test_spec.json"
            try:
                artifact = save_test_spec(
                    path,
                    TestSpec.from_payload(copied_payload()),
                    expected_revision=None,
                    current_context=current_context(roots[context_form]),
                )
            except ValueError as error:
                self.fail(f"physical workspace aliases must be accepted: {error}")
            self.assertEqual("reports/test_spec.json", artifact.path)
            self.assertTrue(
                os.path.samefile(
                    pair.long / "reports" / "test_spec.json",
                    pair.short / "reports" / "test_spec.json",
                )
            )

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 aliases require Windows")
    def test_save_accepts_short_canonical_path_with_long_workspace_alias(self):
        self._assert_alias_save("short", "long")

    @unittest.skipUnless(os.name == "nt", "Windows 8.3 aliases require Windows")
    def test_save_accepts_long_canonical_path_with_short_workspace_alias(self):
        self._assert_alias_save("long", "short")
~~~

Add one negative-control method that proves the existing leaf and lock
authorization still runs before mutation:

~~~python
    def test_canonical_leaf_and_lock_symlinks_are_rejected_before_write(self):
        for entry_kind in ("canonical", "lock"):
            with (
                self.subTest(entry_kind=entry_kind),
                tempfile.TemporaryDirectory() as workspace_dir,
                tempfile.TemporaryDirectory() as outside_dir,
            ):
                workspace = Path(workspace_dir)
                outside = Path(outside_dir)
                reports = workspace / "reports"
                reports.mkdir()
                canonical = reports / "test_spec.json"
                target = outside / f"{entry_kind}.txt"
                target.write_text("outside\n", encoding="utf-8")
                link = (
                    canonical
                    if entry_kind == "canonical"
                    else reports / ".test_spec.json.lock"
                )
                try:
                    os.symlink(target, link)
                except OSError as error:
                    self.skipTest(f"symlink creation unavailable: {error}")
                with self.assertRaises(ValueError):
                    save_test_spec(
                        canonical,
                        TestSpec.from_payload(copied_payload()),
                        expected_revision=None,
                        current_context=current_context(workspace),
                    )
                self.assertEqual(
                    "outside\n",
                    target.read_text(encoding="utf-8"),
                )
~~~

- [ ] **Step 2: Run the TestSpec RED**

~~~powershell
$env:UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS = '1'
py -m unittest tests.test_test_spec_repository -v
~~~

Expected: test_save_accepts_short_canonical_path_with_long_workspace_alias fails through self.fail with the existing canonical-workspace error. The reverse direction and all existing security tests must still pass.

- [ ] **Step 3: Authorize lexically, then compare physically**

In src/unit_test_runner/test_spec/repository.py import:

~~~python
from unit_test_runner.path_utils import resolved_relative_to
~~~

Replace the current root, expected_path, lexical_path, and resolved_parent block in save_test_spec_snapshot with:

~~~python
    lexical_path, lexical_workspace = assert_safe_canonical_test_spec_path(path)
    root = Path(current_context.workspace_root or lexical_workspace)
    try:
        relative_path = resolved_relative_to(lexical_path, root)
    except ValueError as error:
        raise ValueError(
            "Canonical test specifications must be written to the workspace reports/test_spec.json."
        ) from error
    if relative_path != Path("reports") / "test_spec.json":
        raise ValueError(
            "Canonical test specifications must be written to the workspace reports/test_spec.json."
        )
    resolved_root = root.resolve(strict=False)
    resolved_parent = lexical_path.parent.resolve(strict=False)
    if resolved_parent != resolved_root / "reports":
        raise ValueError("Canonical test_spec parent must not escape through a symlink.")
    path = lexical_path
~~~

Keep assert_safe_canonical_test_spec_path before every resolve-based authority decision. Keep the existing leaf, parent, and lock symlink checks. When constructing ProducedArtifact, replace the recomputed relative expression with:

~~~python
            path=relative_path.as_posix(),
~~~

- [ ] **Step 4: Make workflow-return assertions compare physical identity**

In tests/test_test_spec_generation.py change all three alias-sensitive comparisons to:

~~~python
self.assertEqual(
    canonical.resolve(),
    Path(dossier["test_spec"]["json"]).resolve(),
)
self.assertEqual(canonical.resolve(), Path(exported["json"]).resolve())
self.assertEqual(canonical.resolve(), Path(regenerated["json"]).resolve())
~~~

In tests/test_test_spec_reanalysis.py change the result comparison to:

~~~python
self.assertEqual(
    canonical.resolve(),
    Path(result["test_spec_path"]).resolve(),
)
~~~

These are test-only identity corrections. GitHub main run 29187107516 directly
proved the first raw-string comparison fails; the next two comparisons were
not reached in that run and are the same audited short/long identity pattern.

- [ ] **Step 5: Run TestSpec GREEN, security regressions, and commit**

~~~powershell
$env:UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS = '1'
py -m unittest tests.test_test_spec_repository tests.test_test_spec_generation tests.test_test_spec_reanalysis tests.test_test_spec_exports tests.test_test_spec_patch tests.test_test_spec_formal_review_export_atomicity tests.test_test_spec_formal_review_snapshot tests.test_test_spec_formal_review_writer_snapshots tests.test_test_spec_formal_review_provenance -v
py -m compileall -q src tests
git diff --check
git add -- tests/test_test_spec_repository.py tests/test_test_spec_generation.py tests/test_test_spec_reanalysis.py src/unit_test_runner/test_spec/repository.py
git diff --cached --check
git commit -m "fix: accept Windows aliases after TestSpec path authorization"
~~~

Expected: both alias directions and every named TestSpec security module pass; compileall and diff checks exit 0.

---

### Task 5: Make Windows alias coverage mandatory in GitHub Actions

**Files:**
- Modify: tests/test_ci_contract.py
- Modify: .github/workflows/ci.yml

**Interfaces:**
- Consumes: WINDOWS_8DOT3_REQUIRED_ENV from the test fixture.
- Produces: a Python job where an unavailable 8.3 alias is a test failure, not a skip.
- Preserves: all six existing independent jobs and their current commands.

- [ ] **Step 1: Add the CI contract assertion first**

In test_github_actions_runs_python_and_vscode_extension_gates add:

~~~python
self.assertIn(
    'UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "1"',
    text,
)
~~~

- [ ] **Step 2: Run Task 5 RED**

~~~powershell
py -m unittest tests.test_ci_contract -v
~~~

Expected: only the new required-environment assertion fails.

- [ ] **Step 3: Require the alias in the Python job**

Add the job-level environment immediately after runs-on in .github/workflows/ci.yml:

~~~yaml
  python-tests:
    name: Python tests
    runs-on: windows-latest
    env:
      UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "1"
~~~

Do not add this environment to non-Windows jobs or change TEMP/TMP.

- [ ] **Step 4: Run Task 5 GREEN and commit**

~~~powershell
$env:UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS = '1'
py -m unittest tests.test_ci_contract tests.test_windows_path_alias_regression -v
git diff --check
git add -- tests/test_ci_contract.py .github/workflows/ci.yml
git diff --cached --check
git commit -m "ci: require Windows path alias regression"
~~~

Expected: both modules pass and the workflow still declares exactly six independent jobs.

---

## Prerequisite Branch Integration Gate

After all five task reviews are clean:

1. Run every tests/test_*.py module, sorted by name, in a fresh Python process. Expected final inventory on this branch: 112 modules, 532 tests, three local compiler-related skips, zero failing modules. If observed counts differ, record actual counts and investigate every difference.
2. Run py -m compileall -q src tests, py -m unit_test_runner --help, and git diff --check origin/main..HEAD.
3. Generate one origin/main..HEAD review package. Obtain a fresh whole-branch review with spec compliance approved, Critical 0, and Important 0.
4. Push codex/windows-83-path-alias and open a draft pull request against main.
5. Require Source integrity, Python tests, VS Code unit tests, VS Code Extension Host activation, VC6 fixture smoke, and Package contract to pass.
6. In the Python log, confirm tests.test_windows_path_alias_regression executed without skip and no C:\Users\RUNNER~1 versus C:\Users\runneradmin mismatch remains.
7. In the VC6 fixture log, confirm a real compiler-backed E2E passes rather than being skipped.
8. Mark the prerequisite pull request ready only after all checks and reviews are GREEN; merge with a merge commit.
9. Fetch merged origin/main in a fresh verification worktree and rerun the alias module, all formerly failing 13 modules, compileall, CLI help, and diff check.

## PR #17 Follow-up Gate

After the prerequisite is verified on main:

1. In C:\Users\stell\source\repos\unitTestRunner-sdd, fetch origin and merge origin/main into codex/p1-baseline-gate.
2. Resolve any workflow or tests/test_ci_contract.py overlap by keeping both the dynamic isolated-module loop from PR #17 and UNIT_TEST_RUNNER_REQUIRE_8DOT3_ALIAS: "1"; the merged branch is expected to discover 112 test modules.
3. Confirm PR #17 still contains maintenance-only CI/tests/design/evidence and no Task 6 product code. The path-product files from this prerequisite must be part of main, not an effective PR #17 diff.
4. Rerun the complete isolated local gate and whole-branch review, then push the merge update.
5. Require all six GitHub jobs GREEN and the VC6 compiler-backed E2E non-skipped.
6. Mark PR #17 ready and merge with a merge commit.
7. Verify merged main before creating the Phase 1 Task 6 execution plan.

## Self-Review Results

- Spec coverage: all four observed failure families are assigned to an explicit TDD task; baseline assertion prerequisites and CI anti-skip behavior are also explicit.
- Placeholder scan: no deferred implementation marker or unknown field name remains.
- Type consistency: resolved_relative_to returns Path in every task; contract serialization converts only the final relative Path to POSIX text.
- Security order: lexical and reparse authorization remains before physical canonicalization in TestSpec saves.
- Scope: no TEMP workaround and no Phase 1 Task 6 implementation is included.
- Integration: the plan accounts for the live red main baseline, the existing PR #17 overlap, remote checks, merge order, and post-merge verification.

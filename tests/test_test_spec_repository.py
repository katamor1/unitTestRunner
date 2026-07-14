from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch as mock_patch

from unit_test_runner.test_spec import (
    StaleRevisionError,
    TestSpec,
    load_test_spec,
    save_test_spec,
)
from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_spec import repository as repository_module

from tests.spec_support import copied_payload, current_context
from tests.windows_path_alias_support import (
    WINDOWS_8DOT3_PREFIX,
    require_windows_path_alias_pair,
)


class TestSpecRepositoryTests(unittest.TestCase):
    def test_permission_error_is_not_retried_outside_windows(self):
        attempts = 0

        def denied():
            nonlocal attempts
            attempts += 1
            raise PermissionError(13, "injected non-Windows permission denial")

        with mock_patch.object(
            repository_module,
            "_running_on_windows",
            return_value=False,
        ):
            with self.assertRaisesRegex(PermissionError, "non-Windows"):
                repository_module._retry_windows_permission_error(denied)

        self.assertEqual(1, attempts)

    def test_windows_permission_error_retry_stops_at_deadline(self):
        attempts = 0

        def denied():
            nonlocal attempts
            attempts += 1
            raise PermissionError(13, "persistent Windows sharing denial")

        with mock_patch.object(
            repository_module,
            "_running_on_windows",
            return_value=True,
        ), mock_patch.object(
            repository_module.time,
            "monotonic",
            side_effect=(0.0, 0.0, 0.25),
        ), mock_patch.object(repository_module.time, "sleep") as sleep:
            with self.assertRaisesRegex(PermissionError, "persistent Windows"):
                repository_module._retry_windows_permission_error(
                    denied,
                    timeout_seconds=0.25,
                )

        self.assertEqual(1, attempts)
        sleep.assert_called_once_with(0.01)

    def test_lock_retries_one_transient_windows_permission_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / ".test_spec.json.lock"
            original_open = repository_module.os.open
            attempts = 0

            def transient_open(path, flags):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError(13, "injected Windows sharing denial")
                return original_open(path, flags)

            with mock_patch.object(
                repository_module,
                "_running_on_windows",
                return_value=True,
            ), mock_patch.object(
                repository_module.os,
                "open",
                side_effect=transient_open,
            ):
                with repository_module._exclusive_lock(
                    lock_path,
                    timeout_seconds=0.25,
                ):
                    self.assertTrue(lock_path.exists())

            self.assertEqual(2, attempts)
            self.assertFalse(lock_path.exists())

    def test_lock_permission_retry_uses_the_full_lock_deadline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / ".test_spec.json.lock"
            original_open = repository_module.os.open
            attempts = 0

            def delayed_open(path, flags):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError(13, "delayed Windows sharing denial")
                return original_open(path, flags)

            manager = repository_module._exclusive_lock(
                lock_path,
                timeout_seconds=2.0,
            )
            with mock_patch.object(
                repository_module,
                "_running_on_windows",
                return_value=True,
            ), mock_patch.object(
                repository_module.os,
                "open",
                side_effect=delayed_open,
            ), mock_patch.object(
                repository_module.time,
                "monotonic",
                side_effect=(0.0, 0.0, 0.0, 0.0, 1.5),
            ), mock_patch.object(repository_module.time, "sleep"):
                manager.__enter__()

            try:
                self.assertEqual(2, attempts)
                self.assertTrue(lock_path.exists())
            finally:
                manager.__exit__(None, None, None)

            self.assertFalse(lock_path.exists())

    def test_lock_cleanup_retries_one_transient_windows_permission_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / ".test_spec.json.lock"
            original_unlink = repository_module.Path.unlink
            attempts = 0

            def transient_unlink(path, *args, **kwargs):
                nonlocal attempts
                if path == lock_path:
                    attempts += 1
                    if attempts == 1:
                        raise PermissionError(
                            13,
                            "injected Windows sharing denial",
                        )
                return original_unlink(path, *args, **kwargs)

            with mock_patch.object(
                repository_module,
                "_running_on_windows",
                return_value=True,
            ), mock_patch.object(
                repository_module.Path,
                "unlink",
                new=transient_unlink,
            ):
                with repository_module._exclusive_lock(lock_path):
                    self.assertTrue(lock_path.exists())

            self.assertEqual(2, attempts)
            self.assertFalse(lock_path.exists())

    def test_save_retries_one_transient_windows_replace_permission_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = workspace / "reports" / "test_spec.json"
            original_replace = repository_module.os.replace
            canonical_attempts = 0

            def transient_replace(source, destination):
                nonlocal canonical_attempts
                if Path(destination) == path:
                    canonical_attempts += 1
                    if canonical_attempts == 1:
                        raise PermissionError(
                            13,
                            "injected Windows sharing denial",
                        )
                return original_replace(source, destination)

            with mock_patch.object(
                repository_module,
                "_running_on_windows",
                return_value=True,
            ), mock_patch.object(
                repository_module.os,
                "replace",
                side_effect=transient_replace,
            ):
                artifact = save_test_spec(
                    path,
                    TestSpec.from_payload(copied_payload()),
                    expected_revision=None,
                    current_context=current_context(workspace),
                )

            self.assertEqual(2, canonical_attempts)
            self.assertEqual(1, load_test_spec(path, mode=ContractMode.STRICT).revision)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact.sha256)
            self.assertFalse(list(path.parent.glob(".test_spec.json.*.tmp")))

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
                self.assertTrue(link.is_symlink())
                if entry_kind == "lock":
                    self.assertFalse(canonical.exists())
                self.assertFalse(
                    list(reports.glob(".test_spec.json.*.tmp"))
                )
                self.assertEqual(
                    "outside\n",
                    target.read_text(encoding="utf-8"),
                )

    def test_create_writes_exact_canonical_bytes_and_returns_truthful_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = workspace / "reports" / "test_spec.json"
            spec = TestSpec.from_payload(copied_payload())

            artifact = save_test_spec(
                path,
                spec,
                expected_revision=None,
                current_context=current_context(workspace),
            )

            final_bytes = path.read_bytes()
            decoded = json.loads(final_bytes.decode("utf-8"))
            self.assertEqual(1, decoded["data"]["revision"])
            self.assertEqual(hashlib.sha256(final_bytes).hexdigest(), artifact.sha256)
            self.assertEqual("reports/test_spec.json", artifact.path)
            self.assertEqual("test_spec", artifact.kind)

    def test_update_checks_revision_under_lock_and_increments_exactly_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = workspace / "reports" / "test_spec.json"
            save_test_spec(path, TestSpec.from_payload(copied_payload()), expected_revision=None, current_context=current_context(workspace))
            left = load_test_spec(path, mode=ContractMode.STRICT)
            right = load_test_spec(path, mode=ContractMode.STRICT)
            left.test_cases[0]["title"] = "left"
            right.test_cases[0]["title"] = "right"

            def save(candidate: TestSpec):
                return save_test_spec(path, candidate, expected_revision=1, current_context=current_context(workspace))

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(save_or_error, ((save, left), (save, right))))

            self.assertEqual(1, sum(not isinstance(item, Exception) for item in results), results)
            self.assertEqual(1, sum(isinstance(item, StaleRevisionError) for item in results), results)
            persisted = load_test_spec(path, mode=ContractMode.STRICT)
            self.assertEqual(2, persisted.revision)
            self.assertFalse(list(path.parent.glob(".test_spec.json.*.tmp")))

    def test_stale_sequential_update_does_not_change_canonical_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = workspace / "reports" / "test_spec.json"
            save_test_spec(path, TestSpec.from_payload(copied_payload()), expected_revision=None, current_context=current_context(workspace))
            candidate = load_test_spec(path, mode=ContractMode.STRICT)
            candidate.test_cases[0]["title"] = "updated"
            save_test_spec(path, candidate, expected_revision=1, current_context=current_context(workspace))
            self.assertEqual(1, candidate.revision)
            before = path.read_bytes()

            with self.assertRaises(StaleRevisionError):
                save_test_spec(path, candidate, expected_revision=1, current_context=current_context(workspace))

            self.assertEqual(before, path.read_bytes())

    def test_workspace_escape_is_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as outside_dir:
            workspace = Path(workspace_dir)
            outside = Path(outside_dir)
            path = outside / "reports" / "test_spec.json"

            with self.assertRaises(ValueError):
                save_test_spec(path, TestSpec.from_payload(copied_payload()), expected_revision=None, current_context=current_context(workspace))

            self.assertFalse(path.exists())

    def test_nested_reports_directory_is_not_the_canonical_workspace_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = workspace / "nested" / "reports" / "test_spec.json"

            with self.assertRaises(ValueError):
                save_test_spec(path, TestSpec.from_payload(copied_payload()), expected_revision=None, current_context=current_context(workspace))

            self.assertFalse(path.exists())

    def test_symlinked_reports_parent_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as outside_dir:
            workspace = Path(workspace_dir)
            outside = Path(outside_dir)
            try:
                os.symlink(outside, workspace / "reports", target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlink creation unavailable: {error}")
            path = workspace / "reports" / "test_spec.json"

            with self.assertRaises(ValueError):
                save_test_spec(path, TestSpec.from_payload(copied_payload()), expected_revision=None, current_context=current_context(workspace))

            self.assertFalse((outside / "test_spec.json").exists())

    def test_noncanonical_target_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            with self.assertRaises(ValueError):
                save_test_spec(
                    workspace / "reports" / "test_case_design.json",
                    TestSpec.from_payload(copied_payload()),
                    expected_revision=None,
                    current_context=current_context(workspace),
                )


def save_or_error(item):
    save, candidate = item
    try:
        return save(candidate)
    except Exception as error:
        return error


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from unit_test_runner.test_spec import (
    StaleRevisionError,
    TestSpec,
    load_test_spec,
    save_test_spec,
)
from unit_test_runner.contracts import ContractMode

from tests.spec_support import copied_payload, current_context


class TestSpecRepositoryTests(unittest.TestCase):
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

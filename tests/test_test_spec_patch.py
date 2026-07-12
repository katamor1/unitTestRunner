from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_spec import (
    InvalidTestSpecPatchError,
    TestSpec,
    apply_test_spec_patch,
    load_test_spec,
    save_test_spec,
    update_test_spec,
)

from tests.spec_support import copied_payload, current_context


class TestSpecPatchTests(unittest.TestCase):
    def test_replace_addresses_case_by_id_and_json_pointer(self):
        spec = TestSpec.from_payload(copied_payload())

        updated = apply_test_spec_patch(
            spec,
            {
                "operations": [
                    {
                        "op": "replace",
                        "case_id": "tc-control-update-001",
                        "path": "/expected_observations/0/expected_expression",
                        "value": "ERROR",
                    }
                ]
            },
        )

        self.assertEqual("ERROR", updated.test_cases[0]["expected_observations"][0]["expected_expression"])
        self.assertEqual("OK", spec.test_cases[0]["expected_observations"][0]["expected_expression"])

    def test_unknown_case_path_immutable_and_approval_edits_are_rejected(self):
        invalid_operations = (
            {"op": "replace", "case_id": "missing", "path": "/title", "value": "x"},
            {"op": "replace", "case_id": "tc-control-update-001", "path": "/unknown", "value": "x"},
            {"op": "replace", "case_id": "tc-control-update-001", "path": "/test_case_id", "value": "x"},
            {"op": "replace", "case_id": "tc-control-update-001", "path": "/approved", "value": True},
            {"op": "replace", "case_id": "tc-control-update-001", "path": "/../title", "value": "x"},
        )
        for operation in invalid_operations:
            with self.subTest(operation=operation):
                with self.assertRaises(InvalidTestSpecPatchError):
                    apply_test_spec_patch(TestSpec.from_payload(copied_payload()), {"operations": [operation]})

    def test_duplicate_or_prefix_conflicting_operations_are_rejected_without_partial_mutation(self):
        spec = TestSpec.from_payload(copied_payload())
        before = copy.deepcopy(spec.to_payload())
        operations = [
            {"op": "replace", "case_id": "tc-control-update-001", "path": "/title", "value": "x"},
            {"op": "replace", "case_id": "tc-control-update-001", "path": "/title", "value": "y"},
        ]

        with self.assertRaises(InvalidTestSpecPatchError):
            apply_test_spec_patch(spec, {"operations": operations})

        self.assertEqual(before, spec.to_payload())

    def test_update_validates_full_spec_then_revision_checked_save(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            path = workspace / "reports" / "test_spec.json"
            save_test_spec(path, TestSpec.from_payload(copied_payload()), expected_revision=None, current_context=current_context(workspace))

            updated, artifact = update_test_spec(
                path,
                {
                    "operations": [
                        {"op": "replace", "case_id": "tc-control-update-001", "path": "/title", "value": "updated"}
                    ]
                },
                expected_revision=1,
                current_context=current_context(workspace),
            )

            self.assertEqual(2, updated.revision)
            self.assertEqual("updated", updated.test_cases[0]["title"])
            self.assertEqual("test_spec", artifact.kind)
            self.assertEqual(2, load_test_spec(path, mode=ContractMode.STRICT).revision)


if __name__ == "__main__":
    unittest.main()

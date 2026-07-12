from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.contracts import ContractMode
from unit_test_runner.test_spec import TestSpecContractError, load_test_spec

from tests.spec_support import SIGNATURE_SHA, SOURCE_SHA, copied_payload


def lossless_legacy_payload() -> dict:
    return {
        "schema_version": "0.1",
        "producer": {
            "name": "unit-test-runner",
            "version": "0.1.0",
            "commit": "legacy-verified-commit",
        },
        "extensions": {"legacy": {"preserved": True}},
        "spec_id": "spec-control-update",
        "revision": 1,
        "source": {"path": "src/control.c", "sha256": SOURCE_SHA},
        "function": {
            "function_id": "fn-control-update",
            "name": "Control_Update",
            "signature_sha256": SIGNATURE_SHA,
        },
        "generated_from": [],
        "generation_policy": {},
        "test_cases": [],
        "additional_case_candidates": [],
        "coverage_summary": {
            "total_coverage_items": 0,
            "covered_by_design_count": 0,
            "uncovered_coverage_ids": [],
            "coverage_to_test_cases": {},
        },
        "unresolved_items": [],
        "warnings": [],
        "review_item_ids": [],
    }


class TestSpecMigrationTests(unittest.TestCase):
    def test_compatible_load_migrates_v1_0_in_memory_and_strict_rejects_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_spec.json"
            previous = copied_payload()
            previous["schema_version"] = "1.0.0"
            path.write_text(json.dumps(previous, indent=2), encoding="utf-8")
            before = path.read_bytes()

            loaded = load_test_spec(path, mode=ContractMode.COMPATIBLE)

            self.assertEqual(before, path.read_bytes())
            self.assertEqual("1.1.0", loaded.schema_version)
            with self.assertRaises(TestSpecContractError):
                load_test_spec(path, mode=ContractMode.STRICT)

    def test_v1_0_review_status_cannot_be_silently_migrated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_spec.json"
            previous = copied_payload()
            previous["schema_version"] = "1.0.0"
            previous["data"]["test_cases"][0]["review_status"] = "approved"
            path.write_text(json.dumps(previous), encoding="utf-8")

            with self.assertRaises(TestSpecContractError):
                load_test_spec(path, mode=ContractMode.COMPATIBLE)

    def test_compatible_load_migrates_losslessly_in_memory_without_rewriting_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_case_design.json"
            legacy = lossless_legacy_payload()
            path.write_text(json.dumps(legacy, indent=2), encoding="utf-8")
            before = path.read_bytes()

            loaded = load_test_spec(path, mode=ContractMode.COMPATIBLE)

            self.assertEqual(before, path.read_bytes())
            self.assertEqual("1.1.0", loaded.schema_version)
            self.assertEqual("spec-control-update", loaded.spec_id)
            self.assertEqual("fn-control-update", loaded.function.function_id)

    def test_strict_load_rejects_legacy_alias(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_case_design.json"
            path.write_text(json.dumps(lossless_legacy_payload()), encoding="utf-8")

            with self.assertRaises(TestSpecContractError):
                load_test_spec(path, mode=ContractMode.STRICT)

    def test_compatible_load_rejects_legacy_shape_that_requires_fabricated_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_case_design.json"
            legacy = copy.deepcopy(lossless_legacy_payload())
            legacy["function"].pop("signature_sha256")
            path.write_text(json.dumps(legacy), encoding="utf-8")

            with self.assertRaises(TestSpecContractError):
                load_test_spec(path, mode=ContractMode.COMPATIBLE)


if __name__ == "__main__":
    unittest.main()

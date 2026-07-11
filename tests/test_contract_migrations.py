import json
import tempfile
import unittest
from pathlib import Path


from unit_test_runner.contracts import ArtifactKind, ContractMode
from unit_test_runner.contracts.migrations import migrate_payload
from unit_test_runner.contracts.validator import load_artifact


SHA256 = "7b18e68b2afcf1b0f0a1b857c5d1fcb2cf9db4d1540d778a266dbeaa3aa176a8"


def legacy_test_case_design() -> dict:
    return {
        "schema_version": "0.1",
        "source": {"path": "src/control.c", "sha256": SHA256},
        "function": {"name": "Control_Update", "status": "resolved"},
        "generation_policy": {},
        "test_cases": [
            {
                "test_case_id": "tc-control-update-001",
                "coverage_links": [{"coverage_id": "cov-control-update-001"}],
            }
        ],
        "additional_case_candidates": [],
        "coverage_summary": {
            "total_coverage_items": 1,
            "covered_by_design_count": 1,
            "uncovered_coverage_ids": [],
            "coverage_to_test_cases": {
                "cov-control-update-001": ["tc-control-update-001"]
            },
        },
        "unresolved_items": [],
        "warnings": [],
    }


class ContractMigrationTests(unittest.TestCase):
    def test_compatible_load_migrates_v01_in_memory_without_rewriting_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_case_design.json"
            path.write_text(
                json.dumps(legacy_test_case_design(), indent=2) + "\n",
                encoding="utf-8",
            )
            before = path.read_bytes()

            loaded = load_artifact(
                path,
                expected_kind=ArtifactKind.TEST_SPEC,
                mode=ContractMode.COMPATIBLE,
            )

            self.assertEqual(before, path.read_bytes())

        self.assertTrue(loaded.migrated)
        self.assertEqual("0.1", loaded.source_version)
        self.assertEqual("1.0.0", loaded.current_version)
        self.assertEqual("test_spec", loaded.payload["artifact_kind"])
        self.assertEqual("tc-control-update-001", loaded.payload["data"]["test_cases"][0]["test_case_id"])
        self.assertEqual((), loaded.violations)

    def test_strict_load_rejects_v01_without_migration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_case_design.json"
            path.write_text(json.dumps(legacy_test_case_design()), encoding="utf-8")

            loaded = load_artifact(
                path,
                expected_kind=ArtifactKind.TEST_SPEC,
                mode=ContractMode.STRICT,
            )

        self.assertFalse(loaded.migrated)
        self.assertEqual("0.1", loaded.source_version)
        self.assertIn("unsupported_version", {item.code for item in loaded.violations})

    def test_migration_does_not_mutate_input_mapping(self):
        legacy = legacy_test_case_design()
        before = json.dumps(legacy, sort_keys=True)

        migrated = migrate_payload(
            ArtifactKind.TEST_SPEC,
            legacy,
            target_version="1.0.0",
        )

        self.assertEqual(before, json.dumps(legacy, sort_keys=True))
        self.assertEqual("1.0.0", migrated["schema_version"])

    def test_unknown_source_version_is_rejected_in_compatible_mode(self):
        payload = legacy_test_case_design()
        payload["schema_version"] = "9.9"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "artifact.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            loaded = load_artifact(
                path,
                expected_kind=ArtifactKind.TEST_SPEC,
                mode=ContractMode.COMPATIBLE,
            )

        self.assertFalse(loaded.migrated)
        self.assertIn("unsupported_version", {item.code for item in loaded.violations})

    def test_invalid_json_becomes_parse_violation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "artifact.json"
            path.write_text("{not-json", encoding="utf-8")

            loaded = load_artifact(
                path,
                expected_kind=ArtifactKind.TEST_SPEC,
            )

        self.assertEqual("parse_error", loaded.violations[0].code)


if __name__ == "__main__":
    unittest.main()

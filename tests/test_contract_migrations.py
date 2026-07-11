import json
import tempfile
import unittest
from pathlib import Path


from unit_test_runner.contracts import ArtifactKind, ContractMode
from unit_test_runner.contracts.migrations import migrate_payload
from unit_test_runner.contracts.validator import load_artifact, validate_payload
from unit_test_runner.c_analyzer.source_digest import (
    build_source_digest,
    write_source_digest,
)


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
        self.assertNotIn(
            "signature_sha256",
            loaded.payload["data"]["function"],
        )
        self.assertEqual(
            {
                (
                    "missing_provenance",
                    "$.producer.commit",
                    "blocking",
                ),
                (
                    "missing_provenance",
                    "$.data.function.signature_sha256",
                    "blocking",
                )
            },
            {
                (item.code, item.json_path, item.severity)
                for item in loaded.violations
                if item.code == "missing_provenance"
            },
        )

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

    def test_dossier_migration_uses_known_target_source_without_inventing_hash(self):
        legacy = {
            "schema_version": "0.1",
            "target": {
                "source": "src/control.c",
                "function": "Control_Update",
            },
            "project_membership": [],
            "build_context": {},
            "function": {
                "name": "Control_Update",
                "source_path": "C:\\product\\src\\control.c",
                "status": "partial",
            },
            "test_design": {},
            "diagnostics": [],
        }

        migrated = migrate_payload(
            ArtifactKind.FUNCTION_DOSSIER,
            legacy,
            target_version="1.0.0",
        )

        self.assertEqual("src/control.c", migrated["subject"]["source_path"])
        self.assertEqual(
            "src/control.c",
            migrated["data"]["function"]["source_path"],
        )
        self.assertNotIn("source_sha256", migrated["subject"])
        self.assertNotIn("0" * 64, json.dumps(migrated, sort_keys=True))

    def test_wrapped_build_context_migrates_to_the_canonical_data_shape(self):
        legacy = {
            "schema_version": "0.1",
            "build_context": {
                "workspace_root": "workspace",
                "defines": ["DEBUG"],
                "include_dirs": ["include"],
                "compiler_options": ["/W3"],
                "forced_includes": [],
                "precompiled_header": {},
                "unresolved_macros": [],
            },
        }
        before = json.dumps(legacy, sort_keys=True)

        migrated = migrate_payload(
            ArtifactKind.BUILD_CONTEXT,
            legacy,
            target_version="1.0.0",
        )

        self.assertEqual(before, json.dumps(legacy, sort_keys=True))
        self.assertEqual(["DEBUG"], migrated["data"]["defines"])
        self.assertNotIn("build_context", migrated["data"])

    def test_suite_manifest_migration_preserves_absent_roots_as_null(self):
        legacy = {
            "schema_version": "0.1",
            "suite_id": "default",
            "source_root": "",
            "dsw_path": "",
            "entries": [],
        }

        migrated = migrate_payload(
            ArtifactKind.SUITE_MANIFEST,
            legacy,
            target_version="1.0.0",
        )

        self.assertIsNone(migrated["data"]["source_root"])
        self.assertIsNone(migrated["data"]["dsw_path"])

    def test_real_source_digest_migration_normalizes_data_and_preserves_origin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "control.c"
            source_path.write_text("int Control_Update(void) { return 0; }\n", encoding="utf-8")
            written = write_source_digest(
                Path(temp_dir) / "workspace",
                build_source_digest(source_path),
            )
            legacy = json.loads(written["json"].read_text(encoding="utf-8"))

            migrated = migrate_payload(
                ArtifactKind.SOURCE_DIGEST,
                legacy,
                target_version="1.0.0",
            )

        self.assertEqual(
            migrated["subject"]["source_path"],
            migrated["data"]["source"]["path"],
        )
        self.assertEqual(
            legacy["source"]["path"],
            migrated["extensions"]["migration"]["original_source_path"],
        )
        violations = validate_payload(ArtifactKind.SOURCE_DIGEST, migrated)
        self.assertNotIn(
            ("invalid_relative_path", "$.data.masking.masked_source_path"),
            {(item.code, item.json_path) for item in violations},
        )
        self.assertEqual(
            "legacy/masked_source.c",
            migrated["data"]["masking"]["masked_source_path"],
        )
        self.assertEqual(
            legacy["masking"]["masked_source_path"],
            migrated["extensions"]["migration"]["original_masked_source_path"],
        )
        self.assertNotIn(
            "invalid_relative_path",
            {item.code for item in violations},
        )
        self.assertNotIn(
            "invalid_reference",
            {item.code for item in violations},
        )
        self.assertIn(
            ("missing_identity", "$.subject.function_id", "blocking"),
            {
                (item.code, item.json_path, item.severity)
                for item in violations
            },
        )

    def test_migration_omits_unknown_identity_and_cli_scalar_facts(self):
        legacy = {
            "schema_version": "0.1",
            "status": "unmapped_status",
            "message": "Legacy command did not record identity.",
        }

        migrated = migrate_payload(
            ArtifactKind.CLI_RESULT,
            legacy,
            target_version="1.0.0",
        )

        self.assertNotIn("source_path", migrated["subject"])
        self.assertNotIn("source_sha256", migrated["subject"])
        self.assertNotIn("function_id", migrated["subject"])
        self.assertNotIn("command", migrated["data"])
        self.assertNotIn("exit_code", migrated["data"])
        self.assertNotIn("outcome", migrated["data"])
        self.assertNotIn("unknown", json.dumps(migrated, sort_keys=True))
        violations = validate_payload(ArtifactKind.CLI_RESULT, migrated)
        self.assertTrue(
            {
                ("missing_provenance", "$.subject.source_path", "blocking"),
                ("missing_provenance", "$.subject.source_sha256", "blocking"),
                ("missing_identity", "$.subject.function_id", "blocking"),
            }.issubset(
                {
                    (item.code, item.json_path, item.severity)
                    for item in violations
                }
            )
        )

    def test_compatible_migration_keeps_unknown_provenance_missing_and_blocking(self):
        legacy = legacy_test_case_design()
        legacy["source"].pop("sha256")
        legacy["function"].pop("signature_sha256", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_case_design.json"
            path.write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")
            before = path.read_bytes()

            loaded = load_artifact(
                path,
                expected_kind=ArtifactKind.TEST_SPEC,
                mode=ContractMode.COMPATIBLE,
            )

            self.assertEqual(before, path.read_bytes())

        self.assertTrue(loaded.migrated)
        self.assertNotIn("source_sha256", loaded.payload["subject"])
        self.assertNotIn("sha256", loaded.payload["data"]["source"])
        self.assertNotIn(
            "signature_sha256",
            loaded.payload["data"]["function"],
        )
        self.assertNotIn("0" * 64, json.dumps(loaded.payload, sort_keys=True))
        violations = {
            (item.code, item.json_path, item.severity)
            for item in loaded.violations
        }
        self.assertTrue(
            {
                ("missing_provenance", "$.subject.source_sha256", "blocking"),
                ("missing_provenance", "$.data.source.sha256", "blocking"),
                (
                    "missing_provenance",
                    "$.data.function.signature_sha256",
                    "blocking",
                ),
            }.issubset(violations),
            violations,
        )

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

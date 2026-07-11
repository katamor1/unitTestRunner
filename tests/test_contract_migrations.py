import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


from unit_test_runner.contracts import ArtifactKind, ContractMode
from unit_test_runner.contracts import migrations as migrations_module
from unit_test_runner.contracts.migrations import migrate_payload
from unit_test_runner.contracts.validator import load_artifact, validate_payload
from unit_test_runner.c_analyzer.source_digest import (
    build_source_digest,
    write_source_digest,
)
from unit_test_runner.cli.result import CLIResult
from unit_test_runner.build.build_models import BuildProbeReport
from unit_test_runner.build.build_workspace_generator import generate_build_workspace
from unit_test_runner.suite.models import (
    SuiteRunEntryResult,
    SuiteRunPolicy,
    SuiteRunReport,
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

    def test_dossier_migration_omits_unverified_absolute_target_source(self):
        original = "C:/product/src/control.c"
        legacy = {
            "schema_version": "0.1",
            "target": {
                "source": original,
                "function": "Control_Update",
            },
            "project_membership": [],
            "build_context": {},
            "function": {
                "name": "Control_Update",
                "source_path": original,
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

        self.assertNotIn("source_path", migrated["subject"])
        self.assertNotIn("function_id", migrated["subject"])
        self.assertNotIn("source", migrated["data"]["target"])
        self.assertIn(
            ("$.data.target.source", original, False),
            {
                (
                    item["json_path"],
                    item["original_value"],
                    item["verified"],
                )
                for item in migrated["extensions"]["migration"].get(
                    "path_migrations",
                    [],
                )
            },
        )
        self.assertIn(
            ("missing_provenance", "$.data.target.source", "blocking"),
            {
                (item.code, item.json_path, item.severity)
                for item in validate_payload(ArtifactKind.FUNCTION_DOSSIER, migrated)
            },
        )

    def test_dossier_migration_does_not_verify_unrelated_function_source(self):
        original = "D:/unrelated/other.c"
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
                "source_path": original,
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
        self.assertIsNone(migrated["data"]["function"]["source_path"])
        self.assertIn(
            ("$.data.function.source_path", original, False),
            {
                (
                    item["json_path"],
                    item["original_value"],
                    item["verified"],
                )
                for item in migrated["extensions"]["migration"].get(
                    "path_migrations",
                    [],
                )
            },
        )
        self.assertIn(
            (
                "missing_provenance",
                "$.data.function.source_path",
                "blocking",
            ),
            {
                (item.code, item.json_path, item.severity)
                for item in validate_payload(ArtifactKind.FUNCTION_DOSSIER, migrated)
            },
        )

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

    def test_suite_writer_migration_uses_canonical_outcomes_without_legacy_aliases(self):
        cases = (
            ("passed", "green", True, 1, 1, 0, 0, "passed"),
            ("timeout", "not_green", True, 1, 0, 0, 0, "timed_out"),
            ("not_run", "not_green", False, 0, 0, 0, 0, "planned"),
        )
        for (
            execution_status,
            green_status,
            executed,
            total,
            passed,
            failed,
            inconclusive,
            expected_outcome,
        ) in cases:
            with self.subTest(execution_status=execution_status):
                report = SuiteRunReport(
                    suite_id="default",
                    status="completed",
                    selector={"kind": "entry_id", "entry_ids": ["entry-001"]},
                    policy=SuiteRunPolicy(),
                    results=[
                        SuiteRunEntryResult(
                            entry_id="entry-001",
                            function_name="Control_Update",
                            workspace=Path("functions/control-update"),
                            execution_status=execution_status,
                            green_status=green_status,
                            executed=executed,
                            total_tests=total,
                            passed_tests=passed,
                            failed_tests=failed,
                            inconclusive_tests=inconclusive,
                            unresolved_review_count=0,
                            report_path=Path(
                                "functions/control-update/reports/test_execution_report.json"
                            ),
                        )
                    ],
                    summary={
                        "total": 1,
                        "green": 1 if green_status == "green" else 0,
                        "not_green": 0 if green_status == "green" else 1,
                        "executed": 1 if executed else 0,
                        "failed": 1 if failed else 0,
                    },
                )

                migrated = migrate_payload(
                    ArtifactKind.SUITE_RUN_REPORT,
                    report.to_dict(),
                    target_version="1.0.0",
                )

                self.assertEqual("finished", migrated["data"].get("lifecycle"))
                self.assertEqual(expected_outcome, migrated["data"].get("outcome"))
                self.assertEqual(
                    expected_outcome,
                    migrated["data"]["results"][0].get("outcome"),
                )
                self.assertNotIn("status", migrated["data"])
                self.assertNotIn(
                    "execution_status",
                    migrated["data"]["results"][0],
                )
                self.assertNotIn(
                    "not_run_tests",
                    migrated["data"]["results"][0],
                )
                self.assertIn(
                    (
                        "missing_provenance",
                        "$.data.results[0].not_run_tests",
                        "blocking",
                    ),
                    {
                        (item.code, item.json_path, item.severity)
                        for item in validate_payload(
                            ArtifactKind.SUITE_RUN_REPORT,
                            migrated,
                        )
                    },
                )

    def test_cli_writer_migration_prefers_precise_nested_execution_outcome(self):
        cases = {
            "blocked": "blocked",
            "inconclusive": "inconclusive",
            "timeout": "timed_out",
            "timed_out": "timed_out",
            "error": "error",
        }
        for nested_status, expected_outcome in cases.items():
            with self.subTest(nested_status=nested_status):
                legacy = CLIResult(
                    status="tests_blocked",
                    exit_code=2,
                    command="run-tests",
                    message="Execution completed.",
                    data={
                        "test_execution": {
                            "status": nested_status,
                            "executed": True,
                        }
                    },
                ).to_dict()
                legacy["schema_version"] = "0.1"

                migrated = migrate_payload(
                    ArtifactKind.CLI_RESULT,
                    legacy,
                    target_version="1.0.0",
                )

                self.assertEqual(expected_outcome, migrated["data"]["outcome"])

        top_level_error = CLIResult(
            status="tests_error",
            exit_code=1,
            command="run-tests",
            message="Internal error.",
        ).to_dict()
        top_level_error["schema_version"] = "0.1"
        self.assertEqual(
            "error",
            migrate_payload(
                ArtifactKind.CLI_RESULT,
                top_level_error,
                target_version="1.0.0",
            )["data"].get("outcome"),
        )

        ambiguous = CLIResult(
            status="tests_blocked",
            exit_code=2,
            command="run-tests",
            message="Blocked or inconclusive.",
        ).to_dict()
        ambiguous["schema_version"] = "0.1"
        self.assertNotIn(
            "outcome",
            migrate_payload(
                ArtifactKind.CLI_RESULT,
                ambiguous,
                target_version="1.0.0",
            )["data"],
        )

    def test_explicit_artifact_kind_mismatch_is_not_laundered_by_loading(self):
        payload = legacy_test_case_design()
        payload["artifact_kind"] = ArtifactKind.CLI_RESULT.value
        for mode in (ContractMode.COMPATIBLE, ContractMode.STRICT):
            with self.subTest(mode=mode.value), tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "mismatched.json"
                path.write_text(json.dumps(payload), encoding="utf-8")

                loaded = load_artifact(
                    path,
                    expected_kind=ArtifactKind.TEST_SPEC,
                    mode=mode,
                )

                self.assertFalse(loaded.migrated)
                self.assertEqual(payload, loaded.payload)
                self.assertEqual(
                    [
                        (
                            "artifact_kind_mismatch",
                            "$.artifact_kind",
                            "error",
                        )
                    ],
                    [
                        (item.code, item.json_path, item.severity)
                        for item in loaded.violations
                    ],
                )

    def test_migration_writes_the_validated_target_version_argument(self):
        with mock.patch.object(
            migrations_module,
            "CURRENT_CONTRACT_VERSION",
            "9.9.9",
            create=True,
        ):
            migrated = migrations_module.migrate_payload(
                ArtifactKind.TEST_SPEC,
                legacy_test_case_design(),
                target_version="1.0.0",
            )

        self.assertEqual("1.0.0", migrated["schema_version"])

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

        self.assertNotIn("source_path", migrated["subject"])
        self.assertNotIn("function_id", migrated["subject"])
        self.assertNotIn("path", migrated["data"]["source"])
        self.assertIsNone(migrated["data"]["masking"]["masked_source_path"])
        path_migrations = {
            item["json_path"]: item
            for item in migrated["extensions"]["migration"]["path_migrations"]
        }
        self.assertEqual(
            legacy["source"]["path"],
            path_migrations["$.data.source.path"]["original_value"],
        )
        self.assertFalse(path_migrations["$.data.source.path"]["verified"])
        self.assertEqual(
            legacy["masking"]["masked_source_path"],
            path_migrations["$.data.masking.masked_source_path"][
                "original_value"
            ],
        )
        self.assertFalse(
            path_migrations["$.data.masking.masked_source_path"]["verified"]
        )
        violations = validate_payload(ArtifactKind.SOURCE_DIGEST, migrated)
        blocking = {
            (item.code, item.json_path, item.severity)
            for item in violations
        }
        self.assertIn(
            ("missing_provenance", "$.data.source.path", "blocking"),
            blocking,
        )
        self.assertIn(
            (
                "missing_provenance",
                "$.data.masking.masked_source_path",
                "blocking",
            ),
            blocking,
        )
        self.assertNotIn(
            "invalid_relative_path",
            {item.code for item in violations},
        )
        self.assertNotIn(
            "invalid_reference",
            {item.code for item in violations},
        )
        self.assertIn(("missing_identity", "$.subject.function_id", "blocking"), blocking)

    def test_absolute_and_traversing_source_paths_do_not_create_colliding_identity(self):
        originals = (
            "C:/product-a/src/control.c",
            "D:/product-b/src/control.c",
            "../product-c/src/control.c",
        )
        migrated_payloads = []
        for original in originals:
            migrated_payloads.append(
                migrate_payload(
                    ArtifactKind.SOURCE_DIGEST,
                    {
                        "schema_version": "0.1",
                        "source": {"path": original, "sha256": SHA256},
                        "function": {"name": "Control_Update"},
                        "masking": {
                            "masked_source_path": None,
                            "masked_ranges": [],
                        },
                        "preprocessor": {
                            "includes": [],
                            "macros": [],
                            "directives": [],
                        },
                        "token_summary": {},
                        "tokens": [],
                        "warnings": [],
                    },
                    target_version="1.0.0",
                )
            )

        self.assertTrue(
            all("source_path" not in item["subject"] for item in migrated_payloads)
        )
        self.assertTrue(
            all("function_id" not in item["subject"] for item in migrated_payloads)
        )
        self.assertEqual(
            list(originals),
            [
                next(
                    record["original_value"]
                    for record in item["extensions"]["migration"][
                        "path_migrations"
                    ]
                    if record["json_path"] == "$.data.source.path"
                )
                for item in migrated_payloads
            ],
        )

    def test_specialized_test_spec_migration_preserves_unverified_absolute_source(self):
        legacy = legacy_test_case_design()
        original = "C:/product/src/control.c"
        legacy["source"]["path"] = original

        migrated = migrate_payload(
            ArtifactKind.TEST_SPEC,
            legacy,
            target_version="1.0.0",
        )

        self.assertNotIn("source_path", migrated["subject"])
        self.assertNotIn("function_id", migrated["subject"])
        self.assertNotIn("path", migrated["data"]["source"])
        self.assertIn(
            ("$.data.source.path", original, False),
            {
                (
                    item["json_path"],
                    item["original_value"],
                    item["verified"],
                )
                for item in migrated["extensions"]["migration"].get(
                    "path_migrations",
                    [],
                )
            },
        )
        self.assertIn(
            ("missing_provenance", "$.data.source.path", "blocking"),
            {
                (item.code, item.json_path, item.severity)
                for item in validate_payload(ArtifactKind.TEST_SPEC, migrated)
            },
        )

    def test_real_build_workspace_writer_marks_external_copied_sources_unverified(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "product"
            source = project / "src" / "control.c"
            source.parent.mkdir(parents=True)
            source.write_text(
                "int Control_Update(void) { return 0; }\n",
                encoding="ascii",
            )
            output = root / "workspace"
            generate_build_workspace(
                {
                    "workspace_root": str(project),
                    "include_dirs": [],
                    "defines": [],
                    "compiler_options": [],
                },
                {
                    "source": {"path": str(source)},
                    "preprocessor": {"includes": []},
                },
                {
                    "source": {"path": str(source)},
                    "function": {"name": "Control_Update"},
                    "output_root": str(output),
                    "generated_files": [],
                },
                output,
                run_probe=False,
                dry_run=True,
            )
            legacy = json.loads(
                (output / "reports" / "build_workspace_report.json").read_text(
                    encoding="utf-8"
                )
            )

            migrated = migrate_payload(
                ArtifactKind.BUILD_WORKSPACE_REPORT,
                legacy,
                target_version="1.0.0",
            )

        copied = migrated["data"]["copied_files"][0]
        self.assertEqual("extracted/src/control.c", copied["workspace_path"])
        self.assertIsNone(copied["source_path"])
        self.assertEqual(".", migrated["data"]["output_root"])
        path_migrations = {
            item["json_path"]: item
            for item in migrated["extensions"]["migration"]["path_migrations"]
        }
        copied_source_path = "$.data.copied_files[0].source_path"
        self.assertEqual(
            legacy["copied_files"][0]["source_path"],
            path_migrations[copied_source_path]["original_value"],
        )
        self.assertFalse(path_migrations[copied_source_path]["verified"])
        violations = validate_payload(ArtifactKind.BUILD_WORKSPACE_REPORT, migrated)
        self.assertIn(
            ("missing_provenance", copied_source_path, "blocking"),
            {
                (item.code, item.json_path, item.severity)
                for item in violations
            },
        )
        self.assertNotIn(
            "invalid_relative_path",
            {item.code for item in violations},
        )

    def test_build_probe_writer_migration_blocks_absolute_log_file_list_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "product" / "src" / "control.c"
            source.parent.mkdir(parents=True)
            source.write_text("int Control_Update(void) { return 0; }\n", encoding="ascii")
            log_file = root / "workspace" / "logs" / "build.log"
            log_file.parent.mkdir(parents=True)
            log_file.write_text("build output\n", encoding="utf-8")
            legacy = BuildProbeReport(
                source_path=source,
                function_name="Control_Update",
                status="succeeded",
                executed=True,
                exit_code=0,
                commands=[],
                diagnostics=[],
                missing_includes=[],
                unresolved_symbols=[],
                pch_issues=[],
                vc6_compatibility_issues=[],
                log_files=[log_file],
            ).to_dict()

            migrated = migrate_payload(
                ArtifactKind.BUILD_PROBE_REPORT,
                legacy,
                target_version="1.0.0",
            )

        self.assertEqual([], migrated["data"]["log_files"])
        log_path = "$.data.log_files[0]"
        self.assertIn(
            (log_path, legacy["log_files"][0], False),
            {
                (
                    item["json_path"],
                    item["original_value"],
                    item["verified"],
                )
                for item in migrated["extensions"]["migration"].get(
                    "path_migrations",
                    [],
                )
            },
        )
        violations = validate_payload(ArtifactKind.BUILD_PROBE_REPORT, migrated)
        self.assertIn(
            ("missing_provenance", log_path, "blocking"),
            {
                (item.code, item.json_path, item.severity)
                for item in violations
            },
        )
        self.assertNotIn(
            "invalid_relative_path",
            {item.code for item in violations},
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

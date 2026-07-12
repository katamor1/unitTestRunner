import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


from unit_test_runner import contracts as contract_api
from unit_test_runner.contracts import ArtifactKind, ContractMode
from unit_test_runner.contracts import migrations as migrations_module
from unit_test_runner.contracts.migrations import migrate_payload
from unit_test_runner.contracts.validator import load_artifact, validate_payload
from unit_test_runner.c_analyzer.source_digest import (
    build_source_digest,
    write_source_digest,
)
from unit_test_runner.build.build_models import (
    BuildCommand,
    BuildCommandResult,
    BuildDiagnostic,
    BuildPathEntry,
    BuildProbeReport,
    BuildWorkspaceReport,
    CompileUnit,
    LinkLibraryEntry,
    MissingInclude,
    VC6CompatibilityIssue,
    WorkspaceFile,
)
from unit_test_runner.build.build_workspace_generator import generate_build_workspace
from unit_test_runner.build_completion.completion_models import (
    BuildCompletionIterationReport,
    BuildCompletionPlan,
    BuildCompletionPolicy,
    BuildCompletionWarning,
    CompatibilityFeedbackItem,
    CompletionAction,
    CompletionIteration,
    DiagnosticsSummary,
    IncludeCompletionCandidate,
    StubCompletionCandidate,
)
from unit_test_runner.models import BuildConfiguration
from unit_test_runner.vc6.link_context import LinkContext, ResolvedLinkLibrary


SHA256 = "7b18e68b2afcf1b0f0a1b857c5d1fcb2cf9db4d1540d778a266dbeaa3aa176a8"


def public_build_context_payload(root: Path) -> tuple[dict, set[str]]:
    product = root / "product"
    configuration = BuildConfiguration(
        full_name="Control - Win32 Debug",
        defines=["DEBUG"],
        include_dirs=[(product / "include").as_posix()],
        forced_includes=[(product / "include" / "forced.h").as_posix()],
        precompiled_header={},
        compiler_options=["/W3"],
        unresolved_macros=[],
    ).to_dict()
    link_context = LinkContext(
        libraries=[
            ResolvedLinkLibrary(
                path=product / "lib" / "control.lib",
                source="dsp",
                link_order=1,
            )
        ],
        library_dirs=[product / "lib"],
    ).to_dict()
    return (
        {
            "schema_version": "0.1",
            "build_context": {
                "workspace_root": product.as_posix(),
                "defines": configuration["defines"],
                "include_dirs": configuration["include_dirs"],
                "compiler_options": configuration["compiler_options"],
                "forced_includes": configuration["forced_includes"],
                "precompiled_header": configuration["precompiled_header"],
                "unresolved_macros": configuration["unresolved_macros"],
                "link_libraries": link_context["libraries"],
                "library_dirs": link_context["library_dirs"],
                "link_context_warnings": link_context["warnings"],
            },
        },
        {
            "$.data.workspace_root",
            "$.data.include_dirs[0]",
            "$.data.forced_includes[0]",
            "$.data.link_libraries[0].path",
            "$.data.library_dirs[0]",
        },
    )


def public_build_writer_payloads(
    root: Path,
) -> dict[ArtifactKind, tuple[dict, set[str]]]:
    output = root / "workspace"
    product = root / "product"
    diagnostic = BuildDiagnostic(
        code="C1000",
        severity="error",
        message="compile failed",
        file=product / "src" / "control.c",
    )
    include_dir = BuildPathEntry(
        raw="product-include",
        workspace_path=output / "extracted" / "include",
        original_path=product / "include",
        exists=True,
        source="dsp_include",
    )
    workspace_report = BuildWorkspaceReport(
        source_path=product / "src" / "control.c",
        function_name="Control_Update",
        status="generated",
        output_root=output,
        copied_files=[
            WorkspaceFile(
                workspace_path=output / "extracted" / "src" / "control.c",
                file_kind="target_source",
                source_path=product / "src" / "control.c",
                copied=True,
            )
        ],
        referenced_files=[],
        generated_build_files=[
            WorkspaceFile(
                workspace_path=output / "build" / "Makefile",
                file_kind="makefile",
                generated=True,
            )
        ],
        compile_units=[
            CompileUnit(
                source_file=output / "extracted" / "src" / "control.c",
                object_file=output / "obj" / "control.obj",
                include_dirs=[include_dir],
                defines=[],
                compiler_options=[],
                command="cl control.c",
            )
        ],
        link_units=[
            output / "obj" / "control.obj",
            product / "lib" / "control.lib",
        ],
        include_dirs=[include_dir],
        defines=[],
        compiler_options=[],
        build_commands=[
            BuildCommand(
                command_id="CMD_BUILD_001",
                command_kind="compile",
                working_directory=output / "build",
                command_line="cl control.c",
                log_file=output / "logs" / "build.log",
            )
        ],
        diagnostics=[diagnostic],
        link_libraries=[
            LinkLibraryEntry(
                path=product / "lib" / "control.lib",
                source="dsp",
                link_order=1,
            )
        ],
        library_dirs=[product / "lib"],
    )
    workspace_paths = {
        "$.data.source.path",
        "$.data.output_root",
        "$.data.copied_files[0].source_path",
        "$.data.copied_files[0].workspace_path",
        "$.data.generated_build_files[0].workspace_path",
        "$.data.compile_units[0].source_file",
        "$.data.compile_units[0].object_file",
        "$.data.compile_units[0].include_dirs[0].workspace_path",
        "$.data.compile_units[0].include_dirs[0].original_path",
        "$.data.link_units[0]",
        "$.data.link_units[1]",
        "$.data.include_dirs[0].workspace_path",
        "$.data.include_dirs[0].original_path",
        "$.data.build_commands[0].working_directory",
        "$.data.build_commands[0].log_file",
        "$.data.diagnostics[0].file",
        "$.data.link_libraries[0].path",
        "$.data.library_dirs[0]",
    }

    probe_report = BuildProbeReport(
        source_path=product / "src" / "control.c",
        function_name="Control_Update",
        status="failed",
        executed=True,
        exit_code=1,
        commands=[
            BuildCommandResult(
                command_id="CMD_BUILD_001",
                command_kind="compile",
                command_line="cl control.c",
                exit_code=1,
                stdout_log=output / "logs" / "stdout.log",
                stderr_log=output / "logs" / "stderr.log",
                combined_log=output / "logs" / "combined.log",
                diagnostics=[diagnostic],
            )
        ],
        diagnostics=[diagnostic],
        missing_includes=[
            MissingInclude(
                include_name="missing.h",
                included_from=product / "src" / "control.c",
                line_number=4,
                diagnostic_raw="fatal error C1083",
                candidate_dirs=[product / "include", root / "sdk" / "include"],
            )
        ],
        unresolved_symbols=[],
        pch_issues=[],
        vc6_compatibility_issues=[
            VC6CompatibilityIssue(
                issue_kind="unsupported_syntax",
                file=product / "src" / "control.c",
                line_number=8,
                diagnostic_raw="syntax error",
                suggested_action="rewrite",
            )
        ],
        log_files=[output / "logs" / "build.log"],
    )
    probe_paths = {
        "$.data.source.path",
        "$.data.commands[0].stdout_log",
        "$.data.commands[0].stderr_log",
        "$.data.commands[0].combined_log",
        "$.data.commands[0].diagnostics[0].file",
        "$.data.diagnostics[0].file",
        "$.data.missing_includes[0].included_from",
        "$.data.missing_includes[0].candidate_dirs[0]",
        "$.data.missing_includes[0].candidate_dirs[1]",
        "$.data.vc6_compatibility_issues[0].file",
        "$.data.log_files[0]",
    }

    warning = BuildCompletionWarning(
        code="external_file",
        message="manual review",
        related_file=product / "src" / "control.c",
    )
    completion_plan = BuildCompletionPlan(
        source_path=product / "src" / "control.c",
        function_name="Control_Update",
        status="planned",
        policy=BuildCompletionPolicy(),
        completion_actions=[
            CompletionAction(
                action_id="action-001",
                action_kind="add_include",
                source_diagnostic_code="C1083",
                source_diagnostic_raw="missing include",
                description="Add include",
                apply_mode="manual",
                safety_level="review",
                target_files=[product / "src" / "control.c"],
                expected_effect="compile",
            )
        ],
        include_completion_candidates=[
            IncludeCompletionCandidate(
                include_name="missing.h",
                missing_from=product / "src" / "control.c",
                candidate_paths=[product / "include" / "missing.h"],
                candidate_include_dirs=[product / "include"],
                selected_action_id="action-001",
                confidence="high",
                review_required=True,
            )
        ],
        stub_completion_candidates=[
            StubCompletionCandidate(
                symbol_name="Missing",
                function_name_candidate="Missing",
                related_call_name=None,
                related_call_id=None,
                return_type_strategy="int",
                parameter_strategy="none",
                stub_source_path=output / "generated" / "stubs" / "missing.c",
                stub_header_path=output / "generated" / "stubs" / "missing.h",
                makefile_registration_required=True,
                confidence="medium",
                review_required=True,
            )
        ],
        compatibility_feedback_items=[
            CompatibilityFeedbackItem(
                issue_kind="unsupported_syntax",
                file=product / "src" / "control.c",
                line_number=8,
                suspected_generator=None,
                suggested_fix="rewrite",
                feedback_target_item="source",
                review_required=True,
            )
        ],
        warnings=[warning],
    )
    plan_paths = {
        "$.data.source.path",
        "$.data.completion_actions[0].target_files[0]",
        "$.data.include_completion_candidates[0].missing_from",
        "$.data.include_completion_candidates[0].candidate_paths[0]",
        "$.data.include_completion_candidates[0].candidate_include_dirs[0]",
        "$.data.stub_completion_candidates[0].stub_source_path",
        "$.data.stub_completion_candidates[0].stub_header_path",
        "$.data.compatibility_feedback_items[0].file",
        "$.data.warnings[0].related_file",
    }

    iteration = CompletionIteration(
        iteration_index=1,
        input_probe_report=output / "reports" / "build_probe_report.json",
        completion_plan=output / "reports" / "build_completion_plan.json",
        applied_actions=[],
        skipped_actions=[],
        generated_files=[output / "generated" / "stubs" / "missing.c"],
        probe_executed=False,
        probe_report=output / "reports" / "build_probe_report.json",
        diagnostics_before=DiagnosticsSummary(),
        diagnostics_after=None,
        progress="planned",
    )
    iteration_report = BuildCompletionIterationReport(
        source_path=product / "src" / "control.c",
        function_name="Control_Update",
        status="planned",
        iterations=[iteration],
        final_build_probe_status="not_run",
        final_diagnostics_summary=DiagnosticsSummary(),
        stop_reason="manual",
        next_recommended_action="review",
        warnings=[warning],
    )
    iteration_paths = {
        "$.data.source.path",
        "$.data.iterations[0].input_probe_report",
        "$.data.iterations[0].completion_plan",
        "$.data.iterations[0].generated_files[0]",
        "$.data.iterations[0].probe_report",
        "$.data.warnings[0].related_file",
    }
    history_paths = {
        path.replace("$.data.iterations[0]", "$.data.iterations[0]")
        for path in iteration_paths
        if path.startswith("$.data.iterations[0]")
    }

    return {
        ArtifactKind.BUILD_WORKSPACE_REPORT: (
            workspace_report.to_dict(),
            workspace_paths,
        ),
        ArtifactKind.BUILD_PROBE_REPORT: (probe_report.to_dict(), probe_paths),
        ArtifactKind.BUILD_COMPLETION_PLAN: (
            completion_plan.to_dict(),
            plan_paths,
        ),
        ArtifactKind.BUILD_COMPLETION_ITERATION: (
            iteration_report.to_dict(),
            iteration_paths,
        ),
        ArtifactKind.BUILD_COMPLETION_HISTORY: (
            {
                "schema_version": "0.1",
                "iterations": [iteration.to_dict()],
            },
            history_paths,
        ),
    }


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

    def test_build_context_model_paths_migrate_with_blocking_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy, expected_paths = public_build_context_payload(
                Path(temp_dir).resolve()
            )

            migrated = migrate_payload(
                ArtifactKind.BUILD_CONTEXT,
                legacy,
                target_version="1.0.0",
            )

        records = {
            item["json_path"]: item
            for item in migrated["extensions"]["migration"].get(
                "path_migrations",
                [],
            )
        }
        self.assertTrue(
            expected_paths.issubset(records),
            sorted(expected_paths - records.keys()),
        )
        self.assertTrue(
            all(records[path]["verified"] is False for path in expected_paths)
        )
        violations = validate_payload(ArtifactKind.BUILD_CONTEXT, migrated)
        self.assertTrue(
            {
                ("missing_provenance", path, "blocking")
                for path in expected_paths
            }.issubset(
                {
                    (item.code, item.json_path, item.severity)
                    for item in violations
                }
            )
        )
        self.assertNotIn(
            "invalid_relative_path",
            {item.code for item in violations},
        )

    def test_build_context_v1_rejects_every_absolute_structured_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy, expected_paths = public_build_context_payload(
                Path(temp_dir).resolve()
            )
            payload = {
                "artifact_kind": ArtifactKind.BUILD_CONTEXT.value,
                "schema_version": "1.0.0",
                "producer": {
                    "name": "unit-test-runner",
                    "version": "0.1.0",
                    "commit": "ec85f0fe81a486a5ce4bba67be79c3a4624a7763",
                },
                "subject": {
                    "function_id": "fn_control_update_7a32c11d",
                    "source_path": "src/control.c",
                    "source_sha256": SHA256,
                },
                "data": legacy["build_context"],
                "extensions": {},
            }

            invalid_paths = {
                item.json_path
                for item in validate_payload(ArtifactKind.BUILD_CONTEXT, payload)
                if item.code == "invalid_relative_path"
            }

        self.assertTrue(
            expected_paths.issubset(invalid_paths),
            sorted(expected_paths - invalid_paths),
        )

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
                legacy = {
                    "schema_version": "0.1",
                    "status": "suite_run_completed",
                    "suite_id": "default",
                    "selector": {"kind": "entry_id", "entry_ids": ["entry-001"]},
                    "policy": {
                        "run_tests": False,
                        "dry_run": True,
                        "timeout_seconds": 60,
                        "fail_fast": False,
                        "require_green": False,
                    },
                    "results": [
                        {
                            "entry_id": "entry-001",
                            "function": "Control_Update",
                            "workspace": "functions/control-update",
                            "execution_status": execution_status,
                            "green_status": green_status,
                            "executed": executed,
                            "total_tests": total,
                            "passed_tests": passed,
                            "failed_tests": failed,
                            "inconclusive_tests": inconclusive,
                            "unresolved_review_count": 0,
                            "report_path": "functions/control-update/reports/test_execution_report.json",
                        }
                    ],
                    "summary": {
                        "total": 1,
                        "green": 1 if green_status == "green" else 0,
                        "not_green": 0 if green_status == "green" else 1,
                        "executed": 1 if executed else 0,
                        "failed": 1 if failed else 0,
                    },
                }

                migrated = migrate_payload(
                    ArtifactKind.SUITE_RUN_REPORT,
                    legacy,
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
                legacy = {
                    "schema_version": "0.1",
                    "status": "tests_blocked",
                    "exit_code": 2,
                    "command": "run-tests",
                    "message": "Execution completed.",
                    "data": {
                        "test_execution": {
                            "status": nested_status,
                            "executed": True,
                        }
                    },
                    "warnings": [],
                    "errors": [],
                }

                migrated = migrate_payload(
                    ArtifactKind.CLI_RESULT,
                    legacy,
                    target_version="1.0.0",
                )

                self.assertEqual(expected_outcome, migrated["data"]["outcome"])

        top_level_error = {
            "schema_version": "0.1",
            "status": "tests_error",
            "exit_code": 1,
            "command": "run-tests",
            "message": "Internal error.",
            "data": {},
            "warnings": [],
            "errors": [],
        }
        self.assertEqual(
            "error",
            migrate_payload(
                ArtifactKind.CLI_RESULT,
                top_level_error,
                target_version="1.0.0",
            )["data"].get("outcome"),
        )

        ambiguous = {
            "schema_version": "0.1",
            "status": "tests_blocked",
            "exit_code": 2,
            "command": "run-tests",
            "message": "Blocked or inconclusive.",
            "data": {},
            "warnings": [],
            "errors": [],
        }
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

    def test_direct_migration_rejects_declared_kind_mismatch_without_mutation(self):
        compatible = legacy_test_case_design()
        compatible["artifact_kind"] = ArtifactKind.CLI_RESULT.value
        current = {
            "artifact_kind": ArtifactKind.CLI_RESULT.value,
            "schema_version": "1.0.0",
            "data": {"command": "run-tests"},
        }

        for source_version, payload in (
            ("0.1", compatible),
            ("1.0.0", current),
        ):
            with self.subTest(source_version=source_version):
                before = json.dumps(payload, sort_keys=True)

                with self.assertRaises(ValueError) as caught:
                    migrate_payload(
                        ArtifactKind.TEST_SPEC,
                        payload,
                        target_version="1.0.0",
                    )

                self.assertIs(
                    contract_api.ArtifactKindMismatchError,
                    type(caught.exception),
                )
                self.assertEqual("artifact_kind_mismatch", caught.exception.code)
                self.assertEqual(
                    ArtifactKind.TEST_SPEC.value,
                    caught.exception.expected_kind,
                )
                self.assertEqual(
                    ArtifactKind.CLI_RESULT.value,
                    caught.exception.actual_kind,
                )
                self.assertEqual(before, json.dumps(payload, sort_keys=True))

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

    def test_public_build_models_migrate_every_structured_path_with_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixtures = public_build_writer_payloads(Path(temp_dir).resolve())

            for kind, (legacy, expected_paths) in fixtures.items():
                with self.subTest(kind=kind.value):
                    migrated = migrate_payload(
                        kind,
                        legacy,
                        target_version="1.0.0",
                    )
                    records = {
                        item["json_path"]: item
                        for item in migrated["extensions"]["migration"].get(
                            "path_migrations",
                            [],
                        )
                    }

                    self.assertTrue(
                        expected_paths.issubset(records),
                        sorted(expected_paths - records.keys()),
                    )
                    for json_path in expected_paths:
                        self.assertTrue(
                            Path(records[json_path]["original_value"]).is_absolute(),
                            (kind.value, json_path, records[json_path]),
                        )

                    unverified_paths = {
                        json_path
                        for json_path, item in records.items()
                        if item["verified"] is False
                    }
                    violations = validate_payload(kind, migrated)
                    self.assertTrue(
                        {
                            ("missing_provenance", json_path, "blocking")
                            for json_path in unverified_paths
                        }.issubset(
                            {
                                (item.code, item.json_path, item.severity)
                                for item in violations
                            }
                        )
                    )
                    self.assertNotIn(
                        "invalid_relative_path",
                        {item.code for item in violations},
                    )

    def test_public_build_models_reject_every_absolute_structured_path_in_v1(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixtures = public_build_writer_payloads(Path(temp_dir).resolve())

            for kind, (legacy, expected_paths) in fixtures.items():
                with self.subTest(kind=kind.value):
                    payload = {
                        "artifact_kind": kind.value,
                        "schema_version": "1.0.0",
                        "producer": {
                            "name": "unit-test-runner",
                            "version": "0.1.0",
                            "commit": "ec85f0fe81a486a5ce4bba67be79c3a4624a7763",
                        },
                        "subject": {
                            "function_id": "fn_control_update_7a32c11d",
                            "source_path": "src/control.c",
                            "source_sha256": SHA256,
                        },
                        "data": {
                            key: value
                            for key, value in legacy.items()
                            if key != "schema_version"
                        },
                        "extensions": {},
                    }

                    invalid_paths = {
                        item.json_path
                        for item in validate_payload(kind, payload)
                        if item.code == "invalid_relative_path"
                    }
                    self.assertTrue(
                        expected_paths.issubset(invalid_paths),
                        sorted(expected_paths - invalid_paths),
                    )

    def test_workspace_relative_mapping_rejects_syntactic_parent_escape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixtures = public_build_writer_payloads(Path(temp_dir).resolve())
            legacy, _ = fixtures[ArtifactKind.BUILD_WORKSPACE_REPORT]
            traversal = (
                Path(legacy["output_root"]) / ".." / "escape" / "bad.lib"
            ).as_posix()
            legacy["link_units"] = [traversal]

            migrated = migrate_payload(
                ArtifactKind.BUILD_WORKSPACE_REPORT,
                legacy,
                target_version="1.0.0",
            )

        json_path = "$.data.link_units[0]"
        record = {
            item["json_path"]: item
            for item in migrated["extensions"]["migration"]["path_migrations"]
        }[json_path]
        self.assertEqual(traversal, record["original_value"])
        self.assertIsNone(record["migrated_value"])
        self.assertFalse(record["verified"])
        self.assertIn(
            ("missing_provenance", json_path, "blocking"),
            {
                (item.code, item.json_path, item.severity)
                for item in validate_payload(
                    ArtifactKind.BUILD_WORKSPACE_REPORT,
                    migrated,
                )
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
        self.assertNotIn("invocation_id", migrated["subject"])
        self.assertNotIn("command", migrated["data"])
        self.assertNotIn("exit_code", migrated["data"])
        self.assertNotIn("outcome", migrated["data"])
        self.assertNotIn("unknown", json.dumps(migrated, sort_keys=True))
        violations = validate_payload(ArtifactKind.CLI_RESULT, migrated)
        self.assertTrue(violations)
        self.assertTrue(
            any(
                item.code == "required_property"
                and item.json_path in {"$.subject", "$.data"}
                for item in violations
            ),
            [(item.code, item.json_path, item.severity) for item in violations],
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

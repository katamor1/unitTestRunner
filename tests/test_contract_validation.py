import copy
import unittest


from unit_test_runner.contracts import ArtifactKind
from unit_test_runner.contracts.validator import validate_payload


SHA256 = "7b18e68b2afcf1b0f0a1b857c5d1fcb2cf9db4d1540d778a266dbeaa3aa176a8"


def valid_test_spec() -> dict:
    return {
        "artifact_kind": "test_spec",
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
            "spec_id": "spec-control-update",
            "revision": 1,
            "source": {"path": "src/control.c", "sha256": SHA256},
            "function": {
                "function_id": "fn_control_update_7a32c11d",
                "name": "Control_Update",
                "signature_sha256": SHA256,
            },
            "generated_from": [],
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
            "review_item_ids": [],
        },
        "extensions": {},
    }


def valid_cli_result() -> dict:
    payload = valid_test_spec()
    payload["artifact_kind"] = "cli_result"
    payload["data"] = {
        "command": "run-tests",
        "lifecycle": "finished",
        "outcome": "passed",
        "exit_code": 0,
        "message": "Tests passed.",
        "artifacts": [],
        "errors": [],
    }
    return payload


def artifact_payload(kind: ArtifactKind, data: dict) -> dict:
    payload = valid_test_spec()
    payload["artifact_kind"] = kind.value
    payload["data"] = data
    return payload


def valid_function_signature() -> dict:
    return artifact_payload(
        ArtifactKind.FUNCTION_SIGNATURE,
        {
            "source": {"path": "src/control.c", "sha256": SHA256},
            "function": {
                "name": "Control_Update",
                "status": "parsed",
                "style": "ansi",
                "confidence": "high",
                "signature_range": {
                    "start": {"line": 10, "column": 1, "offset": 100},
                    "end": {"line": 10, "column": 31, "offset": 130},
                },
                "header_text_raw": "int Control_Update(void)",
                "header_text_normalized": "int Control_Update(void)",
                "storage_class": None,
                "calling_convention": None,
                "return_type": {
                    "raw": "int",
                    "normalized": "int",
                    "base_type": "int",
                    "qualifiers": [],
                    "storage_class": None,
                    "pointer_level": 0,
                    "is_const_pointer": None,
                    "is_struct": False,
                    "is_union": False,
                    "is_enum": False,
                    "is_typedef_like": False,
                    "is_function_pointer": False,
                    "is_array": False,
                    "array_dimensions": [],
                    "confidence": "high",
                },
                "parameters": [],
                "takes_no_parameters": True,
            },
            "warnings": [],
        },
    )


def valid_build_probe_report() -> dict:
    return artifact_payload(
        ArtifactKind.BUILD_PROBE_REPORT,
        {
            "source": {"path": "src/control.c"},
            "function": {"name": "Control_Update", "status": "succeeded"},
            "executed": True,
            "exit_code": 0,
            "started_at": None,
            "finished_at": None,
            "duration_ms": 5,
            "commands": [],
            "diagnostics": [],
            "missing_includes": [],
            "unresolved_symbols": [],
            "pch_issues": [],
            "vc6_compatibility_issues": [],
            "log_files": ["logs/build.log"],
        },
    )


def valid_evidence_manifest() -> dict:
    evidence_file = {
        "path": "src/control.c",
        "file_kind": "source",
        "sha256": SHA256,
        "required": True,
        "description": "Target source",
    }
    return artifact_payload(
        ArtifactKind.EVIDENCE_MANIFEST,
        {
            "function": "Control_Update",
            "workspace_root": "workspace",
            "created_at": "2026-07-12T00:00:00+00:00",
            "source_files": [evidence_file],
            "generated_files": [],
            "build_reports": [],
            "test_reports": [],
            "logs": [],
            "unresolved_items": [],
            "summary": {
                "build_probe_status": "succeeded",
                "test_execution_status": "passed",
                "total_tests": 1,
                "passed_tests": 1,
                "failed_tests": 0,
                "inconclusive_tests": 0,
                "unresolved_review_count": 0,
                "ready_for_review": True,
            },
        },
    )


def valid_function_dossier() -> dict:
    return artifact_payload(
        ArtifactKind.FUNCTION_DOSSIER,
        {
            "target": {
                "source": "src/control.c",
                "function": "Control_Update",
                "configuration": "Debug",
                "project": "Control",
            },
            "project_membership": [],
            "build_context": {},
            "function": {"name": "Control_Update", "status": "ready"},
            "test_design": {},
            "diagnostics": [],
            "workspace_root": "workspace",
            "created_at": "2026-07-12T00:00:00+00:00",
            "artifact_index": [
                {
                    "artifact_id": "artifact-source-digest",
                    "artifact_kind": "source_digest",
                    "path": "reports/source_digest.json",
                    "exists": True,
                    "sha256": SHA256,
                    "schema_version": "1.0.0",
                    "produced_by_item": "analysis",
                    "required_level": "required",
                    "stale_candidate": False,
                    "modified_at": None,
                    "warnings": [],
                }
            ],
            "summaries": {},
            "traceability": [],
            "review_items": [
                {
                    "review_id": "review-001",
                    "category": "analysis",
                    "title": "Review source digest",
                    "description": "Confirm analysis evidence.",
                    "related_artifacts": ["artifact-source-digest"],
                    "related_test_cases": [],
                    "severity": "warning",
                    "suggested_reviewer_role": "unit_test_reviewer",
                    "done": False,
                }
            ],
            "unresolved_items": [],
            "next_actions": [],
            "readiness": {
                "mvp_level": "analysis",
                "ready_for_review": True,
                "ready_for_harness_generation": False,
                "ready_for_build_probe": False,
                "ready_for_execution": False,
                "evidence_ready": False,
                "blocked": False,
                "blocked_reasons": [],
                "quality_score": None,
            },
            "warnings": [],
        },
    )


def _snapshot(snapshot_id: str) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "function_name": "Control_Update",
        "source_path": "src/control.c",
        "source_sha256": SHA256,
        "build_context_hash": SHA256,
        "created_at": "2026-07-12T00:00:00+00:00",
        "artifacts": {},
    }


def valid_change_impact() -> dict:
    return artifact_payload(
        ArtifactKind.CHANGE_IMPACT,
        {
            "function": {"name": "Control_Update", "status": "changed"},
            "previous_snapshot": _snapshot("snapshot-previous"),
            "current_snapshot": _snapshot("snapshot-current"),
            "source_changes": [],
            "interface_changes": [],
            "dependency_changes": [],
            "coverage_changes": [],
            "test_design_impacts": [],
            "regression_recommendation": None,
            "warnings": [],
        },
    )


def valid_suite_run_report() -> dict:
    return artifact_payload(
        ArtifactKind.SUITE_RUN_REPORT,
        {
            "status": "suite_run_completed",
            "suite_id": "default",
            "selector": {"kind": "entry_id", "entry_ids": ["entry-001"]},
            "policy": {
                "run_tests": True,
                "dry_run": False,
                "timeout_seconds": 60,
                "fail_fast": False,
                "require_green": True,
            },
            "summary": {
                "total": 1,
                "green": 1,
                "not_green": 0,
                "executed": 1,
                "failed": 0,
            },
            "results": [
                {
                    "entry_id": "entry-001",
                    "function": "Control_Update",
                    "workspace": "functions/control-update",
                    "execution_status": "passed",
                    "green_status": "green",
                    "executed": True,
                    "total_tests": 1,
                    "passed_tests": 1,
                    "failed_tests": 0,
                    "inconclusive_tests": 0,
                    "unresolved_review_count": 0,
                    "report_path": "functions/control-update/reports/test_execution_report.json",
                }
            ],
        },
    )


def violation_codes(kind: ArtifactKind, payload: dict) -> set[str]:
    return {item.code for item in validate_payload(kind, payload)}


class ContractValidationTests(unittest.TestCase):
    def test_valid_payload_has_no_violations(self):
        self.assertEqual((), validate_payload(ArtifactKind.TEST_SPEC, valid_test_spec()))
        self.assertEqual((), validate_payload(ArtifactKind.CLI_RESULT, valid_cli_result()))

    def test_missing_artifact_kind_is_rejected(self):
        payload = valid_test_spec()
        payload.pop("artifact_kind")

        self.assertIn("required_property", violation_codes(ArtifactKind.TEST_SPEC, payload))

    def test_unsupported_version_is_rejected(self):
        payload = valid_test_spec()
        payload["schema_version"] = "2.0.0"

        self.assertIn("unsupported_version", violation_codes(ArtifactKind.TEST_SPEC, payload))

    def test_invalid_enum_is_rejected(self):
        payload = valid_cli_result()
        payload["data"]["outcome"] = "successful"

        self.assertIn("invalid_enum", violation_codes(ArtifactKind.CLI_RESULT, payload))

    def test_missing_nested_field_is_rejected(self):
        payload = valid_test_spec()
        payload["producer"].pop("version")

        self.assertIn("required_property", violation_codes(ArtifactKind.TEST_SPEC, payload))

    def test_unknown_root_property_is_rejected(self):
        payload = valid_test_spec()
        payload["unexpected"] = True

        self.assertIn("unknown_property", violation_codes(ArtifactKind.TEST_SPEC, payload))

    def test_extensions_are_not_interpreted_as_builtin_contract_fields(self):
        payload = valid_cli_result()
        payload["extensions"] = {
            "vendor": {
                "path": "C:/cache/vendor/result.json",
                "cache_hash": "etag-v1",
            }
        }

        violations = validate_payload(ArtifactKind.CLI_RESULT, payload)

        self.assertNotIn(
            "invalid_relative_path",
            {item.code for item in violations},
        )
        self.assertNotIn("invalid_hash", {item.code for item in violations})

    def test_duplicate_test_case_id_is_rejected(self):
        payload = valid_test_spec()
        duplicate = copy.deepcopy(payload["data"]["test_cases"][0])
        payload["data"]["test_cases"].append(duplicate)

        self.assertIn("duplicate_id", violation_codes(ArtifactKind.TEST_SPEC, payload))

    def test_repeated_reference_id_is_allowed_when_entity_primary_ids_are_unique(self):
        payload = valid_test_spec()
        payload["artifact_kind"] = "function_dossier"
        payload["data"] = {
            "traceability": [
                {"link_id": "link-001", "test_case_id": "tc-001"},
                {"link_id": "link-002", "test_case_id": "tc-001"},
            ]
        }

        self.assertNotIn(
            "duplicate_id",
            violation_codes(ArtifactKind.FUNCTION_DOSSIER, payload),
        )

    def test_missing_coverage_reference_is_rejected(self):
        payload = valid_test_spec()
        payload["data"]["test_cases"][0]["coverage_links"][0]["coverage_id"] = "cov-missing"

        self.assertIn("invalid_reference", violation_codes(ArtifactKind.TEST_SPEC, payload))

    def test_absolute_subject_path_is_rejected(self):
        payload = valid_test_spec()
        payload["subject"]["source_path"] = "C:\\product\\src\\control.c"

        self.assertIn("invalid_relative_path", violation_codes(ArtifactKind.TEST_SPEC, payload))

    def test_representative_artifact_families_accept_valid_v1_payloads(self):
        samples = {
            ArtifactKind.FUNCTION_SIGNATURE: valid_function_signature(),
            ArtifactKind.BUILD_PROBE_REPORT: valid_build_probe_report(),
            ArtifactKind.EVIDENCE_MANIFEST: valid_evidence_manifest(),
            ArtifactKind.FUNCTION_DOSSIER: valid_function_dossier(),
            ArtifactKind.CHANGE_IMPACT: valid_change_impact(),
            ArtifactKind.SUITE_RUN_REPORT: valid_suite_run_report(),
        }
        for kind, payload in samples.items():
            with self.subTest(kind=kind.value):
                self.assertEqual((), validate_payload(kind, payload))

    def test_analysis_contract_rejects_absolute_data_source_path(self):
        payload = valid_function_signature()
        payload["data"]["source"]["path"] = "C:\\product\\src\\control.c"

        violations = validate_payload(ArtifactKind.FUNCTION_SIGNATURE, payload)

        self.assertIn(
            ("invalid_relative_path", "$.data.source.path"),
            {(item.code, item.json_path) for item in violations},
        )

    def test_call_report_rejects_unknown_related_call_id(self):
        payload = artifact_payload(
            ArtifactKind.CALL_REPORT,
            {
                "source": {"path": "src/control.c", "sha256": SHA256},
                "function": {"name": "Control_Update", "status": "analyzed"},
                "calls": [{"call_id": "call-001"}],
                "stub_candidates": [
                    {"name": "ReadSensor", "related_calls": ["call-missing"]}
                ],
                "side_effect_candidates": [],
                "unresolved_calls": [],
                "warnings": [],
            },
        )

        violations = validate_payload(ArtifactKind.CALL_REPORT, payload)

        self.assertIn(
            (
                "invalid_reference",
                "$.data.stub_candidates[0].related_calls[0]",
            ),
            {(item.code, item.json_path) for item in violations},
        )

    def test_coverage_design_rejects_unknown_target_id(self):
        payload = artifact_payload(
            ArtifactKind.COVERAGE_DESIGN,
            {
                "source": {"path": "src/control.c", "sha256": SHA256},
                "function": {"name": "Control_Update", "status": "analyzed"},
                "branches": [{"branch_id": "branch-001"}],
                "switches": [],
                "loops": [],
                "ternaries": [],
                "return_paths": [],
                "condition_expressions": [],
                "coverage_items": [
                    {"coverage_id": "coverage-001", "target_id": "branch-missing"}
                ],
                "warnings": [],
            },
        )

        violations = validate_payload(ArtifactKind.COVERAGE_DESIGN, payload)

        self.assertIn(
            ("invalid_reference", "$.data.coverage_items[0].target_id"),
            {(item.code, item.json_path) for item in violations},
        )

    def test_coverage_design_accepts_nested_switch_case_target(self):
        payload = artifact_payload(
            ArtifactKind.COVERAGE_DESIGN,
            {
                "source": {"path": "src/control.c", "sha256": SHA256},
                "function": {"name": "Control_Update", "status": "analyzed"},
                "branches": [],
                "switches": [
                    {
                        "switch_id": "switch-001",
                        "cases": [{"case_id": "case-001"}],
                    }
                ],
                "loops": [],
                "ternaries": [],
                "return_paths": [],
                "condition_expressions": [],
                "coverage_items": [
                    {"coverage_id": "coverage-001", "target_id": "case-001"}
                ],
                "warnings": [],
            },
        )

        violations = validate_payload(ArtifactKind.COVERAGE_DESIGN, payload)

        self.assertNotIn(
            ("invalid_reference", "$.data.coverage_items[0].target_id"),
            {(item.code, item.json_path) for item in violations},
        )

    def test_boundary_contract_rejects_unknown_candidate_id(self):
        payload = artifact_payload(
            ArtifactKind.BOUNDARY_CANDIDATES,
            {
                "source": {"path": "src/control.c", "sha256": SHA256},
                "function": {"name": "Control_Update", "status": "generated"},
                "input_candidates": [{"candidate_id": "candidate-001"}],
                "state_candidates": [],
                "stub_return_candidates": [],
                "equivalence_classes": [],
                "boundary_groups": [],
                "coverage_links": [
                    {
                        "coverage_id": "coverage-001",
                        "candidate_ids": ["candidate-missing"],
                    }
                ],
                "warnings": [],
            },
        )

        violations = validate_payload(ArtifactKind.BOUNDARY_CANDIDATES, payload)

        self.assertIn(
            (
                "invalid_reference",
                "$.data.coverage_links[0].candidate_ids[0]",
            ),
            {(item.code, item.json_path) for item in violations},
        )

    def test_build_contract_rejects_invalid_probe_status(self):
        payload = valid_build_probe_report()
        payload["data"]["function"]["status"] = "green"

        violations = validate_payload(ArtifactKind.BUILD_PROBE_REPORT, payload)

        self.assertIn(
            ("invalid_enum", "$.data.function.status"),
            {(item.code, item.json_path) for item in violations},
        )

    def test_build_completion_rejects_unknown_selected_action(self):
        payload = artifact_payload(
            ArtifactKind.BUILD_COMPLETION_PLAN,
            {
                "source": {"path": "src/control.c"},
                "function": {"name": "Control_Update", "status": "planned"},
                "policy": {"apply_safe_completions": False},
                "completion_actions": [{"action_id": "action-001"}],
                "include_completion_candidates": [
                    {
                        "include_name": "missing.h",
                        "selected_action_id": "action-missing",
                    }
                ],
                "stub_completion_candidates": [],
                "pch_completion_candidates": [],
                "compatibility_feedback_items": [],
                "manual_action_items": [],
                "warnings": [],
            },
        )

        violations = validate_payload(ArtifactKind.BUILD_COMPLETION_PLAN, payload)

        self.assertIn(
            (
                "invalid_reference",
                "$.data.include_completion_candidates[0].selected_action_id",
            ),
            {(item.code, item.json_path) for item in violations},
        )

    def test_evidence_contract_blocks_missing_required_file_hash(self):
        payload = valid_evidence_manifest()
        payload["data"]["source_files"][0]["sha256"] = None

        violations = validate_payload(ArtifactKind.EVIDENCE_MANIFEST, payload)

        self.assertIn(
            (
                "missing_provenance",
                "$.data.source_files[0].sha256",
                "blocking",
            ),
            {(item.code, item.json_path, item.severity) for item in violations},
        )

    def test_dossier_contract_rejects_unknown_artifact_reference(self):
        payload = valid_function_dossier()
        payload["data"]["review_items"][0]["related_artifacts"] = [
            "artifact-missing"
        ]

        violations = validate_payload(ArtifactKind.FUNCTION_DOSSIER, payload)

        self.assertIn(
            (
                "invalid_reference",
                "$.data.review_items[0].related_artifacts[0]",
            ),
            {(item.code, item.json_path) for item in violations},
        )

    def test_reanalysis_contract_rejects_invalid_snapshot_hash(self):
        payload = valid_change_impact()
        payload["data"]["current_snapshot"]["source_sha256"] = "unknown"

        violations = validate_payload(ArtifactKind.CHANGE_IMPACT, payload)

        self.assertIn(
            ("invalid_hash", "$.data.current_snapshot.source_sha256"),
            {(item.code, item.json_path) for item in violations},
        )

    def test_reconciliation_rejects_case_in_multiple_partitions(self):
        case = {
            "test_case_id": "case-001",
            "reuse_status": "reusable",
            "previous_coverage_ids": [],
            "current_coverage_ids": [],
            "previous_candidate_ids": [],
            "current_candidate_ids": [],
            "preserved_fields": [],
            "updated_fields": [],
            "review_required_fields": [],
            "reason": "unchanged",
            "confidence": "high",
        }
        payload = artifact_payload(
            ArtifactKind.TEST_CASE_RECONCILIATION,
            {
                "function": {"name": "Control_Update", "status": "completed"},
                "preserved_test_cases": [case],
                "updated_test_cases": [copy.deepcopy(case)],
                "obsolete_test_cases": [],
                "blocked_test_cases": [],
                "new_test_case_candidates": [],
                "manual_merge_items": [],
                "warnings": [],
            },
        )

        violations = validate_payload(
            ArtifactKind.TEST_CASE_RECONCILIATION,
            payload,
        )

        self.assertIn(
            ("duplicate_id", "$.data.updated_test_cases[0].test_case_id"),
            {(item.code, item.json_path) for item in violations},
        )

    def test_suite_contract_rejects_result_outside_selected_entries(self):
        payload = valid_suite_run_report()
        payload["data"]["results"][0]["entry_id"] = "entry-missing"

        violations = validate_payload(ArtifactKind.SUITE_RUN_REPORT, payload)

        self.assertIn(
            ("invalid_reference", "$.data.results[0].entry_id"),
            {(item.code, item.json_path) for item in violations},
        )

    def test_suite_manifest_allows_provenance_roots_to_be_absolute(self):
        payload = artifact_payload(
            ArtifactKind.SUITE_MANIFEST,
            {
                "suite_id": "default",
                "source_root": "C:\\product",
                "dsw_path": "C:\\product\\Product.dsw",
                "entries": [],
            },
        )

        violations = validate_payload(ArtifactKind.SUITE_MANIFEST, payload)

        self.assertNotIn(
            "invalid_relative_path",
            {item.code for item in violations},
        )

    def test_unimplemented_artifact_families_are_blocked_explicitly(self):
        reserved = {
            ArtifactKind.STATE_SETUP_REFLECTION,
            ArtifactKind.REVIEW_DECISIONS,
            ArtifactKind.REANALYSIS_SNAPSHOT,
            ArtifactKind.LATEST_RUN_POINTER,
            ArtifactKind.LATEST_EVIDENCE_POINTER,
            ArtifactKind.LATEST_SUITE_RUN_POINTER,
            ArtifactKind.EVIDENCE_SOURCE_RUN,
        }
        for kind in reserved:
            with self.subTest(kind=kind.value):
                violations = validate_payload(kind, artifact_payload(kind, {}))
                self.assertIn(
                    ("unsupported_artifact_payload", "$.data", "blocking"),
                    {
                        (item.code, item.json_path, item.severity)
                        for item in violations
                    },
                )


if __name__ == "__main__":
    unittest.main()

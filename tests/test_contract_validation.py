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


if __name__ == "__main__":
    unittest.main()

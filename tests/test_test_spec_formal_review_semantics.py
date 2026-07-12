from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from unit_test_runner.contracts import ArtifactKind, ContractMode, load_artifact, validate_payload
from unit_test_runner.execution.test_result_writer import build_artifact_payload

from tests.spec_support import copied_payload


def violation_codes(payload: dict) -> set[str]:
    return {item.code for item in validate_payload(ArtifactKind.TEST_SPEC, payload)}


class TestSpecFormalReviewSemanticTests(unittest.TestCase):
    def test_generic_contract_hook_rejects_nested_review_authority(self):
        payload = copied_payload()
        payload["data"]["test_cases"][0]["input_assignments"][0]["metadata"] = {
            "approved": True
        }

        self.assertIn("embedded_review_authority", violation_codes(payload))
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_spec.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_artifact(
                path,
                expected_kind=ArtifactKind.TEST_SPEC,
                mode=ContractMode.STRICT,
            )
        self.assertIn(
            "embedded_review_authority",
            {item.code for item in loaded.violations},
        )

    def test_generic_contract_rejects_duplicate_ids_across_case_collections(self):
        payload = copied_payload()
        payload["data"]["additional_case_candidates"] = [
            copy.deepcopy(payload["data"]["test_cases"][0])
        ]

        self.assertIn("duplicate_id", violation_codes(payload))

    def test_executable_case_requires_at_least_one_oracle(self):
        payload = copied_payload()
        payload["data"]["test_cases"][0]["expected_observations"] = []

        self.assertIn("missing_executable_oracle", violation_codes(payload))

    def test_leading_whitespace_does_not_hide_placeholder_oracle(self):
        payload = copied_payload()
        payload["data"]["test_cases"][0]["expected_observations"][0][
            "expected_expression"
        ] = "   TBD_EXPECTED_RETURN"

        self.assertIn("unresolved_executable_value", violation_codes(payload))

    def test_blocking_unresolved_item_cannot_reference_executable_case(self):
        payload = copied_payload()
        case_id = payload["data"]["test_cases"][0]["test_case_id"]
        payload["data"]["unresolved_items"] = [
            {
                "item_id": "review-blocking-001",
                "severity": "blocking",
                "related_test_case_ids": [case_id],
            }
        ]
        payload["data"]["review_item_ids"].append("review-blocking-001")

        self.assertIn("blocking_unresolved_executable", violation_codes(payload))

    def test_case_target_function_must_match_top_level_function(self):
        payload = copied_payload()
        payload["data"]["test_cases"][0]["target_function"] = "Other_Function"

        self.assertIn("target_function_mismatch", violation_codes(payload))

    def test_generic_builder_uses_kind_specific_current_version(self):
        source = copied_payload()
        test_spec = build_artifact_payload(
            ArtifactKind.TEST_SPEC,
            source["data"],
            subject=source["subject"],
            producer_commit="review-test",
        )
        other = build_artifact_payload(
            ArtifactKind.CALL_REPORT,
            {},
            subject=source["subject"],
            producer_commit="review-test",
        )

        self.assertEqual("1.1.0", test_spec["schema_version"])
        self.assertEqual("1.0.0", other["schema_version"])


if __name__ == "__main__":
    unittest.main()

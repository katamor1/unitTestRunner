from __future__ import annotations

import unittest

from unit_test_runner.test_spec import (
    ArtifactReference,
    CurrentArtifactContext,
    TestSpec,
    validate_test_spec,
)

from tests.spec_support import copied_payload, current_context


class TestSpecContractTests(unittest.TestCase):
    def assert_violation(self, payload: dict, code: str) -> None:
        spec = TestSpec.from_payload(payload, validate=False)
        violations = validate_test_spec(spec, current_context=current_context())
        self.assertIn(code, {item.code for item in violations}, violations)

    def test_valid_contract_has_no_violations(self):
        spec = TestSpec.from_payload(copied_payload())

        self.assertEqual((), validate_test_spec(spec, current_context=current_context()))
        self.assertNotIn("review_status", str(spec.to_payload()))

    def test_duplicate_case_id_across_executable_and_candidate_is_rejected(self):
        payload = copied_payload()
        payload["data"]["additional_case_candidates"].append(
            {
                "test_case_id": "tc-control-update-001",
                "coverage_links": [{"coverage_id": "cov-normal"}],
            }
        )

        self.assert_violation(payload, "duplicate_id")

    def test_dangling_coverage_review_and_dependency_references_are_rejected(self):
        payload = copied_payload()
        case = payload["data"]["test_cases"][0]
        case["coverage_links"][0]["coverage_id"] = "cov-missing"
        case["input_assignments"][0]["review_item_ids"] = ["review-missing"]
        case["stub_setups"][0]["related_dependency_id"] = "dep-missing"

        spec = TestSpec.from_payload(payload, validate=False)
        codes = {
            item.code
            for item in validate_test_spec(spec, current_context=current_context())
        }

        self.assertTrue(
            {"invalid_coverage_reference", "invalid_review_reference", "invalid_dependency_reference"}.issubset(codes),
            codes,
        )

    def test_embedded_approval_or_review_status_authority_is_rejected(self):
        for field, value in (("approved", True), ("approval", "accepted"), ("review_status", "approved")):
            with self.subTest(field=field):
                payload = copied_payload()
                payload["data"]["test_cases"][0][field] = value
                self.assert_violation(payload, "embedded_review_authority")

    def test_unresolved_executable_value_and_oracle_are_rejected(self):
        for path, value in (("value_expression", "TBD_INPUT"), ("expected_expression", None)):
            with self.subTest(field=path):
                payload = copied_payload()
                case = payload["data"]["test_cases"][0]
                target = case["input_assignments"][0] if path == "value_expression" else case["expected_observations"][0]
                target[path] = value
                self.assert_violation(payload, "unresolved_executable_value")

    def test_stale_source_and_signature_are_compared_to_explicit_context(self):
        payload = copied_payload()
        payload["data"]["source"]["sha256"] = "a" * 64
        payload["subject"]["source_sha256"] = "a" * 64
        payload["data"]["function"]["signature_sha256"] = "b" * 64

        spec = TestSpec.from_payload(payload, validate=False)
        codes = {
            item.code
            for item in validate_test_spec(spec, current_context=current_context())
        }

        self.assertIn("stale_source", codes)
        self.assertIn("stale_signature", codes)

    def test_generated_from_references_are_compared_to_explicit_current_artifacts(self):
        spec = TestSpec.from_payload(copied_payload())
        base = current_context()
        context = CurrentArtifactContext(
            source_path=base.source_path,
            source_sha256=base.source_sha256,
            function_id=base.function_id,
            function_name=base.function_name,
            signature_sha256=base.signature_sha256,
            generated_from=(
                ArtifactReference(
                    artifact_kind="function_signature",
                    path="reports/function_signature.json",
                    sha256="f" * 64,
                ),
            ),
        )

        codes = {item.code for item in validate_test_spec(spec, current_context=context)}

        self.assertIn("stale_generated_from", codes)


if __name__ == "__main__":
    unittest.main()

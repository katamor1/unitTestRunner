from __future__ import annotations

import unittest
from pathlib import Path

from unit_test_runner.dossier.dossier_models import DossierArtifact
from unit_test_runner.dossier.review_decision_models import ReviewItemCollection
from unit_test_runner.dossier.review_workflow import (
    build_review_item_collection,
    build_review_items,
)
from unit_test_runner.review_ids import build_review_id


FUNCTION_ID = "fn_control_update_cdd351ecf31d"
CASE_ID = "TC-01"
SEMANTIC_KEY = "UNRESOLVED_EXPECTED_001"
CATEGORY = "expected_result_unknown"


class DossierReviewAuthorityTests(unittest.TestCase):
    def test_dossier_review_item_binds_stable_identity_to_exact_subject(self):
        review_id = build_review_id(
            CATEGORY,
            FUNCTION_ID,
            CASE_ID,
            SEMANTIC_KEY,
        )
        payloads = {
            "test_spec": {
                "revision": 4,
                "source": {"path": "src/control.c", "sha256": "1" * 64},
                "function": {
                    "function_id": FUNCTION_ID,
                    "name": "Control_Update",
                },
                "test_cases": [],
                "additional_case_candidates": [],
                "unresolved_items": [
                    {
                        "item_id": SEMANTIC_KEY,
                        "item_kind": CATEGORY,
                        "description": "Expected result needs review.",
                        "related_test_case_ids": [CASE_ID],
                        "review_item_ids": [review_id],
                    }
                ],
            }
        }
        artifact = DossierArtifact(
            artifact_id="ART_008_test_spec",
            artifact_kind="test_spec",
            path=Path("reports/test_spec.json"),
            exists=True,
            sha256="a" * 64,
            schema_version="1.1.0",
            produced_by_item="test_case_design_generation",
            required_level="mvp2_required",
            contract_status="valid",
            contract_violations=[],
            contract_subject={
                "function_id": FUNCTION_ID,
                "source_path": "src/control.c",
                "source_sha256": "1" * 64,
            },
            contract_revision=4,
        )

        review_items, unresolved = build_review_items(payloads, [artifact])
        item = next(value for value in review_items if value.review_id == review_id)
        collection = build_review_item_collection(review_items)
        snapshot = collection.resolve(review_id)

        self.assertEqual(CASE_ID, item.case_id)
        self.assertEqual(SEMANTIC_KEY, item.semantic_subject_key)
        self.assertEqual(1, len(item.subject_artifacts))
        self.assertIsNotNone(snapshot)
        self.assertEqual("reports/test_spec.json", snapshot.subject_artifacts[0].path)
        self.assertEqual(4, snapshot.subject_artifacts[0].revision)
        serialized = item.to_dict()
        self.assertNotIn("done", serialized)
        self.assertEqual(SEMANTIC_KEY, serialized["semantic_subject_key"])
        self.assertTrue(serialized["subject_artifacts"])
        self.assertTrue(unresolved)

    def test_legacy_opaque_review_id_remains_display_only_not_authoritative(self):
        payloads = {
            "test_spec": {
                "function": {
                    "function_id": FUNCTION_ID,
                    "name": "Control_Update",
                },
                "test_cases": [
                    {
                        "test_case_id": CASE_ID,
                        "review_item_ids": ["legacy-review-id"],
                        "expected_observations": [
                            {"expected_expression": "TBD_EXPECTED"}
                        ],
                    }
                ],
            }
        }

        review_items, _ = build_review_items(payloads, [])
        collection = build_review_item_collection(review_items)
        legacy = next(item for item in review_items if item.review_id == "legacy-review-id")

        self.assertIsNone(legacy.semantic_subject_key)
        self.assertEqual([], legacy.subject_artifacts)
        self.assertEqual((), collection.items)


if __name__ == "__main__":
    unittest.main()

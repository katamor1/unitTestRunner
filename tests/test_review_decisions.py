from __future__ import annotations

import unittest

from unit_test_runner.dossier.review_assessment import (
    ReviewIdCollisionError,
    build_stable_review_id,
    validate_review_item_identities,
)
from unit_test_runner.dossier.review_decision_models import ReviewItemSnapshot


class StableReviewIdentityTests(unittest.TestCase):
    def test_id_ignores_order_titles_localization_and_paths(self) -> None:
        first = build_stable_review_id(
            category=" expected/result ",
            function_id="fn_Control_Update_1234",
            case_id=" TC-001 ",
            semantic_subject_key="oracle / return-value",
        )
        second = build_stable_review_id(
            category="expected\\result",
            function_id="fn_Control_Update_1234",
            case_id="TC-001",
            semantic_subject_key="oracle\\return-value",
        )
        self.assertEqual(first, second)
        self.assertNotIn("control_update", first.lower())

    def test_c_identifier_case_is_not_folded(self) -> None:
        upper = build_stable_review_id(
            "oracle", "fn_Control_Update_1234", "TC-001", "return",
        )
        lower = build_stable_review_id(
            "oracle", "fn_control_update_1234", "TC-001", "return",
        )
        self.assertNotEqual(upper, lower)

    def test_different_semantic_subjects_get_different_ids(self) -> None:
        left = build_stable_review_id("oracle", "fn-a", "tc-1", "return")
        right = build_stable_review_id("oracle", "fn-a", "tc-1", "global/state")
        self.assertNotEqual(left, right)

    def test_same_id_for_different_semantic_tuple_is_a_typed_collision(self) -> None:
        duplicate = "review-oracle-deadbeef"
        items = (
            ReviewItemSnapshot(
                review_id=duplicate,
                category="oracle",
                function_id="fn-a",
                case_id="tc-1",
                semantic_subject_key="return",
                title="Return value",
                description="Review return value",
            ),
            ReviewItemSnapshot(
                review_id=duplicate,
                category="oracle",
                function_id="fn-a",
                case_id="tc-1",
                semantic_subject_key="global/state",
                title="Global state",
                description="Review global state",
            ),
        )
        with self.assertRaises(ReviewIdCollisionError):
            validate_review_item_identities(items)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
from tempfile import TemporaryDirectory
import json

from unit_test_runner.contracts import ArtifactKind, ContractMode, load_artifact, validate_payload
from unit_test_runner.contracts.registry import get_contract


class ReviewDecisionContractTests(unittest.TestCase):
    def _envelope(self, data: dict) -> dict:
        return {
            "artifact_kind": "review_decisions",
            "schema_version": "1.1.0",
            "producer": {
                "name": "unit-test-runner",
                "version": "0.1.0",
                "commit": "a" * 40,
            },
            "subject": {
                "function_id": "fn-control",
                "source_path": "src/control.c",
                "source_sha256": "2" * 64,
            },
            "data": data,
            "extensions": {},
        }

    def test_task6_contracts_advance_without_removing_v1(self) -> None:
        for kind in (
            ArtifactKind.REVIEW_DECISIONS,
            ArtifactKind.FUNCTION_DOSSIER,
            ArtifactKind.DOSSIER_MANIFEST,
        ):
            self.assertEqual(get_contract(kind).current_version, "1.1.0")
            self.assertEqual(get_contract(kind, "1.0.0").current_version, "1.0.0")

    def test_terminal_decision_requires_reviewer_rationale_and_aware_timestamp(self) -> None:
        subject = {
            "artifact_kind": "test_spec",
            "path": "reports/test_spec.json",
            "sha256": "1" * 64,
            "revision": 1,
            "function_id": "fn-control",
            "source_path": "src/control.c",
            "source_sha256": "2" * 64,
            "semantic_subject_key": "oracle/return",
        }
        valid = self._envelope({
            "revision": 1,
            "decisions": [{
                "review_id": "review-oracle-123",
                "resolution": "approved",
                "reviewer": "reviewer@example.com",
                "rationale": "Matches the requirement.",
                "decided_at": "2026-07-12T12:00:00+09:00",
                "subject_fingerprint": "3" * 64,
                "subject_artifacts": [subject],
            }],
        })
        self.assertEqual(validate_payload(ArtifactKind.REVIEW_DECISIONS, valid), ())
        for field, value in (
            ("reviewer", ""),
            ("rationale", ""),
            ("decided_at", "2026-07-12T12:00:00"),
        ):
            candidate = json.loads(json.dumps(valid))
            candidate["data"]["decisions"][0][field] = value
            self.assertTrue(validate_payload(ArtifactKind.REVIEW_DECISIONS, candidate), field)

    def test_v1_decision_migrates_losslessly_but_unknown_revision_is_stale_capable(self) -> None:
        old = {
            "artifact_kind": "review_decisions",
            "schema_version": "1.0.0",
            "producer": {
                "name": "unit-test-runner",
                "version": "0.1.0",
                "commit": "a" * 40,
            },
            "subject": {
                "function_id": "fn-control",
                "source_path": "src/control.c",
                "source_sha256": "2" * 64,
            },
            "data": {
                "revision": 1,
                "decisions": [{
                    "review_id": "review-oracle-123",
                    "resolution": "approved",
                    "reviewer": "reviewer@example.com",
                    "rationale": "Approved under v1.",
                    "decided_at": "2026-07-12T12:00:00+09:00",
                    "subject_artifacts": [{
                        "artifact_kind": "test_spec",
                        "path": "reports/test_spec.json",
                        "sha256": "1" * 64,
                    }],
                }],
            },
            "extensions": {},
        }
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "review_decisions.json"
            before = (json.dumps(old, indent=2) + "\n").encode()
            path.write_bytes(before)
            loaded = load_artifact(
                path,
                expected_kind=ArtifactKind.REVIEW_DECISIONS,
                mode=ContractMode.COMPATIBLE,
            )
            self.assertTrue(loaded.migrated)
            self.assertFalse(loaded.violations)
            migrated = loaded.payload["data"]["decisions"][0]
            self.assertIsNone(migrated["subject_artifacts"][0]["revision"])
            self.assertEqual(path.read_bytes(), before)

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

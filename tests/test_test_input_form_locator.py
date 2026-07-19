from __future__ import annotations

import copy
import unittest

from unit_test_runner.test_input_form import FIELD_RULES
from unit_test_runner.test_input_form.field_locator import (
    canonical_bytes,
    digest,
    locate_form_items,
)


def case(case_id: str = "TC_Control_Update_001") -> dict:
    return {
        "test_case_id": case_id,
        "input_assignments": [
            {
                "target_kind": "parameter",
                "target_name": "mode",
                "source_candidate_id": "CAND_MODE",
                "value_expression": "TBD_VALID_VALUE",
                "review_required": True,
            },
            {
                "target_kind": "parameter",
                "target_name": "flags",
                "source_candidate_id": "CAND_FLAGS",
                "value_expression": "0",
                "review_required": False,
            },
        ],
        "state_setups": [
            {
                "scope": "global",
                "variable_name": "g_state",
                "source_candidate_id": "CAND_STATE",
                "value_expression": "STATE_IDLE",
                "setup_method_hint": "direct assignment",
                "review_required": True,
            }
        ],
        "stub_setups": [
            {
                "stub_name": "ReadSensor",
                "setup_kind": "return_value",
                "related_call_id": "CALL_SENSOR",
                "source_candidate_id": "CAND_SENSOR",
                "value_expression": "SENSOR_OK",
                "call_behavior": None,
                "review_required": True,
            }
        ],
        "expected_observations": [
            {
                "observation_kind": "return_value",
                "target_name": "return",
                "source": "coverage_design",
                "expected_expression": "OK",
                "note": None,
                "review_required": True,
            }
        ],
        "preconditions": [
            {
                "source": "build_context",
                "description": "VC6 target configuration is selected.",
                "review_required": True,
            }
        ],
        "execution_steps": [
            {
                "order": 1,
                "action": "setup_state",
                "detail": "Apply fixtures.",
                "review_required": True,
            }
        ],
        "dependency_overrides": [
            {
                "callee": "ReadSensor",
                "mode": "inherit",
                "rationale": "",
                "review_required": True,
            }
        ],
        "coverage_links": [{"coverage_id": "cov-1"}],
    }


def spec(*, executable: list[dict] | None = None, candidates: list[dict] | None = None) -> dict:
    return {
        "test_cases": executable or [],
        "additional_case_candidates": candidates or [],
    }


class TestInputFormLocatorTests(unittest.TestCase):
    def test_item_id_survives_case_and_item_reordering_and_case_location_change(self):
        original_case = case()
        original = locate_form_items(spec(candidates=[original_case]))
        original_mode = next(item for item in original if item.parent.get("target_name") == "mode")

        reordered_case = copy.deepcopy(original_case)
        reordered_case["input_assignments"].reverse()
        reordered = locate_form_items(
            spec(
                executable=[case("TC_Unrelated")],
                candidates=[reordered_case],
            )
        )
        reordered_mode = next(
            item
            for item in reordered
            if item.case_id == original_mode.case_id
            and item.parent.get("target_name") == "mode"
        )

        moved = locate_form_items(spec(executable=[copy.deepcopy(reordered_case)]))
        moved_mode = next(item for item in moved if item.parent.get("target_name") == "mode")

        self.assertEqual(original_mode.item_id, reordered_mode.item_id)
        self.assertEqual(original_mode.item_id, moved_mode.item_id)
        self.assertEqual("additional_case_candidates", original_mode.case_location)
        self.assertEqual("test_cases", moved_mode.case_location)
        self.assertNotIn("case_location", original_mode.locator)
        self.assertNotIn("case_index", original_mode.locator)
        self.assertNotIn("item_index", original_mode.locator)

    def test_locator_uses_the_exact_semantic_identity_fields_for_every_rule(self):
        located = locate_form_items(spec(executable=[case()]))
        by_collection = {}
        for item in located:
            by_collection.setdefault(item.collection, []).append(item)

        expected = {
            "input_assignments": {
                "target_kind": "parameter",
                "target_name": "mode",
                "source_candidate_id": "CAND_MODE",
            },
            "state_setups": {
                "scope": "global",
                "variable_name": "g_state",
                "source_candidate_id": "CAND_STATE",
            },
            "stub_setups": {
                "stub_name": "ReadSensor",
                "setup_kind": "return_value",
                "related_call_id": "CALL_SENSOR",
                "source_candidate_id": "CAND_SENSOR",
            },
            "expected_observations": {
                "observation_kind": "return_value",
                "target_name": "return",
                "source": "coverage_design",
            },
            "dependency_overrides": {"callee": "ReadSensor"},
            "preconditions": {"source": "build_context"},
            "execution_steps": {"order": 1, "action": "setup_state"},
        }

        for collection, identity in expected.items():
            with self.subTest(collection=collection):
                selected = by_collection[collection][0]
                self.assertEqual(identity, selected.locator["identity"])
                self.assertEqual(collection, selected.locator["collection"])
                self.assertEqual(FIELD_RULES[collection].kind, selected.locator["kind"])
                self.assertEqual("TC_Control_Update_001", selected.locator["case_id"])

    def test_duplicate_semantic_locators_are_ambiguous_and_never_writable(self):
        duplicate_case = case()
        duplicate_case["input_assignments"].append(
            copy.deepcopy(duplicate_case["input_assignments"][0])
        )

        located = locate_form_items(spec(executable=[duplicate_case]))
        duplicates = [
            item
            for item in located
            if item.collection == "input_assignments"
            and item.parent.get("target_name") == "mode"
        ]

        self.assertEqual(2, len(duplicates))
        self.assertEqual(1, len({item.item_id for item in duplicates}))
        self.assertTrue(all(item.ambiguous for item in duplicates))
        self.assertTrue(all(not item.editable for item in duplicates))
        self.assertEqual([0, 2], [item.item_index for item in duplicates])

    def test_parent_change_updates_fingerprint_without_changing_item_identity(self):
        first_case = case()
        first = locate_form_items(spec(executable=[first_case]))
        first_mode = next(item for item in first if item.parent.get("target_name") == "mode")

        changed_case = copy.deepcopy(first_case)
        changed_case["input_assignments"][0]["value_expression"] = "MODE_AUTO"
        changed_case["input_assignments"][0]["review_required"] = False
        changed = locate_form_items(spec(executable=[changed_case]))
        changed_mode = next(item for item in changed if item.parent.get("target_name") == "mode")

        self.assertEqual(first_mode.item_id, changed_mode.item_id)
        self.assertNotEqual(first_mode.subject_fingerprint, changed_mode.subject_fingerprint)

        reordered_case = copy.deepcopy(first_case)
        reordered_case["input_assignments"].reverse()
        reordered = locate_form_items(spec(executable=[reordered_case]))
        reordered_mode = next(item for item in reordered if item.parent.get("target_name") == "mode")
        self.assertEqual(first_mode.subject_fingerprint, reordered_mode.subject_fingerprint)

    def test_scans_both_case_collections_and_preserves_internal_coordinates(self):
        executable = case("TC_Executable")
        candidate = case("TC_Candidate")
        located = locate_form_items(spec(executable=[executable], candidates=[candidate]))

        self.assertTrue(any(item.case_id == "TC_Executable" for item in located))
        self.assertTrue(any(item.case_id == "TC_Candidate" for item in located))
        executable_items = [item for item in located if item.case_id == "TC_Executable"]
        candidate_items = [item for item in located if item.case_id == "TC_Candidate"]
        self.assertTrue(all(item.case_location == "test_cases" for item in executable_items))
        self.assertTrue(
            all(item.case_location == "additional_case_candidates" for item in candidate_items)
        )
        self.assertTrue(all(item.case_index == 0 for item in executable_items + candidate_items))

    def test_canonical_hashing_is_key_order_independent_and_unicode_preserving(self):
        left = {"b": "日本語", "a": 1}
        right = {"a": 1, "b": "日本語"}

        self.assertEqual(canonical_bytes(left), canonical_bytes(right))
        self.assertEqual(digest(left), digest(right))
        self.assertIn("日本語".encode("utf-8"), canonical_bytes(left))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import unittest

from unit_test_runner.test_input_form import FIELD_RULES
from unit_test_runner.test_input_form.field_locator import (
    canonical_bytes,
    digest,
    locate_form_items,
)
from unit_test_runner.test_spec import TestSpec
from tests.spec_support import copied_payload


class TestInputFormLocatorTests(unittest.TestCase):
    def make_spec(self, case: dict, *, candidate: bool = False) -> TestSpec:
        payload = copied_payload()
        data = payload["data"]
        data["test_cases"] = [] if candidate else [copy.deepcopy(case)]
        data["additional_case_candidates"] = [copy.deepcopy(case)] if candidate else []
        return TestSpec.from_payload(payload, validate=False)

    def full_case(self) -> dict:
        return {
            "test_case_id": "TC_Control_Update_001",
            "title": "locator fixture",
            "target_function": "Control_Update",
            "purpose": "exercise semantic locators",
            "priority": "high",
            "case_kind": "branch",
            "preconditions": [
                {
                    "description": "VC6 target selected",
                    "source": "build_context",
                    "review_required": True,
                }
            ],
            "input_assignments": [
                {
                    "target_kind": "parameter",
                    "target_name": "mode",
                    "source_candidate_id": "CAND_MODE_AUTO",
                    "value_expression": "TBD_VALID_VALUE",
                    "review_required": True,
                },
                {
                    "target_kind": "parameter",
                    "target_name": "limit",
                    "source_candidate_id": "CAND_LIMIT_0",
                    "value_expression": "0",
                    "review_required": False,
                },
            ],
            "state_setups": [
                {
                    "scope": "global",
                    "variable_name": "g_state",
                    "source_candidate_id": "CAND_STATE_IDLE",
                    "value_expression": "STATE_IDLE",
                    "setup_method_hint": "direct assignment",
                    "review_required": True,
                }
            ],
            "stub_setups": [
                {
                    "stub_name": "ReadSensor",
                    "setup_kind": "return_value",
                    "related_call_id": "CALL_READ_SENSOR",
                    "source_candidate_id": "CAND_SENSOR_OK",
                    "value_expression": "SENSOR_OK",
                    "call_behavior": "return once",
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
            "execution_steps": [
                {
                    "order": 1,
                    "action": "call_function",
                    "detail": "Call Control_Update",
                    "review_required": True,
                }
            ],
            "expected_observations": [
                {
                    "observation_kind": "return_value",
                    "target_name": "return",
                    "source": "coverage_design",
                    "expected_expression": "OK",
                    "note": "",
                    "review_required": True,
                }
            ],
            "coverage_links": [{"coverage_id": "cov-normal"}],
        }

    def by_identity(self, spec: TestSpec) -> dict[tuple[str, tuple[tuple[str, object], ...]], object]:
        result = {}
        for item in locate_form_items(spec):
            identity = tuple(sorted(item.locator["identity"].items()))
            result[(item.collection, identity)] = item
        return result

    def test_item_ids_survive_case_and_item_reordering_and_case_location_move(self):
        case = self.full_case()
        first = self.by_identity(self.make_spec(case))

        reordered = copy.deepcopy(case)
        reordered["input_assignments"].reverse()
        reordered["preconditions"].reverse()
        second = self.by_identity(self.make_spec(reordered))
        candidate = self.by_identity(self.make_spec(reordered, candidate=True))

        self.assertEqual(set(first), set(second))
        self.assertEqual(set(first), set(candidate))
        for key in first:
            with self.subTest(key=key):
                self.assertEqual(first[key].item_id, second[key].item_id)
                self.assertEqual(first[key].item_id, candidate[key].item_id)
                self.assertEqual("test_cases", first[key].case_location)
                self.assertEqual("additional_case_candidates", candidate[key].case_location)

    def test_locator_uses_exact_catalog_identity_fields_and_excludes_case_location(self):
        case = self.full_case()
        items = locate_form_items(self.make_spec(case))

        expected_fields = {
            "input_assignments": ("target_kind", "target_name", "source_candidate_id"),
            "state_setups": ("scope", "variable_name", "source_candidate_id"),
            "stub_setups": ("stub_name", "setup_kind", "related_call_id", "source_candidate_id"),
            "expected_observations": ("observation_kind", "target_name", "source"),
            "dependency_overrides": ("callee",),
            "preconditions": ("source",),
            "execution_steps": ("order", "action"),
        }
        self.assertEqual(expected_fields, {name: rule.locator_fields for name, rule in FIELD_RULES.items()})

        for item in items:
            with self.subTest(collection=item.collection, item_id=item.item_id):
                self.assertEqual(
                    set(expected_fields[item.collection]),
                    set(item.locator["identity"]),
                )
                self.assertEqual(case["test_case_id"], item.locator["case_id"])
                self.assertEqual(item.collection, item.locator["collection"])
                self.assertEqual(FIELD_RULES[item.collection].kind, item.locator["kind"])
                self.assertNotIn("case_location", item.locator)
                self.assertNotIn("case_index", item.locator)
                self.assertNotIn("item_index", item.locator)
                self.assertEqual("item-" + digest(item.locator), item.item_id)

    def test_duplicate_semantic_locators_are_ambiguous_and_never_made_unique_by_index(self):
        case = self.full_case()
        duplicate = copy.deepcopy(case["input_assignments"][0])
        duplicate["value_expression"] = "MODE_MANUAL"
        case["input_assignments"].append(duplicate)

        matching = [
            item
            for item in locate_form_items(self.make_spec(case))
            if item.collection == "input_assignments"
            and item.locator["identity"]["target_name"] == "mode"
        ]

        self.assertEqual(2, len(matching))
        self.assertEqual(1, len({item.item_id for item in matching}))
        self.assertTrue(all(item.ambiguous for item in matching))
        self.assertTrue(all(not item.editable for item in matching))
        self.assertEqual({0, 2}, {item.item_index for item in matching})

    def test_subject_fingerprint_tracks_parent_meaning_not_sibling_order(self):
        case = self.full_case()
        original = self.by_identity(self.make_spec(case))
        mode_key = next(
            key
            for key in original
            if key[0] == "input_assignments" and dict(key[1])["target_name"] == "mode"
        )

        reordered = copy.deepcopy(case)
        reordered["input_assignments"].reverse()
        reordered_items = self.by_identity(self.make_spec(reordered))
        self.assertEqual(
            original[mode_key].subject_fingerprint,
            reordered_items[mode_key].subject_fingerprint,
        )

        changed = copy.deepcopy(case)
        changed["input_assignments"][0]["value_expression"] = "MODE_AUTO"
        changed_items = self.by_identity(self.make_spec(changed))
        self.assertNotEqual(
            original[mode_key].subject_fingerprint,
            changed_items[mode_key].subject_fingerprint,
        )
        self.assertEqual(original[mode_key].item_id, changed_items[mode_key].item_id)

    def test_canonical_hashing_ignores_mapping_key_order(self):
        left = {"case_id": "TC", "identity": {"b": 2, "a": 1}}
        right = {"identity": {"a": 1, "b": 2}, "case_id": "TC"}

        self.assertEqual(canonical_bytes(left), canonical_bytes(right))
        self.assertEqual(digest(left), digest(right))


if __name__ == "__main__":
    unittest.main()

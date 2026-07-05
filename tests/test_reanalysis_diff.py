import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.reanalysis.coverage_diff import compare_coverage_designs
from unit_test_runner.reanalysis.dependency_diff import compare_dependencies
from unit_test_runner.reanalysis.signature_diff import compare_signatures


def signature(parameters):
    return {
        "function": {
            "name": "Control_Update",
            "calling_convention": None,
            "return_type": {"normalized": "int", "base_type": "int"},
            "parameters": parameters,
        }
    }


def param(index, name, normalized):
    return {"index": index, "name": name, "type": {"normalized": normalized}, "raw": f"{normalized} {name}"}


class ReanalysisDiffTests(unittest.TestCase):
    def test_signature_diff_marks_parameter_type_change_high_impact(self):
        previous = signature([param(0, "mode", "int")])
        current = signature([param(0, "mode", "long")])

        changes = compare_signatures(previous, current, ["TC_Control_Update_001"])

        self.assertEqual("parameter_type_changed", changes[0].change_kind)
        self.assertEqual("high", changes[0].impact_level)
        self.assertEqual(["TC_Control_Update_001"], changes[0].affected_test_case_ids)

    def test_signature_diff_marks_parameter_name_change_as_review(self):
        previous = signature([param(0, "mode", "int")])
        current = signature([param(0, "input_mode", "int")])

        changes = compare_signatures(previous, current, ["TC_Control_Update_001"])

        self.assertEqual("parameter_name_changed", changes[0].change_kind)
        self.assertEqual("medium", changes[0].impact_level)

    def test_dependency_diff_detects_added_call_and_stub_candidate(self):
        previous_call = {"calls": [], "stub_candidates": []}
        current_call = {
            "calls": [{"call_id": "CALL_001", "name": "CheckSafety", "target_kind": "external_function"}],
            "stub_candidates": [{"name": "CheckSafety", "target_kind": "external_function"}],
        }

        changes = compare_dependencies({}, {}, previous_call, current_call, ["TC_Control_Update_001"])
        kinds = {change.change_kind for change in changes}

        self.assertIn("call_added", kinds)
        self.assertIn("stub_candidate_added", kinds)

    def test_coverage_diff_remaps_modified_condition_by_similarity(self):
        previous = {
            "coverage_items": [
                {
                    "coverage_id": "BR_Control_Update_001_TRUE",
                    "coverage_type": "branch",
                    "target_id": "COND_001",
                    "condition_value": "true",
                    "related_variables": ["sensor"],
                    "related_calls": [],
                    "purpose": "sensor >= SENSOR_MIN",
                }
            ],
            "condition_expressions": [
                {"condition_id": "COND_001", "raw": "sensor >= SENSOR_MIN", "condition_kind": "if"}
            ],
        }
        current = {
            "coverage_items": [
                {
                    "coverage_id": "BR_Control_Update_010_TRUE",
                    "coverage_type": "branch",
                    "target_id": "COND_010",
                    "condition_value": "true",
                    "related_variables": ["sensor"],
                    "related_calls": [],
                    "purpose": "sensor > SENSOR_MIN",
                }
            ],
            "condition_expressions": [
                {"condition_id": "COND_010", "raw": "sensor > SENSOR_MIN", "condition_kind": "if"}
            ],
        }

        result = compare_coverage_designs(previous, current, {"BR_Control_Update_001_TRUE": ["TC_Control_Update_001"]})

        self.assertEqual("coverage_item_modified", result.changes[0].change_kind)
        self.assertEqual("BR_Control_Update_010_TRUE", result.mappings["BR_Control_Update_001_TRUE"].new_coverage_id)
        self.assertGreater(result.mappings["BR_Control_Update_001_TRUE"].similarity, 0.75)


if __name__ == "__main__":
    unittest.main()

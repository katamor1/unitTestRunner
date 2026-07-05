import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.reanalysis.coverage_diff import CoverageMapping
from unit_test_runner.reanalysis.reanalysis_models import CoverageChange, DependencyChange, InterfaceChange
from unit_test_runner.reanalysis.test_case_reconciler import reconcile_test_cases


class TestCaseReconcilerTests(unittest.TestCase):
    def test_reconciler_preserves_manual_expected_fields_and_test_case_id(self):
        previous_design = {
            "function": {"name": "Control_Update"},
            "test_cases": [
                {
                    "test_case_id": "TC_Control_Update_001",
                    "title": "Reviewed lower boundary",
                    "purpose": "Manual purpose",
                    "review_status": "approved",
                    "expected_observations": [
                        {
                            "observation_kind": "return_value",
                            "target_name": None,
                            "expected_expression": "CONTROL_OK",
                        }
                    ],
                    "coverage_links": [
                        {"coverage_id": "BR_Control_Update_001_TRUE", "target_id": "COND_001"}
                    ],
                    "candidate_links": ["IN_001"],
                }
            ],
        }
        current_design = {
            "function": {"name": "Control_Update"},
            "test_cases": [
                {
                    "test_case_id": "TC_Control_Update_999",
                    "title": "Generated lower boundary",
                    "purpose": "Generated purpose",
                    "review_status": "review_required",
                    "expected_observations": [
                        {
                            "observation_kind": "return_value",
                            "target_name": None,
                            "expected_expression": "TBD_EXPECTED_RETURN",
                        }
                    ],
                    "coverage_links": [
                        {"coverage_id": "BR_Control_Update_010_TRUE", "target_id": "COND_010"}
                    ],
                    "candidate_links": ["IN_010"],
                }
            ],
        }
        coverage_change = CoverageChange(
            change_kind="coverage_item_modified",
            old_coverage_id="BR_Control_Update_001_TRUE",
            new_coverage_id="BR_Control_Update_010_TRUE",
            old_condition="sensor >= SENSOR_MIN",
            new_condition="sensor > SENSOR_MIN",
            similarity=0.91,
            affected_test_case_ids=["TC_Control_Update_001"],
            suggested_action="Review boundary.",
        )

        report, updated = reconcile_test_cases(
            previous_design,
            current_design,
            [CoverageMapping("BR_Control_Update_001_TRUE", "BR_Control_Update_010_TRUE", 0.91, "similar_condition")],
            [coverage_change],
            [],
            [],
            generate_updated_test_case_design=True,
        )

        self.assertEqual("TC_Control_Update_001", report.updated_test_cases[0].test_case_id)
        self.assertIn("expected_observations", report.updated_test_cases[0].preserved_fields)
        self.assertEqual("CONTROL_OK", updated["test_cases"][0]["expected_observations"][0]["expected_expression"])
        self.assertEqual("approved", updated["test_cases"][0]["review_status"])

    def test_reconciler_marks_incompatible_signature_change_blocked(self):
        previous_design = {
            "function": {"name": "Control_Update"},
            "test_cases": [{"test_case_id": "TC_Control_Update_001", "coverage_links": []}],
        }

        report, _ = reconcile_test_cases(
            previous_design,
            {"function": {"name": "Control_Update"}, "test_cases": []},
            [],
            [],
            [
                InterfaceChange(
                    change_kind="parameter_removed",
                    target_name="mode",
                    old_signature="int mode",
                    new_signature=None,
                    impact_level="high",
                    affected_test_case_ids=["TC_Control_Update_001"],
                    suggested_action="Update invocation.",
                )
            ],
            [],
        )

        self.assertEqual("blocked", report.blocked_test_cases[0].reuse_status)


if __name__ == "__main__":
    unittest.main()

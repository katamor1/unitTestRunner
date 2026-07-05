import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from unit_test_runner.reanalysis.reanalysis_models import (
    ReconciledTestCase,
    TestCaseReconciliationReport,
)
from unit_test_runner.reanalysis.regression_selector import select_regression_tests


class RegressionSelectorTests(unittest.TestCase):
    def test_selector_selects_impacted_and_skips_unaffected_cases(self):
        reconciliation = TestCaseReconciliationReport(
            function_name="Control_Update",
            status="completed",
            preserved_test_cases=[
                ReconciledTestCase(
                    test_case_id="TC_Control_Update_002",
                    reuse_status="reusable",
                    previous_coverage_ids=[],
                    current_coverage_ids=[],
                    previous_candidate_ids=[],
                    current_candidate_ids=[],
                    preserved_fields=[],
                    updated_fields=[],
                    review_required_fields=[],
                    reason="No related changes.",
                    confidence="high",
                )
            ],
            updated_test_cases=[
                ReconciledTestCase(
                    test_case_id="TC_Control_Update_001",
                    reuse_status="needs_update",
                    previous_coverage_ids=["BR_001"],
                    current_coverage_ids=["BR_010"],
                    previous_candidate_ids=[],
                    current_candidate_ids=[],
                    preserved_fields=["expected_observations"],
                    updated_fields=["coverage_links"],
                    review_required_fields=["expected_observations"],
                    reason="Condition changed.",
                    confidence="medium",
                )
            ],
            obsolete_test_cases=[],
            blocked_test_cases=[],
            new_test_case_candidates=[],
            manual_merge_items=[],
            warnings=[],
        )

        selection = select_regression_tests("Control_Update", reconciliation)

        selected = {case.test_case_id: case for case in selection.selected_test_cases}
        skipped = {case.test_case_id: case for case in selection.skipped_test_cases}
        self.assertEqual("selected", selected["TC_Control_Update_001"].selection_status)
        self.assertTrue(selected["TC_Control_Update_001"].review_required)
        self.assertEqual("skipped_no_impact", skipped["TC_Control_Update_002"].selection_status)


if __name__ == "__main__":
    unittest.main()

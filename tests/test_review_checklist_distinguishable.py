import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dossier.dossier_models import DossierReviewItem
from unit_test_runner.reports.review_checklist_markdown import render_review_checklist_markdown


class ReviewChecklistDistinguishableTests(unittest.TestCase):
    def test_repeated_categories_show_id_target_and_description(self):
        markdown = render_review_checklist_markdown(
            [
                DossierReviewItem(
                    "REVIEW_EXPECTED_001",
                    "expected_result_review",
                    "期待結果を確認: TC_Shared_001",
                    "テストケース TC_Shared_001 の期待値・期待観測を確認してください。",
                    ["test_case_design"],
                    ["TC_Shared_001"],
                ),
                DossierReviewItem(
                    "REVIEW_EXPECTED_002",
                    "expected_result_review",
                    "期待結果を確認: TC_Shared_002",
                    "テストケース TC_Shared_002 の期待値・期待観測を確認してください。",
                    ["test_case_design"],
                    ["TC_Shared_002"],
                ),
            ]
        )

        self.assertIn("| 完了 | ID | 分類 | 対象 | タイトル | 内容 | 重要度 |", markdown)
        self.assertIn("REVIEW_EXPECTED_001", markdown)
        self.assertIn("REVIEW_EXPECTED_002", markdown)
        self.assertIn("TC_Shared_001", markdown)
        self.assertIn("TC_Shared_002", markdown)
        self.assertIn("テストケース TC_Shared_001 の期待値・期待観測を確認してください。", markdown)
        self.assertIn("テストケース TC_Shared_002 の期待値・期待観測を確認してください。", markdown)


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.dossier.dossier_models import DossierUnresolvedItem
from unit_test_runner.dossier.next_actions import build_next_actions
from unit_test_runner.reports.next_actions_markdown import render_next_actions_markdown


class NextActionsTests(unittest.TestCase):
    def test_expected_result_actions_include_test_case_unresolved_ids_and_file_links(self):
        unresolved = [
            DossierUnresolvedItem(
                "UNRESOLVED_EXPECTED_001",
                "test_case_design_generation",
                "expected_result_unknown",
                "Expected result requires review for TC_Shared_001.",
                "The generated test cannot be treated as approved until expected values are reviewed.",
                ["test_spec"],
                ["TC_Shared_001"],
                "Review function specification and replace TBD expected values.",
            ),
            DossierUnresolvedItem(
                "UNRESOLVED_EXPECTED_002",
                "test_case_design_generation",
                "expected_result_unknown",
                "Expected result requires review for TC_Shared_002.",
                "The generated test cannot be treated as approved until expected values are reviewed.",
                ["test_spec"],
                ["TC_Shared_002"],
                "Review function specification and replace TBD expected values.",
            ),
        ]
        artifact_index = [
            {
                "artifact_kind": "test_spec",
                "path": "reports/test_spec.json",
            }
        ]

        actions = build_next_actions(unresolved)
        markdown = render_next_actions_markdown(actions, unresolved, artifact_index, "Shared")

        self.assertEqual("期待結果を確認: テストケース TC_Shared_001", actions[0].title)
        self.assertEqual("期待結果を確認: テストケース TC_Shared_002", actions[1].title)
        self.assertNotEqual(actions[0].title, actions[1].title)
        self.assertIn("TC_Shared_001", actions[0].description)
        self.assertIn("TC_Shared_001", actions[0].expected_output)
        self.assertIn("| ID | 優先度 | アクション | 対応対象・理由 | 操作・参照ファイル | 担当 | 期待成果物 |", markdown)
        self.assertIn("NEXT_001", markdown)
        self.assertIn("UNRESOLVED_EXPECTED_001", markdown)
        self.assertIn("TC_Shared_002", markdown)
        self.assertIn("[テスト仕様](test_spec.md)", markdown)
        self.assertIn("[JSON/成果物](test_spec.json)", markdown)
        self.assertNotIn("test_case_design", markdown)
        self.assertIn("[生成テストソース](../generated/tests/test_Shared.c)", markdown)
        self.assertNotIn("| medium | Review expected result | spec_reviewer | Updated generated workspace artifacts or recorded human review decision. |", markdown)


if __name__ == "__main__":
    unittest.main()

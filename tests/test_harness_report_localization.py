import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.harness.harness_models import HarnessGenerationPolicy, HarnessSkeletonReport, UnresolvedPlaceholder
from unit_test_runner.harness.harness_report_writer import write_harness_report


class HarnessReportLocalizationTests(unittest.TestCase):
    def test_harness_report_json_and_markdown_localize_expected_placeholder_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            report = HarnessSkeletonReport(
                source_path=Path("src/control.c"),
                function_name="Control_Update",
                status="partial",
                output_root=workspace,
                generation_policy=HarnessGenerationPolicy(),
                generated_files=[],
                stub_skeletons=[],
                test_skeletons=[],
                unresolved_placeholders=[
                    UnresolvedPlaceholder(
                        "UP_EXPECTED",
                        "expected_return",
                        "TBD_EXPECTED_RETURN_INT",
                        "TC_Control_Update_001",
                        None,
                        "Expected result is not determined during test design generation.",
                        "Review generated test case and replace TBD expected values.",
                    )
                ],
                build_hints=[],
                warnings=[],
            )

            write_harness_report(workspace, report)

            payload = json.loads((workspace / "reports" / "harness_skeleton_report.json").read_text(encoding="utf-8"))
            markdown = (workspace / "reports" / "harness_skeleton_report.md").read_text(encoding="utf-8")
            combined = json.dumps(payload, ensure_ascii=False) + markdown

            self.assertIn("期待戻り値", combined)
            self.assertIn("テスト設計生成時点では期待結果を確定できません。", combined)
            self.assertIn("生成テストケースを確認し、TBD の期待値を置き換えてください。", combined)
            self.assertNotIn("Expected result is not determined", combined)
            self.assertNotIn("Review generated test case", combined)


if __name__ == "__main__":
    unittest.main()

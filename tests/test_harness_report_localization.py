import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.harness.harness_models import BuildHint, HarnessGenerationPolicy, HarnessSkeletonReport, UnresolvedPlaceholder
from unit_test_runner.harness.harness_report_writer import write_harness_report


class HarnessReportLocalizationTests(unittest.TestCase):
    def test_harness_report_keeps_json_enums_stable_and_localizes_markdown(self):
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
                build_hints=[
                    BuildHint(
                        "HINT_TARGET",
                        "target_source",
                        "Build completion cannot be fully automated.",
                        severity="info",
                    )
                ],
                warnings=[],
            )

            write_harness_report(workspace, report)

            payload = json.loads((workspace / "reports" / "harness_skeleton_report.json").read_text(encoding="utf-8"))
            markdown = (workspace / "reports" / "harness_skeleton_report.md").read_text(encoding="utf-8")
            placeholder = payload["unresolved_placeholders"][0]
            hint = payload["build_hints"][0]
            self.assertEqual("expected_return", placeholder["placeholder_kind"])
            self.assertEqual(
                "Expected result is not determined during test design generation.",
                placeholder["reason"],
            )
            self.assertEqual(
                "Review generated test case and replace TBD expected values.",
                placeholder["suggested_action"],
            )
            self.assertEqual("target_source", hint["hint_kind"])
            self.assertEqual("info", hint["severity"])
            self.assertEqual(
                "Build completion cannot be fully automated.",
                hint["message"],
            )

            self.assertIn("期待戻り値", markdown)
            self.assertIn("テスト設計生成時点では期待結果を確定できません。", markdown)
            self.assertIn("対象ソース", markdown)
            self.assertIn("情報", markdown)
            self.assertIn("ビルド補完は完全には自動化できません。", markdown)
            self.assertNotIn("Expected result is not determined", markdown)
            self.assertNotIn("Build completion cannot be fully automated", markdown)


if __name__ == "__main__":
    unittest.main()

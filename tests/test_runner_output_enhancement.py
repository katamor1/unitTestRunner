import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.execution.runner_output_parser import parse_runner_output
from unit_test_runner.harness.harness_models import TestSkeleton
from unit_test_runner.harness.runner_output_enhancer import enhance_runner_output


class RunnerOutputEnhancementTests(unittest.TestCase):
    def test_parser_accepts_utr_ok_failed_skipped_and_summary_lines(self):
        parsed = parse_runner_output(
            """
UTR RUN TC_Shared3_001
UTR OK TC_Shared3_001
UTR RUN TC_Shared3_002
UTR FAILED TC_Shared3_002
UTR SUMMARY total=2 passed=1 failed=1 skipped=0 inconclusive=0
"""
        )

        self.assertEqual(2, parsed.summary.total)
        self.assertEqual(1, parsed.summary.passed)
        self.assertEqual(1, parsed.summary.failed)
        cases = {case.test_case_id: case for case in parsed.case_results}
        self.assertEqual("passed", cases["TC_Shared3_001"].status)
        self.assertEqual("failed", cases["TC_Shared3_002"].status)

    def test_parser_marks_run_without_completion_as_crashed_on_nonzero_exit(self):
        parsed = parse_runner_output("UTR RUN TC_Shared3_001\n", exit_code=3221225477)

        self.assertEqual(1, parsed.summary.total)
        self.assertEqual(0, parsed.summary.passed)
        self.assertEqual(1, parsed.summary.crashed)
        self.assertEqual(1, parsed.summary.started)
        self.assertEqual(0, parsed.summary.completed)
        self.assertEqual("low", parsed.summary.parser_confidence)
        self.assertEqual("crashed", parsed.case_results[0].status)
        self.assertTrue(parsed.case_results[0].exit_related)
        self.assertIn("exit_code=3221225477", parsed.case_results[0].evidence)

    def test_enhanced_runner_emits_flush_ok_failed_summary_and_case_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "generated" / "harness").mkdir(parents=True)
            path = enhance_runner_output(
                workspace,
                "Shared3",
                [
                    TestSkeleton(
                        "TC_Shared3_001",
                        "Shared3",
                        Path("generated/tests/test_Shared3.c"),
                        "Test_TC_Shared3_001",
                        [],
                        [],
                        0,
                        True,
                    )
                ],
            )

            text = path.read_text(encoding="cp932")
            self.assertIn('printf("UTR RUN %s\\n"', text)
            self.assertIn('printf("UTR OK %s\\n"', text)
            self.assertIn('printf("UTR FAILED %s\\n"', text)
            self.assertIn('printf("UTR SUMMARY total=%d passed=%d failed=%d skipped=%d inconclusive=%d\\n"', text)
            self.assertIn("fflush(stdout);", text)
            self.assertIn("static int utr_test_count = 1;", text)
            self.assertIn("int Utr_RunNamedTest", text)
            self.assertIn('strcmp(argv[1], "--case")', text)


if __name__ == "__main__":
    unittest.main()

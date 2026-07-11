import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from unit_test_runner.reports.quick_summary import write_quick_summary


class QuickSummaryLinkResolutionTests(unittest.TestCase):
    def test_summary_counts_resolved_libraries_linked_functions_and_warnings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "result"
            reports = out_dir / "reports"
            reports.mkdir(parents=True)
            (reports / "call_report.json").write_text(
                json.dumps(
                    {
                        "calls": [
                            {"name": "LinkedOne", "target_kind": "linked_library_function"},
                            {"name": "LinkedTwo", "target_kind": "linked_library_function"},
                            {"name": "LinkedOne", "target_kind": "linked_library_function"},
                            {"name": "External", "target_kind": "external_function"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dossier = {
                "target": {
                    "source": "src/app.c",
                    "function": "App",
                    "configuration": "Win32 Debug",
                    "project": "App",
                },
                "build_context": {
                    "link_libraries": [{"path": "C:/lib/Product.lib"}],
                    "link_context_warnings": [
                        {"code": "library_symbol_scan_failed", "message": "broken library"}
                    ],
                },
                "diagnostics": [],
            }

            paths = write_quick_summary(out_dir, dossier, "harness", "harness_skeleton_generated")
            summary = json.loads(paths["json"].read_text(encoding="utf-8"))
            markdown = paths["markdown"].read_text(encoding="utf-8")

            self.assertEqual(1, summary["link_resolution"]["library_count"])
            self.assertEqual(2, summary["link_resolution"]["linked_function_count"])
            self.assertEqual(1, summary["link_resolution"]["warning_count"])
            self.assertEqual("library_symbol_scan_failed", summary["link_resolution"]["warnings"][0]["code"])
            self.assertIn("## リンク解決", markdown)
            self.assertIn("解決済みライブラリ: 1", markdown)
            self.assertIn("ライブラリ提供関数: 2", markdown)


if __name__ == "__main__":
    unittest.main()

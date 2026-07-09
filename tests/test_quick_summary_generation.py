import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
VC6_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "vc6_project"


def run_module(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "unit_test_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class QuickSummaryGenerationTests(unittest.TestCase):
    def test_quick_check_cli_writes_quick_summary_reports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "quick" / "Control_Update"
            completed = run_module(
                "--json",
                "quick-check",
                "--workspace",
                str(VC6_FIXTURE_ROOT),
                "--dsw",
                str(VC6_FIXTURE_ROOT / "Product.dsw"),
                "--source",
                "src/control.c",
                "--function",
                "Control_Update",
                "--configuration",
                "Win32 Debug",
                "--project",
                "Control",
                "--profile",
                "design",
                "--out",
                str(out_dir),
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            quick_json = out_dir / "reports" / "quick_summary.json"
            quick_md = out_dir / "reports" / "quick_summary.md"
            self.assertTrue(quick_json.exists())
            self.assertTrue(quick_md.exists())
            summary = json.loads(quick_json.read_text(encoding="utf-8"))
            stdout_payload = json.loads(completed.stdout)
            self.assertEqual("Control_Update", summary["target"]["function"])
            self.assertEqual("design", summary["phase"])
            self.assertEqual(str(quick_json), summary["reports"]["quick_summary_json"])
            self.assertEqual(str(quick_json), stdout_payload["reports"]["quick_summary_json"])
            self.assertEqual(str(quick_md), stdout_payload["reports"]["quick_summary_md"])
            self.assertIn("# Quick Check Summary", quick_md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

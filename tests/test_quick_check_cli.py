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


class QuickCheckCliTests(unittest.TestCase):
    def run_module(self, *args):
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

    def test_quick_check_design_profile_runs_without_review_finalization(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "quick" / "Control_Update"
            result = self.run_module(
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

            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual("analyze-function", payload["data"]["command"])
            self.assertEqual("passed", payload["data"]["outcome"])
            self.assertEqual("design", payload["data"]["details"]["phase"])
            self.assertTrue((out_dir / "reports" / "function_dossier.md").exists())
            self.assertTrue((out_dir / "reports" / "test_case_design.csv").exists())
            self.assertFalse((out_dir / "reports" / "review_checklist.md").exists())


if __name__ == "__main__":
    unittest.main()
